from __future__ import annotations

from dataclasses import dataclass

from iced_x86 import FlowControl, Register

from .disasm import DecodedInsn
from .matcher import AoBPattern


@dataclass(frozen=True)
class NormalizedInsn:
    decoded: DecodedInsn
    pattern: AoBPattern


def _is_relative_branch(flow: FlowControl) -> bool:
    return flow in {
        FlowControl.CALL,
        FlowControl.CONDITIONAL_BRANCH,
        FlowControl.UNCONDITIONAL_BRANCH,
    }


def normalize_instruction(di: DecodedInsn, *, profile: str) -> AoBPattern:
    """
    Instruction-aware normalization.

    Always wildcard:
    - RIP-relative displacements
    - Relative branch immediates (call/jmp/jcc)
    - Stack offsets ([rsp+X]) and general base/index displacements ([reg+X])

    Optional (aggressive):
    - Immediate constants
    """
    raw = di.raw
    mask = bytearray(b"\x01" * len(raw))

    insn = di.insn

    # Displacements (RIP-relative and [reg+disp] / [reg+index*scale+disp])
    disp_size = insn.displacement_size
    if disp_size:
        disp_off = insn.displacement_offset
        if disp_off is not None and disp_off + disp_size <= len(mask):
            # "Always wildcard" any displacement that participates in address calculation.
            # Includes RIP-relative and stack/base offsets.
            if insn.is_ip_rel_memory_operand:
                for i in range(disp_off, disp_off + disp_size):
                    mask[i] = 0
            else:
                base = insn.memory_base
                index = insn.memory_index
                if base != Register.NONE or index != Register.NONE:
                    for i in range(disp_off, disp_off + disp_size):
                        mask[i] = 0

    # Relative branch immediates
    if _is_relative_branch(insn.flow_control):
        imm_size = insn.immediate_size
        imm_off = insn.immediate_offset
        if imm_size and imm_off is not None and imm_off + imm_size <= len(mask):
            for i in range(imm_off, imm_off + imm_size):
                mask[i] = 0
        imm2_size = insn.immediate_size2
        imm2_off = insn.immediate_offset2
        if imm2_size and imm2_off is not None and imm2_off + imm2_size <= len(mask):
            for i in range(imm2_off, imm2_off + imm2_size):
                mask[i] = 0

    # Optional immediates (aggressive)
    if profile == "aggressive":
        imm_size = insn.immediate_size
        imm_off = insn.immediate_offset
        if imm_size and imm_off is not None and imm_off + imm_size <= len(mask):
            for i in range(imm_off, imm_off + imm_size):
                mask[i] = 0
        imm2_size = insn.immediate_size2
        imm2_off = insn.immediate_offset2
        if imm2_size and imm2_off is not None and imm2_off + imm2_size <= len(mask):
            for i in range(imm2_off, imm2_off + imm2_size):
                mask[i] = 0

    return AoBPattern(bytes_=raw, mask=bytes(mask))


def normalize_context(insns: tuple[DecodedInsn, ...], *, profile: str) -> tuple[NormalizedInsn, ...]:
    return tuple(NormalizedInsn(decoded=di, pattern=normalize_instruction(di, profile=profile)) for di in insns)

