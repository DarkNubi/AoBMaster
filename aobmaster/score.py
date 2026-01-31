from __future__ import annotations

from dataclasses import dataclass

from .util import clamp01, round6


@dataclass(frozen=True)
class ScoreBreakdown:
    U: float
    P: float
    S: float
    L: float
    A: float
    score: float
    confidence: float

    def to_dict(self) -> dict[str, float]:
        return {
            "U": round6(self.U),
            "P": round6(self.P),
            "S": round6(self.S),
            "L": round6(self.L),
            "A": round6(self.A),
            "score": round6(self.score),
            "confidence": round6(self.confidence),
        }


def length_regularization(byte_len: int) -> float:
    # Prefers ~32 bytes; penalizes too short/long (0..64).
    if byte_len <= 0:
        return 0.0
    if byte_len >= 64:
        return 0.0
    target = 32.0
    return clamp01(1.0 - abs(byte_len - target) / target)


def anchor_proximity(anchor_index_in_window: int, window_len: int) -> float:
    if window_len <= 1:
        return 1.0
    center = (window_len - 1) / 2.0
    dist = abs(anchor_index_in_window - center)
    return clamp01(1.0 - dist / center)


def compute_score(
    *,
    uniqueness: float,
    presence: float,
    specificity: float,
    length_reg: float,
    anchor_prox: float,
) -> float:
    return (
        0.35 * uniqueness
        + 0.25 * presence
        + 0.20 * specificity
        + 0.10 * length_reg
        + 0.10 * anchor_prox
    )


def compute_confidence(
    *,
    num_versions: int,
    max_drift_rva: int,
    had_resync_warning: bool,
    had_alignment_ambiguity: bool,
) -> float:
    # Conservative, deterministic heuristic derived from spec inputs.
    c = 0.55
    if num_versions >= 1:
        c += 0.10
    if num_versions >= 2:
        c += 0.05
    if num_versions >= 3:
        c += 0.05

    # Drift penalty: beyond 0x1000 bytes starts to reduce confidence noticeably.
    drift_pen = min(0.30, (abs(max_drift_rva) / 4096.0) * 0.30)
    c -= drift_pen

    if had_resync_warning:
        c -= 0.05
    if had_alignment_ambiguity:
        c -= 0.15

    return clamp01(c)

