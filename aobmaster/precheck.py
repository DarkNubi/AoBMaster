"""Pattern uniqueness pre-check: Fast estimation before full synthesis."""
from __future__ import annotations

from .matcher import AoBPattern, scan_bytes
from .pe import PEFile


def estimate_pattern_uniqueness(
    pe: PEFile,
    pattern: AoBPattern,
    *,
    section_name: str | None = None,
) -> tuple[int, bool]:
    """
    Quickly estimate how many times a pattern appears in the binary.
    
    Args:
        pe: PE file to search
        pattern: AoB pattern to search for
        section_name: Optional section name to limit search
    
    Returns:
        (match_count, is_unique) tuple
        - match_count: Number of matches found (capped at 100 for performance)
        - is_unique: True if exactly 1 match found
    """
    max_checks = 100  # Cap to avoid excessive scanning
    
    if section_name:
        section = pe.section_by_name(section_name)
        if section:
            data = pe.read_fo(section.raw_ptr, section.raw_size)
            hits = scan_bytes(data, pattern)
            count = min(len(hits), max_checks)
            return (count, count == 1)
    
    # Scan all executable sections
    total_hits = 0
    for section in pe.executable_sections():
        data = pe.read_fo(section.raw_ptr, section.raw_size)
        hits = scan_bytes(data, pattern)
        total_hits += len(hits)
        
        if total_hits > max_checks:
            return (total_hits, False)  # Too many matches, not unique
    
    return (total_hits, total_hits == 1)
