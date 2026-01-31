"""
Signature IR (Intermediate Representation) for AoBMaster v2.

This module defines self-describing signature objects that encode:
- Instruction-level breakdown
- Wildcard reasons
- Constraints
- Anchor metadata
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WildcardReason:
    """Explains why specific bytes were wildcarded."""
    
    positions: tuple[int, ...]  # Byte offsets within instruction
    operand_type: str  # "branch", "displacement", "immediate", "rip_relative", etc.
    reason: str  # Human-readable explanation
    profile_rule: str  # Which profile rule triggered this
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": list(self.positions),
            "operand_type": self.operand_type,
            "reason": self.reason,
            "profile_rule": self.profile_rule,
        }


@dataclass(frozen=True)
class InstructionIR:
    """Intermediate representation of a single instruction in a signature."""
    
    offset: int  # File offset
    rva: int  # Relative virtual address
    asm: str  # Disassembly text
    bytes_raw: bytes  # Raw instruction bytes
    bytes_pattern: bytes  # Pattern bytes (with wildcards as 0x00)
    mask: bytes  # Mask (0xFF = fixed, 0x00 = wildcard)
    wildcards: tuple[WildcardReason, ...]  # Explanations for each wildcard group
    
    @property
    def length(self) -> int:
        return len(self.bytes_raw)
    
    @property
    def has_wildcards(self) -> bool:
        return any(m == 0x00 for m in self.mask)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": hex(self.offset),
            "rva": hex(self.rva),
            "asm": self.asm,
            "bytes_raw": self.bytes_raw.hex(" ").upper(),
            "bytes_pattern": self.bytes_pattern.hex(" ").upper(),
            "mask": self.mask.hex(" ").upper(),
            "length": self.length,
            "has_wildcards": self.has_wildcards,
            "wildcards": [w.to_dict() for w in self.wildcards],
        }


@dataclass(frozen=True)
class SignatureConstraint:
    """Constraint that must hold for signature validity."""
    
    constraint_type: str  # "section", "alignment", "no_relocation", "proximity", etc.
    description: str  # Human-readable constraint
    validation_logic: str  # Pseudo-code or description of how to validate
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.constraint_type,
            "description": self.description,
            "validation": self.validation_logic,
        }


@dataclass
class SignatureIR:
    """
    Self-describing signature intermediate representation.
    
    This is the canonical v2 signature format with full metadata.
    """
    
    # Pattern data
    pattern_bytes: bytes  # Pattern with wildcards as 0x00
    pattern_mask: bytes  # Mask (0xFF = fixed, 0x00 = wildcard)
    pattern_string: str  # CE-style "48 8B ?? ??"
    
    # Instruction breakdown
    instructions: tuple[InstructionIR, ...]
    
    # Anchor metadata
    anchor_offset: int  # File offset of anchor
    anchor_rva: int  # RVA of anchor
    anchor_instruction_index: int  # Which instruction in window is the anchor
    
    # Constraints
    constraints: tuple[SignatureConstraint, ...] = field(default_factory=tuple)
    
    # Metadata
    byte_length: int = field(init=False)
    wildcard_count: int = field(init=False)
    wildcard_ratio: float = field(init=False)
    
    def __post_init__(self):
        object.__setattr__(self, "byte_length", len(self.pattern_bytes))
        object.__setattr__(self, "wildcard_count", sum(1 for m in self.pattern_mask if m == 0x00))
        object.__setattr__(self, "wildcard_ratio", self.wildcard_count / self.byte_length if self.byte_length > 0 else 0.0)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "pattern": {
                "bytes": self.pattern_bytes.hex(" ").upper(),
                "mask": self.pattern_mask.hex(" ").upper(),
                "string": self.pattern_string,
                "length": self.byte_length,
                "wildcard_count": self.wildcard_count,
                "wildcard_ratio": round(self.wildcard_ratio, 3),
            },
            "instructions": [insn.to_dict() for insn in self.instructions],
            "anchor": {
                "offset": hex(self.anchor_offset),
                "rva": hex(self.anchor_rva),
                "instruction_index": self.anchor_instruction_index,
            },
            "constraints": [c.to_dict() for c in self.constraints],
        }
