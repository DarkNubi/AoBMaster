from __future__ import annotations

from aobmaster.pe import PEFile

from .conftest import write_pe


def test_pe_mapping_roundtrip(tmp_path):
    text = b"\x90" * 64  # NOP sled
    p = write_pe(tmp_path, "t.exe", text=text)

    pe = PEFile(p)
    assert pe.info.image_base == 0x140000000
    assert pe.info.entry_point_rva == 0x1000
    sec = pe.section_by_name(".text")
    assert sec is not None
    assert sec.raw_ptr == 0x200
    assert sec.virtual_address == 0x1000

    rva = 0x1000 + 10
    fo = pe.rva_to_fo(rva)
    assert fo == 0x200 + 10
    assert pe.fo_to_rva(fo) == rva
    assert pe.rva_to_va(rva) == pe.info.image_base + rva
