from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import AoBMasterError, ExitCode


@dataclass(frozen=True)
class AoBPattern:
    bytes_: bytes
    mask: bytes  # 1=fixed, 0=wildcard

    def to_ce_string(self) -> str:
        parts: list[str] = []
        for b, m in zip(self.bytes_, self.mask, strict=True):
            parts.append(f"{b:02X}" if m else "??")
        return " ".join(parts)

    @property
    def length(self) -> int:
        return len(self.bytes_)

    @property
    def wildcard_ratio(self) -> float:
        if not self.bytes_:
            return 1.0
        wild = sum(1 for m in self.mask if not m)
        return wild / len(self.bytes_)


def parse_ce_aob(s: str) -> AoBPattern:
    tokens = [t for t in s.strip().split() if t]
    if not tokens:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_aob", "Empty AoB pattern")

    out_b = bytearray()
    out_m = bytearray()
    for t in tokens:
        tt = t.strip()
        if tt in {"?", "??"}:
            out_b.append(0)
            out_m.append(0)
            continue
        if len(tt) != 2:
            raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_aob", f"Invalid token: {t!r}")
        try:
            out_b.append(int(tt, 16))
        except ValueError as e:  # noqa: PERF203
            raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_aob", f"Invalid hex byte: {t!r}") from e
        out_m.append(1)

    if out_m and out_m[0] == 0:
        # Spec hard rejection: empty fixed-byte prefix.
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_aob", "AoB may not start with a wildcard")

    return AoBPattern(bytes_=bytes(out_b), mask=bytes(out_m))


def scan_bytes(buf: bytes, pat: AoBPattern) -> list[int]:
    if pat.length == 0:
        return []

    fixed_positions = [i for i, m in enumerate(pat.mask) if m]
    if not fixed_positions:
        return list(range(0, len(buf) - pat.length + 1))

    first_fixed = fixed_positions[0]
    first_byte = pat.bytes_[first_fixed]

    hits: list[int] = []
    start = 0
    limit = len(buf) - pat.length
    while start <= limit:
        idx = buf.find(bytes([first_byte]), start + first_fixed)
        if idx < 0:
            break
        cand = idx - first_fixed
        if cand < start:
            start = idx + 1
            continue

        ok = True
        for pos in fixed_positions:
            if buf[cand + pos] != pat.bytes_[pos]:
                ok = False
                break
        if ok:
            hits.append(cand)
        start = cand + 1
    return hits


def scan_ranges(ranges: Iterable[tuple[int, bytes]], pat: AoBPattern) -> list[int]:
    out: list[int] = []
    for base_fo, buf in ranges:
        for off in scan_bytes(buf, pat):
            out.append(base_fo + off)
    return out

