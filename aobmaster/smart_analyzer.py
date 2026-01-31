"""Smart anchor scoring: Automatically identify stable instruction regions."""
from __future__ import annotations

from dataclasses import dataclass

from iced_x86 import FlowControl, OpKind

from .disasm import DecodedInsn


@dataclass(frozen=True)
class AnchorScore:
    """Score for an instruction as a potential anchor."""
    fo: int
    rva: int
    score: float
    reason: str
    details: dict[str, any]


def score_instruction_stability(di: DecodedInsn) -> float:
    """
    Score an instruction for stability (0.0-1.0).
    Higher scores indicate more stable instructions suitable as anchors.
    
    Scoring criteria:
    - Penalize branches, calls (volatile targets)
    - Penalize instructions with immediate values (may change)
    - Favor ALU operations, stack ops, data movement
    - Favor instructions with fixed patterns
    """
    insn = di.insn
    score = 0.5  # Base score
    
    # Flow control penalty
    flow = insn.flow_control
    if flow in {FlowControl.CALL, FlowControl.INDIRECT_CALL}:
        score -= 0.3  # Calls are volatile
    elif flow in {FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH}:
        score -= 0.2  # Branches are volatile
    elif flow in {FlowControl.INDIRECT_BRANCH, FlowControl.RETURN, FlowControl.INTERRUPT}:
        score -= 0.4  # Indirect/returns very volatile
    
    # Operand type bonuses/penalties
    has_immediate = False
    has_memory = False
    has_registers_only = True
    
    for op_idx in range(insn.op_count):
        op_kind = insn.op_kind(op_idx)
        
        # Check for immediates (may change between versions)
        if op_kind in {
            OpKind.IMMEDIATE8, OpKind.IMMEDIATE16, OpKind.IMMEDIATE32, 
            OpKind.IMMEDIATE64, OpKind.IMMEDIATE8TO16, OpKind.IMMEDIATE8TO32,
            OpKind.IMMEDIATE8TO64, OpKind.IMMEDIATE32TO64,
        }:
            has_immediate = True
            has_registers_only = False
        
        # Check for memory operands
        elif op_kind == OpKind.MEMORY:
            has_memory = True
            has_registers_only = False
            
            # RIP-relative is less stable (global addresses)
            if insn.is_ip_rel_memory_operand:
                score -= 0.1
    
    # Immediate penalty (values may be tuned)
    if has_immediate:
        score -= 0.15
    
    # Memory operand (mixed - can be stable or not)
    if has_memory:
        score += 0.05  # Slight bonus for having structure
    
    # Register-only operations are often stable
    if has_registers_only and insn.op_count > 0:
        score += 0.2
    
    # Instruction length bonus (longer = more specific)
    if insn.len >= 5:
        score += 0.1
    elif insn.len >= 3:
        score += 0.05
    
    # Common stable patterns
    # MOV, TEST, CMP, LEA, ADD, SUB, XOR, AND, OR
    mnemonic_str = str(insn.mnemonic).lower() if hasattr(insn.mnemonic, 'name') else str(insn.mnemonic).lower()
    stable_mnemonics = {'mov', 'test', 'cmp', 'lea', 'add', 'sub', 'xor', 'and', 'or', 'push', 'pop'}
    if any(stable in mnemonic_str for stable in stable_mnemonics):
        score += 0.15
    
    # Clamp score to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def find_stable_anchors(
    insns: tuple[DecodedInsn, ...],
    *,
    top_n: int = 5,
) -> list[AnchorScore]:
    """
    Find the most stable instructions in a sequence.
    
    Args:
        insns: Decoded instructions
        top_n: Number of top candidates to return
    
    Returns:
        List of AnchorScore objects, sorted by score (descending)
    """
    scores = []
    
    for idx, di in enumerate(insns):
        stability = score_instruction_stability(di)
        
        # Generate reason
        insn = di.insn
        mnemonic = str(insn.mnemonic).lower() if hasattr(insn.mnemonic, 'name') else str(insn.mnemonic).lower()
        
        reason_parts = []
        if stability >= 0.7:
            reason_parts.append("High stability")
        elif stability >= 0.5:
            reason_parts.append("Moderate stability")
        else:
            reason_parts.append("Low stability")
        
        reason_parts.append(f"mnemonic={mnemonic}")
        reason_parts.append(f"len={insn.len}")
        
        scores.append(
            AnchorScore(
                fo=di.fo,
                rva=di.fo,  # Will need PE to convert; using FO for now
                score=stability,
                reason=", ".join(reason_parts),
                details={
                    "instruction_index": idx,
                    "mnemonic": mnemonic,
                    "length": insn.len,
                    "op_count": insn.op_count,
                },
            )
        )
    
    # Sort by score descending
    scores.sort(key=lambda x: (-x.score, x.fo))
    
    return scores[:top_n]
