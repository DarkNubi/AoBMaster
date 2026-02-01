from __future__ import annotations

from dataclasses import dataclass

from iced_x86 import Code, Decoder, DecoderOptions, Instruction

from .errors import AoBMasterError, AoBMasterWarning, ExitCode
from .pe import PEFile, Section


@dataclass(frozen=True)
class DecodedInsn:
    fo: int
    ip: int
    size: int
    insn: Instruction
    raw: bytes


@dataclass(frozen=True)
class AnchorContext:
    insns: tuple[DecodedInsn, ...]
    anchor_index: int
    warnings: tuple[AoBMasterWarning, ...]


def _decode_stream(pe: PEFile, start_fo: int, *, max_bytes: int, max_insns: int) -> list[DecodedInsn]:
    buf = pe.read_fo(start_fo, max_bytes)
    start_rva = pe.fo_to_rva(start_fo)
    ip = pe.rva_to_va(start_rva)

    # Use appropriate bitness based on PE file type
    bitness = 64 if pe.info.is_64bit else 32
    decoder = Decoder(bitness, buf, ip=ip, options=DecoderOptions.NONE)
    out: list[DecodedInsn] = []
    cur_fo = start_fo
    for _ in range(max_insns):
        insn = decoder.decode()
        if insn.code == Code.INVALID:
            break
        raw = pe.read_fo(cur_fo, insn.len)
        out.append(DecodedInsn(fo=cur_fo, ip=insn.ip, size=insn.len, insn=insn, raw=raw))
        cur_fo += insn.len
        if cur_fo >= start_fo + max_bytes:
            break
    return out


def _decode_stream_diag(
    pe: PEFile,
    start_fo: int,
    *,
    max_bytes: int,
    max_insns: int,
) -> tuple[list[DecodedInsn], int | None]:
    """
    Like _decode_stream(), but also returns the first file offset where decoding
    hit an invalid instruction (if any).
    """
    buf = pe.read_fo(start_fo, max_bytes)
    start_rva = pe.fo_to_rva(start_fo)
    ip = pe.rva_to_va(start_rva)

    bitness = 64 if pe.info.is_64bit else 32
    decoder = Decoder(bitness, buf, ip=ip, options=DecoderOptions.NONE)

    out: list[DecodedInsn] = []
    cur_fo = start_fo
    invalid_fo: int | None = None

    for _ in range(max_insns):
        insn = decoder.decode()
        if insn.code == Code.INVALID:
            invalid_fo = cur_fo
            break
        raw = pe.read_fo(cur_fo, insn.len)
        out.append(DecodedInsn(fo=cur_fo, ip=insn.ip, size=insn.len, insn=insn, raw=raw))
        cur_fo += insn.len
        if cur_fo >= start_fo + max_bytes:
            break

    return out, invalid_fo


def resync_anchor_to_insn_start(pe: PEFile, section: Section, anchor_fo: int) -> tuple[int, AoBMasterWarning | None]:
    """
    Attempts instruction-boundary recovery:
    - Backtrack up to 15 bytes
    - If anchor isn't on a boundary, snap to the start of the instruction containing it
    """
    best_start: int | None = None

    floor_fo = max(section.raw_ptr, anchor_fo - 15)
    for start in range(anchor_fo, floor_fo - 1, -1):
        insns = _decode_stream(pe, start, max_bytes=min(64, section.raw_ptr + section.raw_size - start), max_insns=8)
        if not insns:
            continue
        for di in insns:
            begin = di.fo
            end = di.fo + di.size
            if begin == anchor_fo:
                return anchor_fo, None
            if begin < anchor_fo < end:
                if best_start is None or begin > best_start:
                    best_start = begin
    if best_start is None:
        raise AoBMasterError(
            ExitCode.DISASM_FAILURE,
            "anchor_resync_failed",
            "Could not resynchronize anchor to an instruction boundary",
            {"anchor_fo": hex(anchor_fo)},
        )

    return best_start, AoBMasterWarning(
        kind="anchor_resynced",
        message="Anchor was not instruction-aligned; resynchronized to instruction start",
        details={"original_anchor_fo": hex(anchor_fo), "resynced_anchor_fo": hex(best_start), "delta": anchor_fo - best_start},
    )


def decode_anchor_context(
    pe: PEFile,
    section: Section,
    *,
    anchor_fo: int,
    context_before: int,
    context_after: int,
    max_context_insns: int,
) -> AnchorContext:
    total_requested = context_before + 1 + context_after
    if max_context_insns < 1:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "--max-context-insns must be >= 1")
    if total_requested > max_context_insns:
        # Clamp "after" first, preserving "before" + anchor preference deterministically.
        context_after = max(0, max_context_insns - 1 - context_before)

    warnings: list[AoBMasterWarning] = []

    aligned_fo, w = resync_anchor_to_insn_start(pe, section, anchor_fo)
    if w:
        warnings.append(w)
    anchor_fo = aligned_fo

    # Decode a window that is guaranteed to include enough possible instruction starts.
    back_bytes = 15 * max_context_insns
    start_fo = max(section.raw_ptr, anchor_fo - back_bytes)
    max_bytes = min(section.raw_ptr + section.raw_size - start_fo, back_bytes + 15 * max_context_insns)

    best: tuple[int, list[DecodedInsn], int] | None = None  # (score, insns, anchor_index)

    # IMPORTANT: To land on the anchor instruction boundary in a variable-length
    # ISA, the decode start must be close to the anchor. Trying only offsets
    # near `start_fo` is unreliable and can miss valid boundaries.
    cand_start_lo = max(start_fo, anchor_fo - 15)
    cand_start_hi = anchor_fo

    attempts: list[dict[str, object]] = []
    for cand in range(cand_start_lo, cand_start_hi + 1):
        avail = section.raw_ptr + section.raw_size - cand
        if avail <= 0:
            attempts.append(
                {
                    "start_fo": hex(cand),
                    "decoded_insns": 0,
                    "reason": "start_out_of_section",
                }
            )
            continue
        used_max_bytes = min(max_bytes, avail)
        insns, invalid_fo = _decode_stream_diag(
            pe,
            cand,
            max_bytes=used_max_bytes,
            max_insns=max_context_insns + 8,
        )
        if not insns:
            attempts.append(
                {
                    "start_fo": hex(cand),
                    "decoded_insns": 0,
                    "max_bytes": used_max_bytes,
                    "invalid_fo": hex(invalid_fo) if invalid_fo is not None else None,
                    "reason": "no_instructions_decoded",
                }
            )
            continue
        anchor_idx = next((i for i, di in enumerate(insns) if di.fo == anchor_fo), None)
        if anchor_idx is None:
            last_end = insns[-1].fo + insns[-1].size
            attempts.append(
                {
                    "start_fo": hex(cand),
                    "decoded_insns": len(insns),
                    "decoded_span": {"first_fo": hex(insns[0].fo), "last_end_fo": hex(last_end)},
                    "max_bytes": used_max_bytes,
                    "invalid_fo": hex(invalid_fo) if invalid_fo is not None else None,
                    "reason": "anchor_not_reached",
                }
            )
            continue
        before_ok = min(context_before, anchor_idx)
        after_ok = min(context_after, len(insns) - anchor_idx - 1)
        score = before_ok * 1000 + after_ok * 10 - (anchor_fo - cand)
        attempts.append(
            {
                "start_fo": hex(cand),
                "decoded_insns": len(insns),
                "anchor_index": anchor_idx,
                "before_ok": before_ok,
                "after_ok": after_ok,
                "max_bytes": used_max_bytes,
                "invalid_fo": hex(invalid_fo) if invalid_fo is not None else None,
                "score": score,
                "reason": "ok",
            }
        )
        if best is None or score > best[0]:
            best = (score, insns, anchor_idx)

    if best is None:
        section_end = section.raw_ptr + section.raw_size
        anchor_bytes: str | None = None
        try:
            n = min(16, max(0, section_end - anchor_fo))
            if n:
                anchor_bytes = pe.read_fo(anchor_fo, n).hex(" ").upper()
        except Exception:
            anchor_bytes = None

        raise AoBMasterError(
            ExitCode.DISASM_FAILURE,
            "disasm_failed",
            "Failed to decode instruction context around anchor",
            {
                "anchor_fo": hex(anchor_fo),
                "section": {
                    "name": section.name,
                    "raw_ptr": hex(section.raw_ptr),
                    "raw_size": hex(section.raw_size),
                    "raw_end": hex(section_end),
                },
                "constraints": {
                    "context_before": context_before,
                    "context_after": context_after,
                    "max_context_insns": max_context_insns,
                },
                "decode_window": {"start_fo": hex(start_fo), "max_bytes": int(max_bytes)},
                "attempts": attempts,
                "anchor_bytes_hex": anchor_bytes,
                "suggestions": [
                    "Verify the anchor is in executable code (not data/padding) even if section is .text",
                    "Try --anchor-shift (e.g. 4) to search nearby instructions",
                    "Use `aobmaster smart` to get stable anchor suggestions near the target RVA",
                ],
            },
        )

    _, insns, anchor_idx = best
    start_idx = max(0, anchor_idx - context_before)
    end_idx = min(len(insns), anchor_idx + context_after + 1)
    sliced = insns[start_idx:end_idx]
    new_anchor_idx = anchor_idx - start_idx
    return AnchorContext(insns=tuple(sliced), anchor_index=new_anchor_idx, warnings=tuple(warnings))

