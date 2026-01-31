"""
Structural Anchors for AoBMaster v2 Phase 6

Provides function boundary detection, prologue/epilogue recognition,
and structural anchor resolution for patch-resilient signatures.

HIGH RISK MODULE: Uses heuristics. Must fail loudly. Opt-in only.
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
from .disasm import disassemble
from .pe import PEFile


@dataclass
class FunctionBoundary:
    """Detected function boundary with confidence score."""
    start_rva: int
    start_fo: int
    prologue_size: int  # bytes
    prologue_pattern: str  # human-readable description
    confidence: float  # 0.0-1.0
    detection_method: str  # "standard_prologue" | "push_prologue" | "frameless" | "symbol"


@dataclass
class StructuralAnchor:
    """Structural anchor relative to function boundaries."""
    anchor_rva: int
    anchor_fo: int
    function_start_rva: int
    offset_from_function_start: int  # bytes
    anchor_type: str  # "prologue" | "epilogue" | "call_site" | "relative"
    description: str
    confidence: float


# Standard x64 function prologues (ordered by confidence)
PROLOGUE_PATTERNS = [
    # Standard frame pointer setup (highest confidence)
    {
        "pattern": [0x55, 0x48, 0x89, 0xE5],  # push rbp; mov rbp, rsp
        "name": "standard_frame_pointer",
        "confidence": 0.95,
        "min_length": 4
    },
    {
        "pattern": [0x48, 0x83, 0xEC],  # sub rsp, imm8 (frameless with stack alloc)
        "name": "frameless_with_stack",
        "confidence": 0.85,
        "min_length": 4  # sub rsp, imm8 is 4 bytes
    },
    {
        "pattern": [0x48, 0x81, 0xEC],  # sub rsp, imm32 (larger stack frame)
        "name": "frameless_large_stack",
        "confidence": 0.85,
        "min_length": 7  # sub rsp, imm32 is 7 bytes
    },
    {
        "pattern": [0x40, 0x53],  # push rbx (common register save)
        "name": "register_save_prologue",
        "confidence": 0.70,
        "min_length": 2
    },
    {
        "pattern": [0x55],  # push rbp alone
        "name": "simple_push_prologue",
        "confidence": 0.60,
        "min_length": 1
    },
]


def detect_function_boundary(pe: PEFile, rva: int) -> Optional[FunctionBoundary]:
    """
    Detect function boundary at or before the given RVA.
    
    Searches backwards from RVA to find function prologue patterns.
    Uses heuristics - may fail.
    
    Args:
        pe: PE file object
        rva: Target RVA to search from
        
    Returns:
        FunctionBoundary if detected, None if not found or low confidence
    """
    section = pe.rva_to_section(rva)
    if not section or section.name not in [".text", "CODE"]:
        return None  # Only analyze code sections
    
    # Search backwards up to 1024 bytes for function start
    search_range = min(1024, rva - section.rva)
    start_rva = rva - search_range
    
    fo = pe.rva_to_fo(start_rva)
    if fo is None:
        return None
    
    data = pe.data[fo:fo + search_range + 64]  # Extra bytes for prologue analysis
    
    # Try to find prologue patterns
    best_match = None
    best_confidence = 0.0
    
    for offset in range(0, search_range, 1):
        for pattern_info in PROLOGUE_PATTERNS:
            pattern = pattern_info["pattern"]
            if offset + len(pattern) > len(data):
                continue
                
            # Check if pattern matches
            if all(data[offset + i] == pattern[i] for i in range(len(pattern))):
                # Additional validation: check alignment
                candidate_rva = start_rva + offset
                if candidate_rva % 16 != 0 and pattern_info["confidence"] < 0.80:
                    # Lower confidence for unaligned functions (unless high-confidence pattern)
                    confidence = pattern_info["confidence"] * 0.7
                else:
                    confidence = pattern_info["confidence"]
                
                # Prefer matches closer to target RVA
                distance_penalty = (rva - candidate_rva) / 1024.0 * 0.1
                confidence = max(0.1, confidence - distance_penalty)
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    candidate_fo = pe.rva_to_fo(candidate_rva)
                    best_match = FunctionBoundary(
                        start_rva=candidate_rva,
                        start_fo=candidate_fo,
                        prologue_size=pattern_info["min_length"],
                        prologue_pattern=pattern_info["name"],
                        confidence=confidence,
                        detection_method=pattern_info["name"]
                    )
    
    # Only return if confidence is reasonable
    if best_match and best_match.confidence >= 0.50:
        return best_match
    
    return None


def resolve_structural_anchor(
    pe: PEFile,
    rva: int,
    anchor_type: str = "relative"
) -> Optional[StructuralAnchor]:
    """
    Resolve a structural anchor relative to function boundaries.
    
    Args:
        pe: PE file object
        rva: Target RVA
        anchor_type: Type of structural anchor:
            - "relative": Anchor relative to nearest function start
            - "prologue": Anchor within function prologue
            - "absolute": Convert to absolute RVA (fallback to v1.x behavior)
            
    Returns:
        StructuralAnchor if successful, None if detection failed
    """
    # Detect function boundary
    func = detect_function_boundary(pe, rva)
    
    if func is None:
        # Fallback: treat as absolute anchor (v1.x behavior)
        fo = pe.rva_to_fo(rva)
        if fo is None:
            return None
            
        return StructuralAnchor(
            anchor_rva=rva,
            anchor_fo=fo,
            function_start_rva=rva,  # No function detected
            offset_from_function_start=0,
            anchor_type="absolute",
            description="No function boundary detected; using absolute RVA (v1.x fallback)",
            confidence=0.30  # Low confidence - couldn't detect structure
        )
    
    # Calculate offset from function start
    offset = rva - func.start_rva
    fo = pe.rva_to_fo(rva)
    
    if fo is None:
        return None
    
    # Determine anchor type
    if offset < func.prologue_size:
        actual_type = "prologue"
        description = f"Within function prologue (+{offset} bytes from function start)"
        confidence = func.confidence * 0.95  # High confidence - prologue is stable
    elif offset < 64:
        actual_type = "relative"
        description = f"Early in function (+{offset} bytes from function start)"
        confidence = func.confidence * 0.85  # Good confidence - early function body
    else:
        actual_type = "relative"
        description = f"Mid-function (+{offset} bytes from function start)"
        confidence = func.confidence * 0.70  # Lower confidence - deeper in function
    
    return StructuralAnchor(
        anchor_rva=rva,
        anchor_fo=fo,
        function_start_rva=func.start_rva,
        offset_from_function_start=offset,
        anchor_type=actual_type,
        description=description,
        confidence=confidence
    )


def validate_structural_anchor(anchor: StructuralAnchor, min_confidence: float = 0.60) -> Tuple[bool, str]:
    """
    Validate a structural anchor meets minimum confidence requirements.
    
    Args:
        anchor: StructuralAnchor to validate
        min_confidence: Minimum acceptable confidence (default 0.60)
        
    Returns:
        (is_valid, failure_reason)
    """
    if anchor.confidence < min_confidence:
        return False, f"Confidence {anchor.confidence:.2f} below threshold {min_confidence:.2f}"
    
    if anchor.anchor_type == "absolute":
        return False, "Could not detect function boundary; structural mode requires function detection"
    
    # Warn if offset is very large (>1KB into function)
    if anchor.offset_from_function_start > 1024:
        return False, f"Anchor is {anchor.offset_from_function_start} bytes into function (too deep for reliable structural anchoring)"
    
    return True, "Structural anchor valid"


def get_structural_context(pe: PEFile, rva: int) -> dict:
    """
    Get structural context information for debugging/explain mode.
    
    Returns dictionary with:
    - function_detected: bool
    - function_start_rva: Optional[int]
    - prologue_pattern: Optional[str]
    - offset_from_start: int
    - confidence: float
    - warnings: List[str]
    """
    anchor = resolve_structural_anchor(pe, rva, anchor_type="relative")
    
    if anchor is None:
        return {
            "function_detected": False,
            "function_start_rva": None,
            "prologue_pattern": None,
            "offset_from_start": 0,
            "confidence": 0.0,
            "warnings": ["Failed to resolve structural anchor"]
        }
    
    warnings = []
    is_valid, reason = validate_structural_anchor(anchor, min_confidence=0.50)
    if not is_valid:
        warnings.append(reason)
    
    if anchor.confidence < 0.70:
        warnings.append(f"Low confidence ({anchor.confidence:.2f}) - structural anchor may be unreliable")
    
    return {
        "function_detected": anchor.anchor_type != "absolute",
        "function_start_rva": anchor.function_start_rva,
        "prologue_pattern": anchor.description,
        "offset_from_start": anchor.offset_from_function_start,
        "confidence": anchor.confidence,
        "anchor_type": anchor.anchor_type,
        "warnings": warnings
    }
