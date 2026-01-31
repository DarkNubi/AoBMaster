from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import __version__
from .align import align_versions
from .anchor_shift import generate_shifted_anchors
from .candidates import Candidate, deduplicate_candidates, generate_candidates
from .disasm import decode_anchor_context, resync_anchor_to_insn_start
from .errors import AoBMasterError, AoBMasterWarning, ExitCode
from .ir_bridge import convert_candidate_to_ir, format_explain_output
from .matcher import AoBPattern, scan_ranges
from .normalize import normalize_context
from .output import emit_json, emit_text
from .pe import PEFile, parse_hex_int
from .score import (
    ScoreBreakdown,
    anchor_proximity,
    compute_confidence,
    compute_score,
    length_regularization,
)
from .trace import (
    AlignmentEvent,
    AnchorResolutionEvent,
    AnchorResyncEvent,
    ScoringEvent,
    TraceCollector,
)
from .util import round6, sha256_file, unique_preserve_order


def _scan_domain_ranges_for_anchor(pe: PEFile, *, domain: str, anchor_rva: int) -> list[tuple[int, bytes]]:
    if domain == "section":
        sec = pe.section_containing_rva(anchor_rva)
        if not sec:
            raise AoBMasterError(
                ExitCode.ANCHOR_FAILURE,
                "anchor_out_of_range",
                "Anchor not within any section",
                {"path": str(pe.path), "anchor_rva": hex(anchor_rva)},
            )
        return [(sec.raw_ptr, pe.read_fo(sec.raw_ptr, sec.raw_size))]
    if domain == "module":
        ranges: list[tuple[int, bytes]] = []
        for s in pe.executable_sections():
            ranges.append((s.raw_ptr, pe.read_fo(s.raw_ptr, s.raw_size)))
        return ranges
    raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown scan range: {domain}")


def _resolve_anchor(base_pe: PEFile, args: Any) -> tuple[int, int, int]:
    if args.anchor_rva:
        rva = parse_hex_int(args.anchor_rva)
    elif args.anchor_fo:
        fo = parse_hex_int(args.anchor_fo)
        rva = base_pe.fo_to_rva(fo)
    elif args.anchor_va:
        va = parse_hex_int(args.anchor_va)
        rva = base_pe.va_to_rva(va)
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "Missing anchor")
    fo = base_pe.rva_to_fo(rva)
    va = base_pe.rva_to_va(rva)
    return rva, fo, va


def _bool_arg(s: str) -> bool:
    if s == "true":
        return True
    if s == "false":
        return False
    raise ValueError("expected true|false")


def run_synth(args: Any) -> int:
    # Initialize trace collector (v2 feature, opt-in)
    trace = TraceCollector(enabled=getattr(args, 'explain', False))
    warnings: list[AoBMasterWarning] = []
    
    base_pe = PEFile(args.base)
    versions = unique_preserve_order([str(p) for p in (args.versions or [])])
    version_paths = [Path(p) for p in versions if Path(p) != args.base]

    base_anchor_rva, base_anchor_fo, base_anchor_va = _resolve_anchor(base_pe, args)
    
    # Phase 6 (v2): Structural anchor resolution (OPT-IN, HIGH RISK)
    structural_context = None
    anchor_mode = getattr(args, 'anchor_mode', 'byte-offset')
    
    if anchor_mode == 'structural':
        # Import here to avoid dependency when not using structural mode
        from .structural import (
            resolve_structural_anchor,
            validate_structural_anchor,
            get_structural_context
        )
        
        structural_context = get_structural_context(base_pe, base_anchor_rva)
        
        # Structural context is added to final output JSON, not trace
        # (Adding to trace would require creating a StructuralAnchorEvent class)
        
        # Validate structural anchor
        min_confidence = getattr(args, 'structural_min_confidence', 0.60)
        if structural_context["confidence"] < min_confidence:
            # Automatic fallback to byte-offset mode when confidence is too low
            warnings.append(AoBMasterWarning(
                "structural_anchor_fallback",
                f"Structural anchor confidence {structural_context['confidence']:.2f} below threshold {min_confidence:.2f}. "
                f"Falling back to byte-offset mode.",
                {
                    "confidence": structural_context["confidence"],
                    "min_confidence": min_confidence,
                    "warnings": structural_context["warnings"]
                }
            ))
            # Setting to None signals fallback to byte-offset anchor mode
            structural_context = None
        elif structural_context["warnings"]:
            for warning_msg in structural_context["warnings"]:
                warnings.append(AoBMasterWarning("structural_anchor_warning", warning_msg, {}))
    
    # Trace anchor resolution
    trace.add(AnchorResolutionEvent(
        input_rva=parse_hex_int(args.anchor_rva) if args.anchor_rva else None,
        input_fo=parse_hex_int(args.anchor_fo) if args.anchor_fo else None,
        input_va=parse_hex_int(args.anchor_va) if args.anchor_va else None,
        resolved_fo=base_anchor_fo,
        resolved_rva=base_anchor_rva,
        section=base_pe.section_containing_rva(base_anchor_rva).name if base_pe.section_containing_rva(base_anchor_rva) else "unknown",
    ))
    
    base_section = base_pe.section_containing_rva(base_anchor_rva)
    if not base_section:
        raise AoBMasterError(
            ExitCode.ANCHOR_FAILURE,
            "anchor_out_of_range",
            "Anchor not within any section",
            {"anchor_rva": hex(base_anchor_rva)},
        )

    # Instruction boundary recovery is defined as part of anchor handling; do it before bytespan alignment.
    original_fo = base_anchor_fo
    base_anchor_fo, w = resync_anchor_to_insn_start(base_pe, base_section, base_anchor_fo)
    if w:
        warnings.append(w)
        # Trace resync event
        trace.add(AnchorResyncEvent(
            original_fo=original_fo,
            resynced_fo=base_anchor_fo,
            backtrack_bytes=original_fo - base_anchor_fo,
            instruction_asm="(instruction at resynced offset)",
        ))
    base_anchor_rva = base_pe.fo_to_rva(base_anchor_fo)
    base_anchor_va = base_pe.rva_to_va(base_anchor_rva)

    aligned = align_versions(
        base_pe=base_pe,
        base_anchor_fo=base_anchor_fo,
        base_anchor_rva=base_anchor_rva,
        base_anchor_section=base_section,
        version_paths=version_paths,
        mode=args.align,
        seed_bytes=args.seed_bytes,
        seed_scan=args.seed_scan,
        seed_allow_multi=_bool_arg(args.seed_allow_multi),
    )
    
    # Trace alignment events
    for aligned_anchor in aligned:
        if aligned_anchor.path != str(args.base):
            drift = aligned_anchor.anchor_rva - base_anchor_rva
            # Determine ambiguity: seed_hits > 1 means multiple matches (ambiguous)
            ambiguity = aligned_anchor.seed_hits is not None and aligned_anchor.seed_hits > 1
            trace.add(AlignmentEvent(
                mode=args.align,
                base_rva=base_anchor_rva,
                version_path=str(aligned_anchor.path),
                aligned_rva=aligned_anchor.anchor_rva,
                drift=drift,
                ambiguity=ambiguity,
            ))

    # After alignment, the "base" record is aligned[0] and may differ from initial FO
    base_aligned_fo = aligned[0].anchor_fo
    base_aligned_rva = aligned[0].anchor_rva
    base_section = base_pe.section_containing_rva(base_aligned_rva)  # should exist
    if not base_section:
        raise AoBMasterError(ExitCode.ANCHOR_FAILURE, "anchor_out_of_range", "Anchor not within any section")

    # Anchor shifting: Generate alternative anchor offsets if enabled
    anchor_shift_range = getattr(args, 'anchor_shift', 0)
    shifted_anchors = [(base_aligned_fo, 0)]  # Default: just the original anchor
    
    if anchor_shift_range > 0:
        shifted_anchors = generate_shifted_anchors(
            base_pe,
            base_section,
            base_aligned_fo,
            shift_range=anchor_shift_range,
            max_context_insns=args.max_context_insns,
        )
        if len(shifted_anchors) > 1:
            warnings.append(
                AoBMasterWarning(
                    kind="anchor_shift_enabled",
                    message=f"Anchor shifting enabled: trying {len(shifted_anchors)} anchor positions (±{anchor_shift_range} instructions)",
                    details={"shift_range": anchor_shift_range, "anchor_count": len(shifted_anchors)},
                )
            )

    # Context variations: generate candidates for multiple context windows if enabled
    context_configs = [(args.context_before, args.context_after)]
    if args.context_variations == "on":
        # Add variations: forward-heavy, backward-heavy, and balanced
        context_configs.extend([
            (0, 10),   # Forward only
            (0, 15),   # Forward only (longer)
            (5, 10),   # Balanced
            (10, 5),   # Backward heavy
            (12, 8),   # Slightly backward heavy
        ])

    all_candidates = []
    
    # Try each shifted anchor
    for shifted_fo, shift_idx in shifted_anchors:
        # For each anchor, try all context configurations
        for ctx_before, ctx_after in context_configs:
            try:
                ctx = decode_anchor_context(
                    base_pe,
                    base_section,
                    anchor_fo=shifted_fo,
                    context_before=ctx_before,
                    context_after=ctx_after,
                    max_context_insns=args.max_context_insns,
                )
            except Exception as e:
                # If context decoding fails for a shifted anchor, skip it
                warnings.append(
                    AoBMasterWarning(
                        kind="anchor_shift_decode_failed",
                        message=f"Failed to decode context for shifted anchor (shift={shift_idx}): {e}",
                        details={"shift": shift_idx, "anchor_fo": hex(shifted_fo)},
                    )
                )
                continue
                
            warnings.extend(list(ctx.warnings))

            norm_ctx = normalize_context(ctx.insns, profile=args.profile)
            candidates, cand_warnings = generate_candidates(
                norm_ctx,
                anchor_ctx_index=ctx.anchor_index,
                min_insns=args.min_insns,
                max_insns=args.max_insns,
            )
            warnings.extend(cand_warnings)
            all_candidates.extend(candidates)

    # Use all_candidates from context variations and anchor shifting
    candidates = all_candidates

    # Apply similarity-based deduplication to remove near-duplicate patterns
    candidates = deduplicate_candidates(candidates, threshold=0.75)

    require_unique = _bool_arg(args.require_unique)
    require_present_all = _bool_arg(args.require_present_all)

    # scan-range defaults: base=section, versions=module unless user explicitly sets --scan-range
    scan_range_base = args.scan_range or "section"
    scan_range_versions = args.scan_range or ("module" if version_paths else "section")

    # Build PE objects for versions once.
    pes: dict[Path, PEFile] = {args.base: base_pe}
    for p in version_paths:
        pes[p] = PEFile(p)

    # Drift metrics for confidence
    max_drift_rva = 0
    had_alignment_ambiguity = any(a.seed_hits and a.seed_hits > 1 for a in aligned[1:])
    for a in aligned[1:]:
        if abs(a.drift_rva) > abs(max_drift_rva):
            max_drift_rva = a.drift_rva

    had_resync_warning = any(w.kind == "anchor_resynced" for w in warnings)

    results: list[dict[str, Any]] = []

    for c in candidates:
        rec: dict[str, Any] = c.to_dict()
        if c.rejected:
            rec["valid"] = False
            results.append(rec)
            continue

        # Scan in base and versions
        per_file: dict[str, Any] = {}
        base_ranges = _scan_domain_ranges_for_anchor(base_pe, domain=scan_range_base, anchor_rva=base_aligned_rva)
        base_hits = scan_ranges(base_ranges, c.pattern)
        per_file[str(args.base)] = {"count": len(base_hits), "hits_fo": [hex(x) for x in base_hits]}

        version_present = 0
        version_total = len(version_paths)
        version_unique_ok = True
        version_present_ok = True

        for a in aligned[1:]:
            pe = pes[a.path]
            v_ranges = _scan_domain_ranges_for_anchor(pe, domain=scan_range_versions, anchor_rva=a.anchor_rva)
            hits = scan_ranges(v_ranges, c.pattern)
            per_file[str(a.path)] = {"count": len(hits), "hits_fo": [hex(x) for x in hits], "drift_rva": a.drift_rva}
            if hits:
                version_present += 1
            else:
                version_present_ok = False
            if len(hits) > 1:
                version_unique_ok = False

        # Validation
        valid = True
        if require_unique:
            if len(base_hits) != 1:
                valid = False
            if version_total and (not version_unique_ok):
                valid = False
            if version_total and (not version_present_ok):
                valid = False
        else:
            if len(base_hits) < 1:
                valid = False
            if require_present_all and version_total and (not version_present_ok):
                valid = False

        rec["matches"] = per_file
        rec["valid"] = valid

        if not valid:
            results.append(rec)
            continue

        # Score components
        if require_unique:
            U = 1.0
        else:
            U = 1.0 / float(len(base_hits)) if base_hits else 0.0

        if version_total == 0:
            P = 1.0
        else:
            P = version_present / float(version_total)

        S = 1.0 - c.wildcard_ratio
        L = length_regularization(c.total_bytes)
        A = anchor_proximity(c.anchor_index, c.window_len)
        score = compute_score(uniqueness=U, presence=P, specificity=S, length_reg=L, anchor_prox=A)
        conf = compute_confidence(
            num_versions=version_total,
            max_drift_rva=max_drift_rva,
            had_resync_warning=had_resync_warning,
            had_alignment_ambiguity=had_alignment_ambiguity,
        )
        
        # Trace scoring event
        trace.add(ScoringEvent(
            candidate_pattern=c.pattern.to_ce_string(),
            uniqueness=U,
            presence=P,
            specificity=S,
            length_reg=L,
            anchor_prox=A,
            final_score=score,
            confidence=conf,
        ))
        
        sb = ScoreBreakdown(U=U, P=P, S=S, L=L, A=A, score=score, confidence=conf)
        rec["score"] = sb.to_dict()
        results.append(rec)

    # Rank valid results deterministically
    def rank_key(r: dict[str, Any]) -> tuple:
        if not r.get("valid"):
            return (1, 0, "", 0)
        s = r.get("score", {})
        score = float(s.get("score", 0.0))
        conf = float(s.get("confidence", 0.0))
        aob = str(r.get("aob", ""))
        byte_len = int(r.get("byte_len", 0))
        return (0, -score, -conf, -byte_len, aob)

    results.sort(key=rank_key)

    out_obj: dict[str, Any] = {
        "ok": True,
        "version": __version__,
        "inputs": {
            "base": str(args.base),
            "versions": [str(p) for p in version_paths],
            "anchor": {
                "anchor_rva": args.anchor_rva,
                "anchor_fo": args.anchor_fo,
                "anchor_va": args.anchor_va,
                "anchor_mode": anchor_mode,  # v2 Phase 6
            },
            "align": {
                "mode": args.align,
                "seed_bytes": args.seed_bytes,
                "seed_scan": args.seed_scan,
                "seed_allow_multi": _bool_arg(args.seed_allow_multi),
            },
            "context": {
                "before": args.context_before,
                "after": args.context_after,
                "max_insns": args.max_context_insns,
            },
            "profile": args.profile,
            "candidate_windows": {"min_insns": args.min_insns, "max_insns": args.max_insns},
            "scan_range": {"base": scan_range_base, "versions": scan_range_versions},
            "validation": {"require_unique": require_unique, "require_present_all": require_present_all},
        },
        "hashes": {str(p): {"sha256": sha256_file(Path(p))} for p in [args.base, *version_paths]},
        "anchor": {
            "resolved_base": {"fo": hex(base_aligned_fo), "rva": hex(base_aligned_rva), "va": hex(base_pe.rva_to_va(base_aligned_rva))},
            "section": base_section.name,
        },
        "alignment": [a.to_dict() for a in aligned],
        "warnings": [w.to_dict() for w in warnings],
        "errors": [],
        "candidates": results,
    }
    
    # Add structural context if structural mode was used (v2 Phase 6)
    if structural_context:
        out_obj["structural_anchor"] = structural_context
    
    # Add trace data if explain mode is enabled (v2 feature)
    if trace.enabled:
        out_obj["trace"] = trace.to_dict()
        # Add SignatureIR for top candidate if available
        top_candidates = [r for r in results if r.get("valid")]
        if top_candidates and top_candidates[0].get("insns"):
            try:
                from .matcher import parse_ce_aob
                top_cand = top_candidates[0]
                # Convert top candidate to SignatureIR using proper parsing
                pattern_bytes, pattern_mask = parse_ce_aob(top_cand.get("aob", ""))
                sig_ir = convert_candidate_to_ir(
                    insns=top_cand.get("insns", []),
                    pattern_bytes=pattern_bytes,
                    pattern_mask=pattern_mask,
                    pattern_string=top_cand.get("aob", ""),
                    anchor_fo=base_aligned_fo,
                    anchor_rva=base_aligned_rva,
                    profile=args.profile,
                    section_name=base_section.name,
                )
                out_obj["signature_ir"] = sig_ir.to_dict()
            except Exception:
                # Silently skip IR conversion if it fails (best-effort)
                pass

    if args.format == "json":
        emit_json(out_obj)
    elif args.format == "text":
        # Check if explain mode is enabled
        if trace.enabled:
            # Output explain format instead of normal text
            sig_ir = out_obj.get("signature_ir")
            if sig_ir:
                from .signature_ir import SignatureIR
                # Reconstruct SignatureIR from dict (simplified)
                sig_ir_obj = None  # Would need full reconstruction
            else:
                sig_ir_obj = None
            explain_lines = format_explain_output(trace.get_events(), sig_ir_obj)
            emit_text(explain_lines)
        else:
            # Normal text output
            lines: list[str] = []
            lines.append("AoBMaster v1.1")
            lines.append(f"Base: {args.base}")
            lines.append(f"Anchor: RVA {hex(base_aligned_rva)} (FO {hex(base_aligned_fo)}) Section {base_section.name}")
            lines.append("")

            top_n = max(1, args.top_n if hasattr(args, 'top_n') else 5)
            top = [r for r in results if r.get("valid")][:top_n]
            if not top:
                lines.append("No valid candidates.")
            else:
                lines.append(f"Top {len(top)} candidates:")
                for i, r in enumerate(top, 1):
                    s = r.get("score", {})
                    lines.append(f"{i}. score={s.get('score')} conf={s.get('confidence')} bytes={r.get('byte_len')} wc={r.get('wildcard_ratio')}")
                    lines.append(f"   {r.get('aob')}")
            emit_text(lines)
    elif args.format == "ce":
        module_name = Path(args.base).name
        top_n = max(1, args.top_n if hasattr(args, 'top_n') else 5)
        top = [r for r in results if r.get("valid")][:top_n]
        lines: list[str] = []
        if not top:
            lines.append("; AoBMaster: no valid candidates")
        for i, r in enumerate(top, 1):
            name = f"AOB_MASTER_{i}"
            lines.append(f"aobscanmodule({name}, {module_name}, {r.get('aob')})")
        emit_text(lines)
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown format: {args.format}")

    return int(ExitCode.SUCCESS)
