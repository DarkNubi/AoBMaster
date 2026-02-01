from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .errors import AoBMasterError, ExitCode
from .matcher import parse_ce_aob, scan_ranges
from .output import emit_json, emit_text
from .pe import PEFile
from .score import length_regularization
from .synth import _resolve_anchor, run_synthesis_core
from .util import round6, sha256_file


def _build_scan_ranges(pe: PEFile, *, scan_range: str, section_name: str | None) -> list[tuple[int, bytes]]:
    if scan_range == "module":
        ranges: list[tuple[int, bytes]] = []
        for s in pe.executable_sections():
            ranges.append((s.raw_ptr, pe.read_fo(s.raw_ptr, s.raw_size)))
        return ranges
    if scan_range == "section":
        if not section_name:
            raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "--section is required when --scan-range=section")
        sec = pe.section_by_name(section_name)
        if not sec:
            raise AoBMasterError(
                ExitCode.INVALID_ARGS,
                "invalid_args",
                "Section not found",
                {"section": section_name},
            )
        return [(sec.raw_ptr, pe.read_fo(sec.raw_ptr, sec.raw_size))]
    raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown scan-range: {scan_range}")


def _candidate_score(base_score: float, *, match_count: int, byte_len: int) -> float:
    uniqueness = 1.0 if match_count == 1 else 1.0 / float(match_count)
    length_factor = length_regularization(byte_len)
    return base_score * uniqueness * length_factor


def run_locate(args: Any) -> int:
    base_pe = PEFile(args.base)
    base_anchor_rva, base_anchor_fo, base_anchor_va = _resolve_anchor(base_pe, args)

    synth_obj = run_synthesis_core(
        base_binary=args.base,
        anchor_rva=base_anchor_rva,
        anchor_fo=base_anchor_fo,
        anchor_va=base_anchor_va,
        version_binaries=[],
        align_mode="bytespan",
        seed_bytes=32,
        seed_scan="section",
        seed_allow_multi=False,
        context_before=args.context_before,
        context_after=args.context_after,
        max_context_insns=args.max_context_insns,
        context_variations=(args.context_variations == "on"),
        profile=args.profile,
        min_insns=args.min_insns,
        max_insns=args.max_insns,
        require_unique=False,
        require_present_all=False,
        scan_range_base=None,
        scan_range_versions=None,
        explain=False,
        anchor_mode="byte-offset",
        structural_min_confidence=0.60,
        anchor_shift=args.anchor_shift,
    )

    base_candidates = [c for c in synth_obj.get("candidates", []) if c.get("valid")]
    base_candidates = base_candidates[: max(1, args.candidate_limit)]

    targets: list[dict[str, Any]] = []
    for target_path in args.target:
        target_pe = PEFile(target_path)
        ranges = _build_scan_ranges(target_pe, scan_range=args.scan_range, section_name=args.section)

        results: list[dict[str, Any]] = []
        for cand in base_candidates:
            aob = cand.get("aob", "")
            if not aob:
                continue
            pat = parse_ce_aob(aob)
            hits = scan_ranges(ranges, pat)
            if not hits:
                continue
            hits.sort()
            match_count = len(hits)
            if match_count > 1 and not args.allow_multiple:
                continue

            base_score = float(cand.get("score", {}).get("score", 0.0))
            byte_len = int(cand.get("byte_len", 0))
            score = _candidate_score(base_score, match_count=match_count, byte_len=byte_len)
            first_hit = hits[0]
            hit_rva = target_pe.fo_to_rva(first_hit)
            hit_va = target_pe.rva_to_va(hit_rva)

            record: dict[str, Any] = {
                "target_rva": hex(hit_rva),
                "target_fo": hex(first_hit),
                "target_va": hex(hit_va),
                "score": round6(score),
                "match_count": match_count,
                "candidate": {
                    "aob": aob,
                    "wildcard_ratio": cand.get("wildcard_ratio"),
                    "byte_len": byte_len,
                    "base_score": round6(base_score),
                },
            }
            if match_count > 1 or args.explain:
                record["hits"] = [
                    {
                        "fo": hex(h),
                        "rva": hex(target_pe.fo_to_rva(h)),
                        "va": hex(target_pe.rva_to_va(target_pe.fo_to_rva(h))),
                    }
                    for h in hits
                ]
            results.append(record)

        results.sort(key=lambda r: (-float(r.get("score", 0.0)), r.get("target_rva", "")))
        results = results[: max(1, args.top_n)]
        targets.append({"path": str(target_path), "results": results})

    out_obj = {
        "ok": True,
        "version": __version__,
        "base": {
            "path": str(args.base),
            "anchor_rva": hex(base_anchor_rva),
            "anchor_fo": hex(base_anchor_fo),
            "anchor_va": hex(base_anchor_va),
        },
        "inputs": {
            "scan_range": args.scan_range,
            "candidate_limit": args.candidate_limit,
            "allow_multiple": bool(args.allow_multiple),
            "top_n": args.top_n,
        },
        "hashes": {str(p): {"sha256": sha256_file(Path(p))} for p in [args.base, *args.target]},
        "targets": targets,
        "warnings": synth_obj.get("warnings", []),
        "errors": [],
    }
    if args.explain:
        out_obj["base_candidates"] = base_candidates

    if args.format == "json":
        emit_json(out_obj)
    elif args.format == "text":
        lines: list[str] = []
        lines.append(f"AoBMaster locate v{__version__}")
        lines.append(f"Base: {args.base}")
        lines.append(f"Anchor: RVA {hex(base_anchor_rva)} (FO {hex(base_anchor_fo)})")
        lines.append("")
        for target in targets:
            lines.append(f"Target: {target['path']}")
            results = target.get("results", [])
            if not results:
                lines.append("  No candidates found.")
                continue
            for idx, res in enumerate(results, 1):
                lines.append(
                    f"  {idx}. score={res.get('score')} rva={res.get('target_rva')} matches={res.get('match_count')}"
                )
                lines.append(f"     {res.get('candidate', {}).get('aob')}")
            lines.append("")
        emit_text(lines)
    elif args.format == "ce":
        lines = []
        for target in targets:
            for idx, res in enumerate(target.get("results", []), 1):
                name = f"AOB_LOCATE_{idx}"
                lines.append(f"aobscanmodule({name}, {Path(target['path']).name}, {res.get('candidate', {}).get('aob')})")
        if not lines:
            lines.append("; AoBMaster locate: no results")
        emit_text(lines)
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown format: {args.format}")

    return int(ExitCode.SUCCESS)
