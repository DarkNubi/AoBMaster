"""Auto-recover command: Automatic signature recovery for broken patterns."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text
from .pe import PEFile, parse_hex_int
from .recovery import diagnose_signature_failure, run_recovery_strategies
from .synth import run_synthesis_core


def run_auto_recover(args: Any) -> int:
    """
    Run automated signature recovery.
    
    This command:
    1. Diagnoses why the signature failed (not found vs multiple matches)
    2. Runs recovery strategies in priority order
    3. For each recovered anchor, generates new signatures
    4. Returns ranked results with confidence scores
    """
    # Load binaries
    base_pe = PEFile(args.base)
    target_pe = PEFile(args.target)
    
    # Parse original anchor from base binary
    if args.anchor_rva:
        original_anchor_rva = parse_hex_int(args.anchor_rva)
    elif args.anchor_fo:
        fo = parse_hex_int(args.anchor_fo)
        original_anchor_rva = base_pe.fo_to_rva(fo)
    elif args.anchor_va:
        va = parse_hex_int(args.anchor_va)
        original_anchor_rva = base_pe.va_to_rva(va)
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "Missing anchor")
    
    # Print progress
    if args.format != "json":
        print(f"[auto-recover] Analyzing signature failure...", file=sys.stderr)
    
    # Step 1: Diagnose signature failure (if signature provided)
    failure_reason = "unknown"
    match_locations = []
    
    if args.signature:
        failure_reason, match_locations = diagnose_signature_failure(
            target_pe,
            args.signature,
            scan_range="module",
        )
        
        if args.format != "json":
            if failure_reason == "not_found":
                print(f"[auto-recover] Signature not found in target binary", file=sys.stderr)
            elif failure_reason == "multiple_matches":
                print(f"[auto-recover] Signature has {len(match_locations)} matches (expected 1)", file=sys.stderr)
            elif failure_reason == "found":
                print(f"[auto-recover] Note: Signature was actually found (no recovery needed)", file=sys.stderr)
    
    # Step 2: Run recovery strategies
    if args.format != "json":
        print(f"[auto-recover] Running recovery strategies...", file=sys.stderr)
    
    # Parse strategies
    strategies = args.strategies.split(",") if args.strategies else None
    
    # Convert target RVA (might not exist in target at same location)
    # We'll search around the approximate location
    try:
        target_search_rva = original_anchor_rva  # Start with same RVA
    except Exception:
        # If conversion fails, just use original
        target_search_rva = original_anchor_rva
    
    recovery_results = run_recovery_strategies(
        target_pe,
        target_search_rva,
        strategies=strategies,
        byte_range=args.byte_range,
    )
    
    # Filter to successful results
    successful_recoveries = [r for r in recovery_results if r.success]
    
    if not successful_recoveries:
        if args.format == "json":
            output = {
                "ok": False,
                "version": __version__,
                "mode": "auto-recover",
                "inputs": {
                    "base": str(args.base),
                    "target": str(args.target),
                    "original_anchor_rva": hex(original_anchor_rva),
                    "signature": args.signature,
                },
                "diagnosis": {
                    "failure_reason": failure_reason,
                    "match_count": len(match_locations),
                },
                "recovery_attempts": len(recovery_results),
                "successful_recoveries": 0,
                "results": [],
            }
            emit_json(output)
        else:
            print("\nNo successful recovery strategies found.", file=sys.stderr)
            print("The signature could not be automatically recovered.", file=sys.stderr)
        
        return int(ExitCode.NO_CANDIDATES)
    
    if args.format != "json":
        print(f"[auto-recover] Found {len(successful_recoveries)} potential recovery points", file=sys.stderr)
        print(f"[auto-recover] Generating signatures for recovered anchors...", file=sys.stderr)
    
    # Step 3: Generate signatures for each recovered anchor
    recovered_signatures: list[dict[str, Any]] = []
    
    for idx, recovery in enumerate(successful_recoveries[:args.max_results], 1):
        if args.format != "json":
            print(f"[auto-recover] Processing recovery {idx}/{min(args.max_results, len(successful_recoveries))} (strategy: {recovery.strategy})...", file=sys.stderr)
        
        try:
            # Generate signature at recovered anchor
            synth_result = run_synthesis_core(
                base_binary=args.target,  # Use target as base for synthesis
                anchor_rva=recovery.anchor_rva,
                anchor_fo=recovery.anchor_fo,
                anchor_va=target_pe.rva_to_va(recovery.anchor_rva),
                version_binaries=[],  # No multi-version validation in recovery
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
                require_unique=True,
                require_present_all=False,  # Only one binary
                scan_range_base=None,
                scan_range_versions=None,
                explain=False,
                anchor_mode="byte-offset",
                structural_min_confidence=0.60,
                anchor_shift=0,
            )
            
            # Get top candidate
            valid_candidates = [c for c in synth_result.get("candidates", []) if c.get("valid")]
            
            if valid_candidates:
                top_candidate = valid_candidates[0]  # Already sorted by score
                
                # Add recovery metadata
                recovered_signatures.append({
                    "recovery_strategy": recovery.strategy,
                    "recovery_confidence": recovery.confidence,
                    "recovery_reason": recovery.reason,
                    "anchor_rva": hex(recovery.anchor_rva),
                    "anchor_fo": hex(recovery.anchor_fo),
                    "drift_from_original": recovery.anchor_rva - original_anchor_rva,
                    "signature": top_candidate.get("aob", ""),
                    "signature_score": top_candidate.get("score", {}),
                    "byte_length": top_candidate.get("byte_len", 0),
                    "details": recovery.details,
                })
        
        except Exception as e:
            if args.format != "json":
                print(f"[auto-recover] Warning: Failed to generate signature at RVA {hex(recovery.anchor_rva)}: {e}", file=sys.stderr)
            continue
    
    if not recovered_signatures:
        raise AoBMasterError(
            ExitCode.NO_CANDIDATES,
            "no_signatures_generated",
            "Recovery strategies succeeded but no signatures could be generated",
            {"recoveries_tried": len(successful_recoveries)},
        )
    
    # Step 4: Format output
    if args.format == "json":
        output = {
            "ok": True,
            "version": __version__,
            "mode": "auto-recover",
            "inputs": {
                "base": str(args.base),
                "target": str(args.target),
                "original_anchor_rva": hex(original_anchor_rva),
                "signature": args.signature,
                "strategies": strategies or ["anchor_shift", "xref_search", "function_boundary"],
            },
            "diagnosis": {
                "failure_reason": failure_reason,
                "match_count": len(match_locations),
            },
            "recovery_attempts": len(recovery_results),
            "successful_recoveries": len(successful_recoveries),
            "total_signatures": len(recovered_signatures),
            "results": recovered_signatures,
        }
        emit_json(output)
        
    elif args.format == "text":
        lines = []
        lines.append("=" * 80)
        lines.append("AoBMaster Auto-Recover Results")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Base binary: {args.base}")
        lines.append(f"Target binary: {args.target}")
        lines.append(f"Original anchor: {hex(original_anchor_rva)}")
        if args.signature:
            lines.append(f"Original signature: {args.signature}")
            lines.append(f"Failure reason: {failure_reason}")
        lines.append("")
        lines.append(f"Recovery attempts: {len(recovery_results)}")
        lines.append(f"Successful recoveries: {len(successful_recoveries)}")
        lines.append(f"Generated signatures: {len(recovered_signatures)}")
        lines.append("")
        lines.append(f"Top {len(recovered_signatures)} recovered signatures:")
        lines.append("")
        
        for idx, sig in enumerate(recovered_signatures, 1):
            lines.append(f"[{idx}] Strategy: {sig['recovery_strategy']}")
            lines.append(f"    Anchor RVA: {sig['anchor_rva']} (drift: {sig['drift_from_original']:+d} bytes)")
            lines.append(f"    Confidence: {sig['recovery_confidence']:.3f}")
            lines.append(f"    Reason: {sig['recovery_reason']}")
            lines.append(f"    Signature: {sig['signature']}")
            score_data = sig.get("signature_score", {})
            lines.append(f"    Signature Score: {score_data.get('score', 0.0):.3f}")
            lines.append("")
        
        emit_text(lines)
        
    elif args.format == "ce":
        lines = []
        lines.append("// Auto-recovered signatures by AoBMaster")
        lines.append(f"// Base: {args.base}")
        lines.append(f"// Target: {args.target}")
        lines.append(f"// Original anchor: {hex(original_anchor_rva)}")
        lines.append("")
        
        for idx, sig in enumerate(recovered_signatures, 1):
            lines.append(f"// Strategy: {sig['recovery_strategy']}, Confidence: {sig['recovery_confidence']:.3f}")
            lines.append(f"// Anchor: {sig['anchor_rva']}, Drift: {sig['drift_from_original']:+d} bytes")
            lines.append(f"aobscanmodule(RECOVERED_SIG_{idx}, {Path(args.target).name}, {sig['signature']})")
            lines.append("")
        
        emit_text(lines)
    
    return int(ExitCode.SUCCESS)
