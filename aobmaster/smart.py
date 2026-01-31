"""Smart analysis command: Suggest stable anchor points."""
from __future__ import annotations

from typing import Any

from . import __version__
from .disasm import decode_anchor_context
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text
from .pe import PEFile, parse_hex_int
from .smart_analyzer import find_stable_anchors


def run_smart(args: Any) -> int:
    """Run smart analysis to suggest stable anchors."""
    base_pe = PEFile(args.base)
    
    # Parse RVA
    start_rva = parse_hex_int(args.rva)
    start_fo = base_pe.rva_to_fo(start_rva)
    
    # Find section
    section = base_pe.section_containing_rva(start_rva)
    if not section:
        raise AoBMasterError(
            ExitCode.ANCHOR_FAILURE,
            "rva_out_of_range",
            "RVA not within any section",
            {"rva": hex(start_rva)},
        )
    
    # Decode instructions
    try:
        ctx = decode_anchor_context(
            base_pe,
            section,
            anchor_fo=start_fo,
            context_before=0,
            context_after=args.insns,
            max_context_insns=args.insns + 10,
        )
    except Exception as e:
        raise AoBMasterError(
            ExitCode.DISASM_FAILURE,
            "disasm_failed",
            f"Failed to disassemble region: {e}",
            {"rva": hex(start_rva)},
        ) from e
    
    # Find stable anchors
    top_n = max(1, args.top_n)
    stable_anchors = find_stable_anchors(ctx.insns, top_n=top_n)
    
    # Build output
    if args.format == "json":
        out_obj = {
            "ok": True,
            "version": __version__,
            "inputs": {
                "base": str(args.base),
                "rva": hex(start_rva),
                "insns_analyzed": len(ctx.insns),
                "top_n": top_n,
            },
            "suggestions": [
                {
                    "fo": hex(a.fo),
                    "rva": hex(base_pe.fo_to_rva(a.fo)),
                    "va": hex(base_pe.rva_to_va(base_pe.fo_to_rva(a.fo))),
                    "score": round(a.score, 4),
                    "reason": a.reason,
                    "details": a.details,
                }
                for a in stable_anchors
            ],
        }
        emit_json(out_obj)
    else:  # text
        lines = []
        lines.append(f"AoBMaster Smart Analysis")
        lines.append(f"Base: {args.base}")
        lines.append(f"Start RVA: {hex(start_rva)}")
        lines.append(f"Instructions analyzed: {len(ctx.insns)}")
        lines.append("")
        lines.append(f"Top {len(stable_anchors)} stable anchor suggestions:")
        lines.append("")
        
        for i, anchor in enumerate(stable_anchors, 1):
            rva = base_pe.fo_to_rva(anchor.fo)
            lines.append(f"{i}. RVA {hex(rva)} (score: {anchor.score:.3f})")
            lines.append(f"   {anchor.reason}")
            lines.append("")
        
        lines.append("Use one of these RVAs with 'aobmaster synth --anchor-rva <rva>'")
        emit_text(lines)
    
    return int(ExitCode.SUCCESS)
