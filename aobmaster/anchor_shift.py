"""Anchor shifting: Try nearby instructions as alternative anchors."""
from __future__ import annotations

from typing import Any

from .disasm import decode_anchor_context
from .pe import PEFile, Section


def generate_shifted_anchors(
    base_pe: PEFile,
    base_section: Section,
    base_anchor_fo: int,
    *,
    shift_range: int,
    max_context_insns: int,
) -> list[tuple[int, int]]:
    """
    Generate alternative anchor offsets by shifting ±N instructions.
    
    Args:
        base_pe: PE file
        base_section: Section containing anchor
        base_anchor_fo: Base anchor file offset
        shift_range: Number of instructions to shift (±N)
        max_context_insns: Maximum context instructions for decoding
    
    Returns:
        List of (file_offset, instruction_index_shift) tuples for shifted anchors.
        Includes the original anchor (shift=0) at index 0.
    """
    if shift_range <= 0:
        return [(base_anchor_fo, 0)]
    
    # Decode a larger context to get neighboring instructions
    context_before = min(shift_range + 8, max_context_insns // 2)
    context_after = min(shift_range + 8, max_context_insns // 2)
    
    try:
        ctx = decode_anchor_context(
            base_pe,
            base_section,
            anchor_fo=base_anchor_fo,
            context_before=context_before,
            context_after=context_after,
            max_context_insns=max_context_insns,
        )
    except Exception:
        # If context decoding fails, just return original anchor
        return [(base_anchor_fo, 0)]
    
    anchor_idx = ctx.anchor_index
    results = [(base_anchor_fo, 0)]  # Original anchor first
    
    # Add shifted anchors
    for shift in range(-shift_range, shift_range + 1):
        if shift == 0:
            continue  # Skip original (already added)
        
        shifted_idx = anchor_idx + shift
        if 0 <= shifted_idx < len(ctx.insns):
            shifted_fo = ctx.insns[shifted_idx].fo
            results.append((shifted_fo, shift))
    
    return results
