from __future__ import annotations

from aobmaster.disasm import decode_anchor_context
from aobmaster.normalize import normalize_instruction
from aobmaster.pe import PEFile

from .conftest import write_pe


def test_wildcard_rip_relative_disp(tmp_path):
    # mov rax, [rip+0x44332211]  => 48 8B 05 11 22 33 44
    text = bytes.fromhex("48 8B 05 11 22 33 44 C3")
    p = write_pe(tmp_path, "t.exe", text=text)
    pe = PEFile(p)
    sec = pe.section_by_name(".text")
    assert sec is not None
    anchor_fo = sec.raw_ptr  # at instruction start

    ctx = decode_anchor_context(pe, sec, anchor_fo=anchor_fo, context_before=0, context_after=0, max_context_insns=4)
    pat = normalize_instruction(ctx.insns[0], profile="default")
    # Wildcard the disp32 bytes (offset 3..6)
    assert pat.mask[3:7] == b"\x00\x00\x00\x00"


def test_wildcard_relative_branch_imm(tmp_path):
    # call rel32 => E8 11 22 33 44
    text = bytes.fromhex("E8 11 22 33 44 C3")
    p = write_pe(tmp_path, "t.exe", text=text)
    pe = PEFile(p)
    sec = pe.section_by_name(".text")
    assert sec is not None
    anchor_fo = sec.raw_ptr

    ctx = decode_anchor_context(pe, sec, anchor_fo=anchor_fo, context_before=0, context_after=0, max_context_insns=4)
    pat = normalize_instruction(ctx.insns[0], profile="default")
    assert pat.mask[1:5] == b"\x00\x00\x00\x00"

