"""Auto-synth command: Automatic multi-anchor AoB synthesis."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import __version__
from .auto_anchor_search import find_stable_anchors_wide_search
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text
from .pe import PEFile, parse_hex_int
from .synth import run_synthesis_core


def run_auto_synth(args: Any) -> int:
    """
    Run automated multi-anchor synthesis.
    
    This command:
    1. Performs wide-range anchor search (±byte_range)
    2. Generates AoB candidates for top-N anchors
    3. Cross-validates all candidates across all versions
    4. Returns best stable signatures ranked by quality
    
    Note: anchor_shift is disabled in auto mode since we're already doing
    wide anchor enumeration. Using both would be redundant and slow.
    """
    base_pe = PEFile(args.base)
    
    # Parse center anchor
    if args.anchor_rva:
        center_rva = parse_hex_int(args.anchor_rva)
    elif args.anchor_fo:
        fo = parse_hex_int(args.anchor_fo)
        center_rva = base_pe.fo_to_rva(fo)
    elif args.anchor_va:
        va = parse_hex_int(args.anchor_va)
        center_rva = base_pe.va_to_rva(va)
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "Missing anchor")
    
    # Print progress to stderr
    if args.format != "json":
        print(f"[auto-synth] Searching for stable anchors around RVA {hex(center_rva)}...", file=sys.stderr)
    
    # Step 1: Find stable anchor candidates
    anchor_candidates = find_stable_anchors_wide_search(
        base_pe,
        center_rva,
        byte_range=args.byte_range,
        top_n=args.max_anchors,
        max_context_insns=args.max_context_insns,
    )
    
    if not anchor_candidates:
        raise AoBMasterError(
            ExitCode.ANCHOR_FAILURE,
            "no_anchors_found",
            "No suitable anchor candidates found in range",
            {"center_rva": hex(center_rva), "byte_range": args.byte_range},
        )
    
    if args.format != "json":
        print(f"[auto-synth] Found {len(anchor_candidates)} anchor candidates", file=sys.stderr)
        print(f"[auto-synth] Generating signatures for each anchor...", file=sys.stderr)
    
    # Step 2: Generate signatures for each anchor candidate
    all_results: list[dict[str, Any]] = []
    
    for idx, anchor_cand in enumerate(anchor_candidates, 1):
        if args.format != "json":
            print(f"[auto-synth] Processing anchor {idx}/{len(anchor_candidates)} at RVA {hex(anchor_cand.rva)}...", file=sys.stderr)
        
        try:
            # Run synthesis for this anchor
            synth_result = run_synthesis_core(
                base_binary=args.base,
                anchor_rva=anchor_cand.rva,
                anchor_fo=anchor_cand.fo,
                anchor_va=anchor_cand.va,
                version_binaries=args.versions,
                align_mode=args.align,
                seed_bytes=args.seed_bytes,
                seed_scan=args.seed_scan,
                seed_allow_multi=False,
                context_before=args.context_before,
                context_after=args.context_after,
                max_context_insns=args.max_context_insns,
                context_variations=(args.context_variations == "on"),
                profile=args.profile,
                min_insns=args.min_insns,
                max_insns=args.max_insns,
                require_unique=True,
                require_present_all=True,
                scan_range_base=None,
                scan_range_versions=None,
                explain=False,
                anchor_mode="byte-offset",
                structural_min_confidence=0.60,
                anchor_shift=0,  # Don't use anchor shift in auto mode (we're already doing wide search)
            )
            
            # Extract valid candidates from this anchor
            valid_candidates = [c for c in synth_result.get("candidates", []) if c.get("valid")]
            
            # Add anchor metadata to each candidate
            for cand in valid_candidates:
                cand["anchor_metadata"] = {
                    "anchor_rva": hex(anchor_cand.rva),
                    "anchor_fo": hex(anchor_cand.fo),
                    "anchor_va": hex(anchor_cand.va),
                    "anchor_score": anchor_cand.score,
                    "anchor_reason": anchor_cand.reason,
                }
            
            all_results.extend(valid_candidates)
            
        except AoBMasterError as e:
            # If synthesis fails for this anchor, log and continue
            if args.format != "json":
                print(f"[auto-synth] Warning: Anchor at RVA {hex(anchor_cand.rva)} failed: {e.message}", file=sys.stderr)
            continue
    
    if not all_results:
        raise AoBMasterError(
            ExitCode.ALIGNMENT_FAILURE,
            "no_valid_signatures",
            "No valid signatures found across any anchor candidates",
            {"anchors_tried": len(anchor_candidates)},
        )
    
    # Step 3: Sort all results by composite quality score
    # We want signatures that:
    # 1. Have high synth score
    # 2. Come from high-quality anchors
    for result in all_results:
        synth_score = result.get("score", {}).get("score", 0.0)
        anchor_score = result.get("anchor_metadata", {}).get("anchor_score", 0.0)
        # Composite: 70% synth quality, 30% anchor quality
        result["composite_score"] = 0.7 * synth_score + 0.3 * anchor_score
    
    all_results.sort(key=lambda x: x.get("composite_score", 0.0), reverse=True)
    
    # Step 4: Format output
    if args.format == "json":
        output = {
            "ok": True,
            "version": __version__,
            "mode": "auto-synth",
            "inputs": {
                "base": str(args.base),
                "center_anchor_rva": hex(center_rva),
                "byte_range": args.byte_range,
                "versions": [str(v) for v in args.versions],
                "max_anchors": args.max_anchors,
                "anchors_tried": len(anchor_candidates),
            },
            "total_candidates": len(all_results),
            "candidates": all_results[:args.top_n] if args.top_n > 0 else all_results,
        }
        emit_json(output)
        
    elif args.format == "text":
        lines = []
        lines.append("=" * 80)
        lines.append("AoBMaster Auto-Synth Results")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Base binary: {args.base}")
        lines.append(f"Center anchor: {hex(center_rva)}")
        lines.append(f"Search range: ±{args.byte_range} bytes")
        lines.append(f"Versions: {len(args.versions)}")
        lines.append(f"Anchors tried: {len(anchor_candidates)}")
        lines.append(f"Total signatures: {len(all_results)}")
        lines.append("")
        lines.append(f"Top {min(args.top_n, len(all_results))} signatures:")
        lines.append("")
        
        for idx, cand in enumerate(all_results[:args.top_n], 1):
            meta = cand.get("anchor_metadata", {})
            score_data = cand.get("score", {})
            
            lines.append(f"[{idx}] Pattern: {cand.get('aob', '')}")
            lines.append(f"    Composite Score: {cand.get('composite_score', 0.0):.3f}")
            lines.append(f"    Synth Score: {score_data.get('score', 0.0):.3f}")
            lines.append(f"    Anchor RVA: {meta.get('anchor_rva', 'N/A')} (quality: {meta.get('anchor_score', 0.0):.3f})")
            lines.append(f"    Reason: {meta.get('anchor_reason', 'N/A')}")
            lines.append("")
        
        emit_text(lines)
        
    elif args.format == "ce":
        lines = []
        lines.append("// Auto-generated by AoBMaster auto-synth")
        lines.append(f"// Base: {args.base}")
        lines.append(f"// Center anchor: {hex(center_rva)}")
        lines.append("")
        
        for idx, cand in enumerate(all_results[:args.top_n], 1):
            meta = cand.get("anchor_metadata", {})
            aob = cand.get('aob', '')
            lines.append(f"// Anchor RVA: {meta.get('anchor_rva', 'N/A')}, Score: {cand.get('composite_score', 0.0):.3f}")
            lines.append(f"aobscanmodule(AUTO_SIG_{idx}, {Path(args.base).name}, {aob})")
            lines.append("")
        
        emit_text(lines)
    
    return int(ExitCode.SUCCESS)
