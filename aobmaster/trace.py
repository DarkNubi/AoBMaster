"""
Structured trace events for AoBMaster v2 explainability.

All decisions (anchor resolution, wildcarding, scoring, rejection) are logged
as structured events that can be queried and formatted for --explain mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of trace events."""
    
    ANCHOR_RESOLUTION = "anchor_resolution"
    ANCHOR_RESYNC = "anchor_resync"
    ALIGNMENT = "alignment"
    WILDCARDING = "wildcarding"
    CANDIDATE_GENERATION = "candidate_generation"
    CANDIDATE_REJECTION = "candidate_rejection"
    SCORING = "scoring"
    DEDUPLICATION = "deduplication"
    VALIDATION = "validation"


@dataclass
class TraceEvent:
    """Base class for all trace events."""
    
    event_type: EventType
    phase: str  # "anchor_resolution", "normalization", "scoring", etc.
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event_type.value,
            "phase": self.phase,
            "description": self.description,
            "details": self.details,
        }


@dataclass
class AnchorResolutionEvent(TraceEvent):
    """Trace event for anchor resolution."""
    
    def __init__(
        self,
        input_rva: int | None,
        input_fo: int | None,
        input_va: int | None,
        resolved_fo: int,
        resolved_rva: int,
        section: str,
    ):
        super().__init__(
            event_type=EventType.ANCHOR_RESOLUTION,
            phase="anchor_resolution",
            description=f"Resolved anchor to FO {hex(resolved_fo)}, RVA {hex(resolved_rva)} in section {section}",
            details={
                "input": {
                    "rva": hex(input_rva) if input_rva is not None else None,
                    "fo": hex(input_fo) if input_fo is not None else None,
                    "va": hex(input_va) if input_va is not None else None,
                },
                "resolved": {
                    "fo": hex(resolved_fo),
                    "rva": hex(resolved_rva),
                    "section": section,
                },
            },
        )


@dataclass
class AnchorResyncEvent(TraceEvent):
    """Trace event for instruction boundary recovery."""
    
    def __init__(
        self,
        original_fo: int,
        resynced_fo: int,
        backtrack_bytes: int,
        instruction_asm: str,
    ):
        super().__init__(
            event_type=EventType.ANCHOR_RESYNC,
            phase="anchor_resolution",
            description=f"Resynced anchor from {hex(original_fo)} to {hex(resynced_fo)} (backtracked {backtrack_bytes} bytes)",
            details={
                "original_fo": hex(original_fo),
                "resynced_fo": hex(resynced_fo),
                "backtrack_bytes": backtrack_bytes,
                "instruction": instruction_asm,
            },
        )


@dataclass
class AlignmentEvent(TraceEvent):
    """Trace event for multi-version alignment."""
    
    def __init__(
        self,
        mode: str,
        base_rva: int,
        version_path: str,
        aligned_rva: int,
        drift: int,
        ambiguity: bool,
    ):
        super().__init__(
            event_type=EventType.ALIGNMENT,
            phase="alignment",
            description=f"Aligned version {version_path}: RVA {hex(aligned_rva)}, drift={drift:+d}",
            details={
                "mode": mode,
                "base_rva": hex(base_rva),
                "version_path": version_path,
                "aligned_rva": hex(aligned_rva),
                "drift": drift,
                "ambiguity": ambiguity,
            },
        )


@dataclass
class WildcardingEvent(TraceEvent):
    """Trace event for wildcarding decision."""
    
    def __init__(
        self,
        instruction_offset: int,
        instruction_asm: str,
        byte_positions: list[int],
        operand_type: str,
        reason: str,
        profile: str,
    ):
        super().__init__(
            event_type=EventType.WILDCARDING,
            phase="normalization",
            description=f"Wildcarded bytes {byte_positions} in '{instruction_asm}': {reason}",
            details={
                "instruction_offset": hex(instruction_offset),
                "instruction_asm": instruction_asm,
                "byte_positions": byte_positions,
                "operand_type": operand_type,
                "reason": reason,
                "profile": profile,
            },
        )


@dataclass
class CandidateRejectionEvent(TraceEvent):
    """Trace event for candidate rejection."""
    
    def __init__(
        self,
        candidate_pattern: str,
        rejection_reason: str,
        details_data: dict[str, Any],
    ):
        super().__init__(
            event_type=EventType.CANDIDATE_REJECTION,
            phase="candidate_generation",
            description=f"Rejected candidate: {rejection_reason}",
            details={
                "pattern": candidate_pattern,
                "reason": rejection_reason,
                **details_data,
            },
        )


@dataclass
class ScoringEvent(TraceEvent):
    """Trace event for scoring breakdown."""
    
    def __init__(
        self,
        candidate_pattern: str,
        uniqueness: float,
        presence: float,
        specificity: float,
        length_reg: float,
        anchor_prox: float,
        final_score: float,
        confidence: float,
    ):
        super().__init__(
            event_type=EventType.SCORING,
            phase="scoring",
            description=f"Scored candidate: U={uniqueness:.3f} P={presence:.3f} S={specificity:.3f} L={length_reg:.3f} A={anchor_prox:.3f} → {final_score:.3f}",
            details={
                "pattern": candidate_pattern,
                "factors": {
                    "uniqueness": round(uniqueness, 3),
                    "presence": round(presence, 3),
                    "specificity": round(specificity, 3),
                    "length_reg": round(length_reg, 3),
                    "anchor_prox": round(anchor_prox, 3),
                },
                "final_score": round(final_score, 3),
                "confidence": round(confidence, 3),
            },
        )


@dataclass
class DeduplicationEvent(TraceEvent):
    """Trace event for candidate deduplication."""
    
    def __init__(
        self,
        kept_pattern: str,
        removed_pattern: str,
        similarity: float,
    ):
        super().__init__(
            event_type=EventType.DEDUPLICATION,
            phase="candidate_generation",
            description=f"Removed duplicate candidate (similarity={similarity:.2%})",
            details={
                "kept": kept_pattern,
                "removed": removed_pattern,
                "similarity": round(similarity, 3),
            },
        )


class TraceCollector:
    """
    Collects trace events during execution.
    
    Thread-safe collector for --explain mode.
    """
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._events: list[TraceEvent] = []
    
    def add(self, event: TraceEvent) -> None:
        """Add a trace event."""
        if self.enabled:
            self._events.append(event)
    
    def get_events(self) -> list[TraceEvent]:
        """Get all collected events."""
        return list(self._events)
    
    def get_events_by_phase(self, phase: str) -> list[TraceEvent]:
        """Get events for a specific phase."""
        return [e for e in self._events if e.phase == phase]
    
    def get_events_by_type(self, event_type: EventType) -> list[TraceEvent]:
        """Get events of a specific type."""
        return [e for e in self._events if e.event_type == event_type]
    
    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "enabled": self.enabled,
            "event_count": len(self._events),
            "events": [e.to_dict() for e in self._events],
        }
