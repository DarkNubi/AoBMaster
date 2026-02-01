"""Signature recovery: Automated strategies for finding broken signatures."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .auto_anchor_search import find_stable_anchors_wide_search
from .disasm import decode_anchor_context
from .errors import AoBMasterError, ExitCode
from .matcher import parse_ce_aob, scan_ranges
from .pe import PEFile, Section
from .structural import detect_function_boundary


@dataclass(frozen=True)
class RecoveryResult:
    """Result from a recovery strategy."""
    strategy: str
    success: bool
    anchor_rva: int
    anchor_fo: int
    confidence: float
    reason: str
    details: dict[str, Any]


def diagnose_signature_failure(
    target_pe: PEFile,
    pattern_str: str,
    *,
    scan_range: str = "module",
) -> tuple[str, list[int]]:
    """
    Diagnose why a signature failed.
    
    Returns:
        (failure_reason, match_locations)
        failure_reason: "not_found" or "multiple_matches"
        match_locations: List of file offsets where pattern was found
    """
    try:
        pattern = parse_ce_aob(pattern_str)
    except AoBMasterError:
        return ("invalid_pattern", [])
    
    # Build scan ranges
    ranges: list[tuple[int, bytes]] = []
    if scan_range == "module":
        for s in target_pe.executable_sections():
            ranges.append((s.raw_ptr, target_pe.read_fo(s.raw_ptr, s.raw_size)))
    else:
        # Default to module scan
        for s in target_pe.executable_sections():
            ranges.append((s.raw_ptr, target_pe.read_fo(s.raw_ptr, s.raw_size)))
    
    # Scan for pattern
    hits = scan_ranges(ranges, pattern)
    
    if not hits:
        return ("not_found", [])
    elif len(hits) == 1:
        return ("found", hits)  # Actually found, not a failure
    else:
        return ("multiple_matches", hits)


def strategy_anchor_shift(
    target_pe: PEFile,
    original_anchor_rva: int,
    *,
    byte_range: int = 50,
    top_n: int = 5,
) -> list[RecoveryResult]:
    """
    Recovery strategy: Try nearby instructions as anchors.
    
    This is the fastest and most reliable strategy.
    """
    results: list[RecoveryResult] = []
    
    try:
        # Find stable anchors in wider range
        candidates = find_stable_anchors_wide_search(
            target_pe,
            original_anchor_rva,
            byte_range=byte_range,
            top_n=top_n,
        )
        
        for cand in candidates:
            results.append(
                RecoveryResult(
                    strategy="anchor_shift",
                    success=True,
                    anchor_rva=cand.rva,
                    anchor_fo=cand.fo,
                    confidence=cand.score,
                    reason=f"Found stable anchor near original location: {cand.reason}",
                    details={
                        "drift_from_original": cand.rva - original_anchor_rva,
                        "anchor_quality": cand.score,
                    },
                )
            )
    except Exception as e:
        results.append(
            RecoveryResult(
                strategy="anchor_shift",
                success=False,
                anchor_rva=0,
                anchor_fo=0,
                confidence=0.0,
                reason=f"Anchor shift failed: {str(e)}",
                details={},
            )
        )
    
    return results


def strategy_xref_search(
    target_pe: PEFile,
    original_anchor_rva: int,
    *,
    ref_types: str = "call,jmp",
    max_refs: int = 20,
) -> list[RecoveryResult]:
    """
    Recovery strategy: Find calls/jumps to the target address.
    
    Useful when the function has moved but callers still exist.
    NOTE: This is a placeholder for future xref-based recovery.
    Currently returns no results as it requires more complex implementation.
    """
    results: list[RecoveryResult] = []
    
    # Placeholder: XRef-based recovery is complex and requires
    # decoding all instructions in the binary to find references.
    # For now, we return empty results.
    results.append(
        RecoveryResult(
            strategy="xref_search",
            success=False,
            anchor_rva=0,
            anchor_fo=0,
            confidence=0.0,
            reason="XRef recovery not yet implemented",
            details={},
        )
    )
    
    return results


def strategy_function_boundary(
    target_pe: PEFile,
    original_anchor_rva: int,
) -> list[RecoveryResult]:
    """
    Recovery strategy: Detect function boundaries and anchor there.
    
    Function prologues/epilogues are often more stable.
    """
    results: list[RecoveryResult] = []
    
    try:
        # Detect function boundary at or before the anchor
        boundary = detect_function_boundary(target_pe, original_anchor_rva)
        
        if not boundary:
            results.append(
                RecoveryResult(
                    strategy="function_boundary",
                    success=False,
                    anchor_rva=0,
                    anchor_fo=0,
                    confidence=0.0,
                    reason="No function boundary detected",
                    details={},
                )
            )
            return results
        
        # Use function start as anchor
        results.append(
            RecoveryResult(
                strategy="function_boundary",
                success=True,
                anchor_rva=boundary.start_rva,
                anchor_fo=boundary.start_fo,
                confidence=boundary.confidence,
                reason=f"Function prologue detected: {boundary.prologue_pattern}",
                details={
                    "detection_method": boundary.detection_method,
                    "prologue_size": boundary.prologue_size,
                    "distance_from_original": abs(boundary.start_rva - original_anchor_rva),
                },
            )
        )
    
    except Exception as e:
        results.append(
            RecoveryResult(
                strategy="function_boundary",
                success=False,
                anchor_rva=0,
                anchor_fo=0,
                confidence=0.0,
                reason=f"Function boundary detection failed: {str(e)}",
                details={},
            )
        )
    
    return results


def run_recovery_strategies(
    target_pe: PEFile,
    original_anchor_rva: int,
    *,
    strategies: list[str] | None = None,
    byte_range: int = 50,
) -> list[RecoveryResult]:
    """
    Run multiple recovery strategies in priority order.
    
    Args:
        target_pe: Target binary where signature broke
        original_anchor_rva: Original anchor RVA from base binary
        strategies: List of strategy names to run (None = all)
                   Note: xref_search is currently unimplemented and returns placeholder
        byte_range: Byte range for anchor shift strategy
    
    Returns:
        List of recovery results sorted by confidence
    """
    if strategies is None:
        # Default strategies: anchor_shift is fast and reliable
        # function_boundary is slower but handles larger code changes
        # xref_search is unimplemented placeholder
        strategies = ["anchor_shift", "function_boundary"]
    
    all_results: list[RecoveryResult] = []
    
    for strategy in strategies:
        if strategy == "anchor_shift":
            results = strategy_anchor_shift(target_pe, original_anchor_rva, byte_range=byte_range)
            all_results.extend(results)
        
        elif strategy == "xref_search":
            results = strategy_xref_search(target_pe, original_anchor_rva)
            all_results.extend(results)
        
        elif strategy == "function_boundary":
            results = strategy_function_boundary(target_pe, original_anchor_rva)
            all_results.extend(results)
    
    # Sort by confidence (highest first)
    all_results.sort(key=lambda x: x.confidence, reverse=True)
    
    return all_results
