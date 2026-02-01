"""Enhanced anchor search: Wide-range multi-anchor enumeration and quality filtering."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .disasm import DecodedInsn, decode_anchor_context
from .pe import PEFile, Section
from .smart_analyzer import score_instruction_stability


@dataclass(frozen=True)
class AnchorCandidate:
    """Represents a potential anchor point with quality score."""
    fo: int
    rva: int
    va: int
    score: float
    reason: str
    insn: DecodedInsn


def enumerate_instructions_in_range(
    pe: PEFile,
    section: Section,
    center_fo: int,
    *,
    byte_range: int,
    max_context_insns: int = 200,
) -> list[tuple[DecodedInsn, int]]:
    """
    Enumerate all instructions within ±byte_range of center_fo.
    
    Args:
        pe: PE file
        section: Section containing the center point
        center_fo: Center file offset
        byte_range: Byte range to search (±N bytes)
        max_context_insns: Maximum instructions to decode
    
    Returns:
        List of (decoded_instruction, rva) tuples in the range
    """
    # Calculate byte bounds
    start_fo = max(section.raw_ptr, center_fo - byte_range)
    end_fo = min(section.raw_ptr + section.raw_size, center_fo + byte_range)
    
    # Decode larger context to get all instructions
    context_before = max(0, byte_range // 2)  # Rough estimate
    context_after = max(0, byte_range // 2)
    
    try:
        ctx = decode_anchor_context(
            pe,
            section,
            anchor_fo=center_fo,
            context_before=context_before,
            context_after=context_after,
            max_context_insns=max_context_insns,
        )
    except Exception:
        # If context decode fails, return empty
        return []
    
    # Filter to instructions within byte range and compute RVAs
    result: list[tuple[DecodedInsn, int]] = []
    for insn in ctx.insns:
        if start_fo <= insn.fo <= end_fo:
            rva = pe.fo_to_rva(insn.fo)
            result.append((insn, rva))
    
    return result


def score_anchor_candidates(
    instructions: list[tuple[DecodedInsn, int]],
    *,
    top_n: int = 10,
) -> list[AnchorCandidate]:
    """
    Score and rank instructions as potential anchors.
    
    Args:
        instructions: List of (decoded_instruction, rva) tuples
        top_n: Number of top candidates to return
    
    Returns:
        List of top-N anchor candidates sorted by score (best first)
    """
    scored: list[tuple[float, DecodedInsn, int, str]] = []
    
    for insn, rva in instructions:
        score = score_instruction_stability(insn)
        
        # Generate reason based on score
        if score >= 0.7:
            reason = "High stability anchor"
        elif score >= 0.5:
            reason = "Moderate stability anchor"
        else:
            reason = "Low stability anchor"
        
        scored.append((score, insn, rva, reason))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Take top N and convert to AnchorCandidate
    result: list[AnchorCandidate] = []
    for score, insn, rva, reason in scored[:top_n]:
        # Compute VA from IP
        va = insn.ip
        result.append(
            AnchorCandidate(
                fo=insn.fo,
                rva=rva,
                va=va,
                score=score,
                reason=reason,
                insn=insn,
            )
        )
    
    return result


def find_stable_anchors_wide_search(
    pe: PEFile,
    center_rva: int,
    *,
    byte_range: int = 100,
    top_n: int = 10,
    max_context_insns: int = 200,
) -> list[AnchorCandidate]:
    """
    Perform wide search for stable anchors around a center point.
    
    This is the main entry point for automated multi-anchor search.
    It enumerates all instructions within ±byte_range and scores them.
    
    Args:
        pe: PE file to analyze
        center_rva: Center RVA to search around
        byte_range: Byte range to search (±N bytes from center)
        top_n: Number of top candidates to return
        max_context_insns: Maximum instructions to decode
    
    Returns:
        List of top-N anchor candidates sorted by quality score
    """
    # Find section
    section = pe.section_containing_rva(center_rva)
    if not section:
        return []
    
    center_fo = pe.rva_to_fo(center_rva)
    
    # Enumerate all instructions in range
    instructions = enumerate_instructions_in_range(
        pe,
        section,
        center_fo,
        byte_range=byte_range,
        max_context_insns=max_context_insns,
    )
    
    if not instructions:
        return []
    
    # Score and rank
    return score_anchor_candidates(instructions, top_n=top_n)
