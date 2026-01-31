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

