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
    for cand in range(start_fo, min(start_fo + 16, anchor_fo + 1)):
        avail = section.raw_ptr + section.raw_size - cand
        if avail <= 0:
            continue
        insns = _decode_stream(pe, cand, max_bytes=min(max_bytes, avail), max_insns=max_context_insns + 8)
        if not insns:
            continue
        anchor_idx = next((i for i, di in enumerate(insns) if di.fo == anchor_fo), None)
        if anchor_idx is None:
            continue
        before_ok = min(context_before, anchor_idx)
        after_ok = min(context_after, len(insns) - anchor_idx - 1)
        score = before_ok * 1000 + after_ok * 10 - (anchor_fo - cand)
        if best is None or score > best[0]:
            best = (score, insns, anchor_idx)

    if best is None:
        raise AoBMasterError(
            ExitCode.DISASM_FAILURE,
            "disasm_failed",
            "Failed to decode instruction context around anchor",
            {"anchor_fo": hex(anchor_fo)},
        )

    _, insns, anchor_idx = best
    start_idx = max(0, anchor_idx - context_before)
    end_idx = min(len(insns), anchor_idx + context_after + 1)
    sliced = insns[start_idx:end_idx]
    new_anchor_idx = anchor_idx - start_idx
    return AnchorContext(insns=tuple(sliced), anchor_index=new_anchor_idx, warnings=tuple(warnings))

