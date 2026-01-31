from __future__ import annotations

from dataclasses import dataclass

from iced_x86 import FlowControl, OpKind, Register

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


def _is_stack_register(reg: Register) -> bool:
    """Check if register is stack-related (RSP, RBP, ESP, EBP)."""
    return reg in {
        Register.RSP, Register.ESP,
        Register.RBP, Register.EBP,
    }


def _get_immediate_info(insn) -> list[tuple[int, int]]:
    """
    Get immediate offset and size for instruction.
    Returns list of (offset, size) tuples for all immediates.
    """
    results = []
    
    # Check each operand for immediates
    for op_idx in range(insn.op_count):
        op_kind = insn.op_kind(op_idx)
        
        # Determine size and calculate offset based on operand kind
        if op_kind == OpKind.IMMEDIATE8:
            size = 1
        elif op_kind == OpKind.IMMEDIATE8_2ND:
            size = 1
        elif op_kind == OpKind.IMMEDIATE8TO16:
            size = 1
        elif op_kind == OpKind.IMMEDIATE8TO32:
            size = 1
        elif op_kind == OpKind.IMMEDIATE8TO64:
            size = 1
        elif op_kind == OpKind.IMMEDIATE16:
            size = 2
        elif op_kind == OpKind.IMMEDIATE32:
            size = 4
        elif op_kind == OpKind.IMMEDIATE32TO64:
            size = 4
        elif op_kind == OpKind.IMMEDIATE64:
            size = 8
        elif op_kind in {OpKind.NEAR_BRANCH16, OpKind.FAR_BRANCH16}:
            size = 2
        elif op_kind in {OpKind.NEAR_BRANCH32, OpKind.FAR_BRANCH32}:
            size = 4
        elif op_kind == OpKind.NEAR_BRANCH64:
            size = 4  # rel32 in 64-bit mode
        else:
            continue
            
        # Calculate offset: instruction length minus immediate size minus any following immediates
        # For simplicity, assume immediate is at the end for most instructions
        offset = insn.len - size
        for existing_off, existing_size in results:
            if existing_off >= offset:
                offset -= existing_size
        
        results.append((offset, size))
    
    return results


def normalize_instruction(di: DecodedInsn, *, profile: str) -> AoBPattern:
    """
    Instruction-aware normalization with multiple profile strategies.

    Profiles:
    - minimal: Only branch/call offsets (maximum uniqueness)
    - default: Branch offsets + all memory displacements (balanced)
    - balanced: Default + RIP-relative globals (between default and aggressive)
    - aggressive: Everything including immediates (maximum stability)
    - stack-only: Only stack-related offsets ([rsp/rbp+X])
    - global-only: Only RIP-relative addressing
    - memory-heavy: All memory displacements including struct offsets
    - strict: Only absolute minimum (branches only)
    """
    raw = di.raw
    mask = bytearray(b"\x01" * len(raw))

    insn = di.insn

    # Profile-specific wildcarding logic
    wildcard_branches = profile in {"minimal", "default", "strict", "balanced", "aggressive", "stack-only", "global-only", "memory-heavy"}
    wildcard_rip_relative = profile in {"default", "balanced", "aggressive", "global-only", "memory-heavy"}
    wildcard_stack_disps = profile in {"default", "balanced", "aggressive", "stack-only", "memory-heavy"}
    wildcard_other_disps = profile in {"default", "balanced", "aggressive", "memory-heavy"}
    wildcard_immediates = profile in {"aggressive"}

    # Relative branch immediates (call/jmp/jcc)
    if wildcard_branches and _is_relative_branch(insn.flow_control):
        for imm_off, imm_size in _get_immediate_info(insn):
            if imm_off + imm_size <= len(mask):
                for i in range(imm_off, imm_off + imm_size):
                    mask[i] = 0

    # Displacements (RIP-relative and [reg+disp] / [reg+index*scale+disp])
    memory_displ_size = insn.memory_displ_size
    if memory_displ_size > 0:
        # For x86-64, RIP-relative always uses disp32 (4 bytes), even though the address is 64-bit
        # Calculate displacement offset: it comes after opcode, prefixes, ModRM, and optionally SIB
        # For RIP-relative: the displacement is typically 4 bytes in the encoding
        # For other memory operands: can be 1, 2, or 4 bytes
        
        # Estimate encoded displacement size based on operand
        if insn.is_ip_rel_memory_operand:
            # RIP-relative always uses disp32 in x86-64
            encoded_disp_size = 4
        else:
            # For other memory operands, displacement can be 0, 1, 2, or 4 bytes
            # We need to check the actual encoding
            # If memory_displ_size is set, we have a displacement
            # Typical sizes: disp8 (1), disp16 (2), disp32 (4)
            # For 64-bit mode, most often disp8 or disp32
            encoded_disp_size = min(memory_displ_size, 4)
            if encoded_disp_size == 3:
                encoded_disp_size = 4  # No 3-byte displacements
            elif encoded_disp_size > 4:
                encoded_disp_size = 4  # Max disp32 in encoding
        
        # Calculate offset: displacement comes before any immediates
        imm_total = sum(size for _, size in _get_immediate_info(insn))
        disp_off = insn.len - encoded_disp_size - imm_total
        
        if disp_off >= 0 and disp_off + encoded_disp_size <= len(mask):
            # RIP-relative addressing (global addresses)
            if insn.is_ip_rel_memory_operand:
                if wildcard_rip_relative:
                    for i in range(disp_off, disp_off + encoded_disp_size):
                        mask[i] = 0
            else:
                # Memory operands with base/index registers
                base = insn.memory_base
                index = insn.memory_index
                if base != Register.NONE or index != Register.NONE:
                    # Check if this is stack-related
                    is_stack = _is_stack_register(base) or _is_stack_register(index)
                    if is_stack and wildcard_stack_disps:
                        for i in range(disp_off, disp_off + encoded_disp_size):
                            mask[i] = 0
                    elif not is_stack and wildcard_other_disps:
                        for i in range(disp_off, disp_off + encoded_disp_size):
                            mask[i] = 0

    # Immediate constants (aggressive profile only, and not for branches which are already handled)
    if wildcard_immediates and not _is_relative_branch(insn.flow_control):
        for imm_off, imm_size in _get_immediate_info(insn):
            if imm_off + imm_size <= len(mask):
                for i in range(imm_off, imm_off + imm_size):
                    mask[i] = 0

    return AoBPattern(bytes_=raw, mask=bytes(mask))


def normalize_context(insns: tuple[DecodedInsn, ...], *, profile: str) -> tuple[NormalizedInsn, ...]:
    return tuple(NormalizedInsn(decoded=di, pattern=normalize_instruction(di, profile=profile)) for di in insns)

