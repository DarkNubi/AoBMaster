from __future__ import annotations

from dataclasses import dataclass

from .errors import AoBMasterWarning
from .matcher import AoBPattern
from .normalize import NormalizedInsn


@dataclass(frozen=True)
class Candidate:
    window_start: int  # index into context list
    window_len: int
    anchor_index: int  # index into window
    pattern: AoBPattern
    total_bytes: int
    wildcard_ratio: float
    rejected: bool
    reject_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "window_start": self.window_start,
            "window_len": self.window_len,
            "anchor_index": self.anchor_index,
            "aob": self.pattern.to_ce_string(),
            "byte_len": self.total_bytes,
            "wildcard_ratio": round(self.wildcard_ratio, 6),
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
        }


def _concat_patterns(parts: list[AoBPattern]) -> AoBPattern:
    b = bytearray()
    m = bytearray()
    for p in parts:
        b.extend(p.bytes_)
        m.extend(p.mask)
    return AoBPattern(bytes_=bytes(b), mask=bytes(m))


def calculate_pattern_similarity(pat1: AoBPattern, pat2: AoBPattern) -> float:
    """
    Calculate similarity between two patterns (0.0 = completely different, 1.0 = identical).
    Compares byte-by-byte, treating wildcards as partial matches.
    """
    len1, len2 = pat1.length, pat2.length
    max_len = max(len1, len2)
    if max_len == 0:
        return 1.0

    # Compare up to the shorter length
    min_len = min(len1, len2)
    matches = 0.0

    for i in range(min_len):
        b1, m1 = pat1.bytes_[i], pat1.mask[i]
        b2, m2 = pat2.bytes_[i], pat2.mask[i]
        
        # Both wildcards: partial match
        if m1 == 0 and m2 == 0:
            matches += 0.5
        # Both fixed and same byte: full match
        elif m1 != 0 and m2 != 0 and b1 == b2:
            matches += 1.0
        # One wildcard, one fixed: partial match
        elif (m1 == 0 and m2 != 0) or (m1 != 0 and m2 == 0):
            matches += 0.3
        # Both fixed but different: no match
        # else: matches += 0

    return matches / max_len


def deduplicate_candidates(candidates: list[Candidate], *, threshold: float = 0.75) -> list[Candidate]:
    """
    Deduplicate candidates based on pattern similarity.
    Keep patterns that are less than `threshold` similar (default: 75%).
    This means patterns must be >25% different to be kept.
    """
    if not candidates:
        return []

    unique = [candidates[0]]

    for candidate in candidates[1:]:
        is_unique = True
        for existing in unique:
            similarity = calculate_pattern_similarity(candidate.pattern, existing.pattern)
            if similarity >= threshold:  # If 75% or more similar, skip
                is_unique = False
                break
        if is_unique:
            unique.append(candidate)

    return unique


def generate_candidates(
    ctx: tuple[NormalizedInsn, ...],
    *,
    anchor_ctx_index: int,
    min_insns: int,
    max_insns: int,
) -> tuple[list[Candidate], tuple[AoBMasterWarning, ...]]:
    warnings: list[AoBMasterWarning] = []

    if min_insns < 1 or max_insns < 1 or min_insns > max_insns:
        raise ValueError("invalid min/max insns")

    out: list[Candidate] = []
    n_ctx = len(ctx)

    for win_len in range(min_insns, max_insns + 1):
        for start in range(0, n_ctx - win_len + 1):
            end = start + win_len
            if not (start <= anchor_ctx_index < end):
                continue
            anchor_in_win = anchor_ctx_index - start
            pats = [ctx[i].pattern for i in range(start, end)]
            pat = _concat_patterns(pats)

            reject_reason: str | None = None
            rejected = False

            if pat.length > 64:
                rejected = True
                reject_reason = "byte_len_gt_64"

            wildcard_ratio = pat.wildcard_ratio
            if not rejected and wildcard_ratio > 0.45:
                rejected = True
                reject_reason = "wildcard_ratio_gt_45pct"

            if not rejected and (pat.mask[0] == 0):
                rejected = True
                reject_reason = "empty_fixed_prefix"

            out.append(
                Candidate(
                    window_start=start,
                    window_len=win_len,
                    anchor_index=anchor_in_win,
                    pattern=pat,
                    total_bytes=pat.length,
                    wildcard_ratio=wildcard_ratio,
                    rejected=rejected,
                    reject_reason=reject_reason,
                )
            )

    # Deterministic ordering before scoring: longer windows first, then earlier start.
    out.sort(key=lambda c: (-c.window_len, c.window_start, c.pattern.to_ce_string()))
    return out, tuple(warnings)

