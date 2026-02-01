"""
Integration layer: Convert v1.x candidate format to v2 SignatureIR.

This module bridges the gap between existing v1.x code and new v2 IR format.
"""

from __future__ import annotations

from typing import Any

from .disasm import DecodedInsn
from .signature_ir import (
    InstructionIR,
    SignatureConstraint,
    SignatureIR,
    WildcardReason,
)


def build_wildcard_reasons(
    insn: DecodedInsn,
    mask: bytes,
    profile: str,
) -> tuple[WildcardReason, ...]:
    """
    Infer wildcard reasons from instruction and mask.

    This is a heuristic reconstruction since v1.x doesn't track reasons.
    v2 native code should record reasons during normalization.
    """
    reasons: list[WildcardReason] = []

    # Find wildcard byte ranges
    wildcard_positions: list[int] = []
    for i, m in enumerate(mask):
        if m == 0x00:
            wildcard_positions.append(i)

    if not wildcard_positions:
        return tuple(reasons)

    # Group consecutive wildcards
    groups: list[list[int]] = []
    current_group: list[int] = [wildcard_positions[0]]

    for pos in wildcard_positions[1:]:
        if pos == current_group[-1] + 1:
            current_group.append(pos)
        else:
            groups.append(current_group)
            current_group = [pos]
    groups.append(current_group)

    # Infer reason for each group based on instruction string
    insn_str = str(insn.insn).lower()

    for group in groups:
        # Heuristic: identify operand type based on instruction pattern
        if any(x in insn_str for x in ["call", "jmp", "jz", "jnz", "je", "jne"]):
            operand_type = "branch"
            reason = f"Branch offset wildcarded (profile={profile})"
            rule = f"{profile}:branch_offsets"
        elif "[rip+" in insn_str or "[rip-" in insn_str:
            operand_type = "rip_relative"
            reason = f"RIP-relative displacement wildcarded (profile={profile})"
            rule = f"{profile}:rip_relative"
        elif "[rsp+" in insn_str or "[rbp+" in insn_str or "[rsp-" in insn_str or "[rbp-" in insn_str:
            operand_type = "stack_offset"
            reason = f"Stack offset wildcarded (profile={profile})"
            rule = f"{profile}:stack_offsets"
        elif "[" in insn_str and "+" in insn_str:
            operand_type = "displacement"
            reason = f"Memory displacement wildcarded (profile={profile})"
            rule = f"{profile}:memory_displacements"
        else:
            operand_type = "immediate"
            reason = f"Immediate value wildcarded (profile={profile})"
            rule = f"{profile}:immediates"

        reasons.append(
            WildcardReason(
                positions=tuple(group),
                operand_type=operand_type,
                reason=reason,
                profile_rule=rule,
            )
        )

    return tuple(reasons)


def convert_candidate_to_ir(
    insns: list[DecodedInsn],
    pattern_bytes: bytes,
    pattern_mask: bytes,
    pattern_string: str,
    anchor_fo: int,
    anchor_rva: int,
    profile: str,
    section_name: str,
) -> SignatureIR:
    """
    Convert v1.x candidate data to v2 SignatureIR format.

    Args:
        insns: Decoded instructions in the window
        pattern_bytes: Pattern with wildcards as 0x00
        pattern_mask: Mask (0xFF = fixed, 0x00 = wildcard)
        pattern_string: CE-style pattern string
        anchor_fo: Anchor file offset
        anchor_rva: Anchor RVA
        profile: Wildcard profile used
        section_name: Section containing anchor

    Returns:
        SignatureIR with full metadata
    """
    # Build InstructionIR for each instruction
    instruction_irs: list[InstructionIR] = []
    byte_offset = 0
    anchor_insn_index = 0

    for i, insn in enumerate(insns):
        insn_len = insn.size
        insn_mask = pattern_mask[byte_offset:byte_offset + insn_len]
        insn_pattern = pattern_bytes[byte_offset:byte_offset + insn_len]

        # Track which instruction contains anchor
        if insn.fo <= anchor_fo < insn.fo + insn_len:
            anchor_insn_index = i

        # Build wildcard reasons
        wildcards = build_wildcard_reasons(insn, insn_mask, profile)

        instruction_irs.append(
            InstructionIR(
                offset=insn.fo,
                rva=anchor_rva + (insn.fo - anchor_fo),
                asm=str(insn.insn),
                bytes_raw=insn.raw,
                bytes_pattern=insn_pattern,
                mask=insn_mask,
                wildcards=wildcards,
            )
        )

        byte_offset += insn_len

    # Build constraints
    constraints: list[SignatureConstraint] = [
        SignatureConstraint(
            constraint_type="section",
            description=f"Anchor must be in {section_name} section",
            validation_logic=f"verify anchor RVA maps to section '{section_name}'",
        ),
        SignatureConstraint(
            constraint_type="alignment",
            description="Anchor must be at instruction boundary",
            validation_logic="decode instruction at anchor offset; verify anchor offset == instruction start",
        ),
    ]

    # Add no-relocation constraint if in .text section
    if section_name == ".text":
        constraints.append(
            SignatureConstraint(
                constraint_type="no_relocation",
                description="No relocation entries within pattern bytes",
                validation_logic="check PE relocation table for entries in [anchor, anchor+pattern_len]",
            )
        )

    return SignatureIR(
        pattern_bytes=pattern_bytes,
        pattern_mask=pattern_mask,
        pattern_string=pattern_string,
        instructions=tuple(instruction_irs),
        anchor_offset=anchor_fo,
        anchor_rva=anchor_rva,
        anchor_instruction_index=anchor_insn_index,
        constraints=tuple(constraints),
    )


def format_explain_output(trace_events: list[Any], signature_ir: SignatureIR | None = None) -> list[str]:
    """
    Format trace events and signature IR for --explain mode.

    Args:
        trace_events: List of TraceEvent objects or serialized event dicts
        signature_ir: Optional SignatureIR to explain

    Returns:
        List of formatted lines for text output
    """
    lines: list[str] = []

    lines.append("=" * 80)
    lines.append("AOBMASTER v2 EXPLAINABILITY OUTPUT")
    lines.append("=" * 80)
    lines.append("")

    # Group events by phase. Accept either TraceEvent objects or dicts produced by TraceCollector.to_dict().
    phases: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for event in trace_events:
        if isinstance(event, dict):
            # Serialized event dict (from TraceCollector.to_dict()['events'])
            phase = event.get("phase", "unknown")
            description = event.get("description", "")
            details = event.get("details", {}) or {}
        else:
            # Event object
            phase = getattr(event, "phase", "unknown")
            description = getattr(event, "description", "")
            details = getattr(event, "details", {}) or {}

        if phase not in phases:
            phases[phase] = []
        phases[phase].append((description, details))

    # Output events by phase
    for phase, events in phases.items():
        lines.append(f"--- PHASE: {phase.upper()} ---")
        for description, details in events:
            lines.append(f"  • {description}")
            if details:
                # details may contain nested dicts or simple values
                for key, value in details.items():
                    if isinstance(value, dict):
                        lines.append(f"    {key}:")
                        for k2, v2 in value.items():
                            lines.append(f"      {k2}: {v2}")
                    else:
                        lines.append(f"    {key}: {value}")
        lines.append("")

    # Output signature IR details if provided
    if signature_ir:
        lines.append("--- SIGNATURE IR ---")
        lines.append(f"Pattern: {signature_ir.pattern_string}")
        lines.append(f"Length: {signature_ir.byte_length} bytes")
        lines.append(f"Wildcards: {signature_ir.wildcard_count} ({signature_ir.wildcard_ratio:.1%})")
        lines.append("")

        lines.append("Instructions:")
        for i, insn in enumerate(signature_ir.instructions):
            marker = "  ← ANCHOR" if i == signature_ir.anchor_instruction_index else ""
            lines.append(f"  {i+1}. {insn.asm}{marker}")
            lines.append(f"     Bytes: {insn.bytes_raw.hex(' ').upper()}")
            if insn.has_wildcards:
                lines.append(f"     Pattern: {insn.bytes_pattern.hex(' ').upper()}")
                lines.append(f"     Mask: {insn.mask.hex(' ').upper()}")
                for wc in insn.wildcards:
                    lines.append(f"       • Wildcarded positions {wc.positions}: {wc.reason}")
        lines.append("")

        lines.append("Constraints:")
        for constraint in signature_ir.constraints:
            lines.append(f"  • [{constraint.constraint_type}] {constraint.description}")
        lines.append("")

    lines.append("=" * 80)

    return lines
