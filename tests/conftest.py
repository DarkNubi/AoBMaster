from __future__ import annotations

import struct
from pathlib import Path


def _align(n: int, a: int) -> int:
    return (n + (a - 1)) & ~(a - 1)


def build_minimal_pe64(*, text: bytes, image_base: int = 0x140000000, section_rva: int = 0x1000) -> bytes:
    """
    Minimal PE32+ (x64) with a single .text section.

    This is purpose-built for tests and only populates fields required by `aobmaster.pe`.
    """
    file_align = 0x200
    sect_align = 0x1000

    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)

    pe_sig = b"PE\x00\x00"
    num_sections = 1
    opt_size = 0xF0
    coff = struct.pack("<HHIIIHH", 0x8664, num_sections, 0, 0, 0, opt_size, 0x2022)

    raw_size = _align(len(text), file_align)
    size_of_headers = file_align
    size_of_image = _align(section_rva + _align(len(text), sect_align), sect_align)

    # Optional header (PE32+)
    opt = bytearray(opt_size)
    struct.pack_into("<H", opt, 0, 0x20B)  # Magic
    struct.pack_into("<I", opt, 16, section_rva)  # AddressOfEntryPoint
    struct.pack_into("<I", opt, 20, section_rva)  # BaseOfCode
    struct.pack_into("<Q", opt, 24, image_base)  # ImageBase
    struct.pack_into("<I", opt, 32, sect_align)  # SectionAlignment
    struct.pack_into("<I", opt, 36, file_align)  # FileAlignment
    struct.pack_into("<I", opt, 56, size_of_image)  # SizeOfImage
    struct.pack_into("<I", opt, 60, size_of_headers)  # SizeOfHeaders
    struct.pack_into("<H", opt, 68, 3)  # Subsystem (CUI)
    struct.pack_into("<I", opt, 108, 16)  # NumberOfRvaAndSizes

    # Section header
    sec = bytearray(40)
    sec[0:8] = b".text\x00\x00\x00"
    struct.pack_into("<I", sec, 8, len(text))  # VirtualSize
    struct.pack_into("<I", sec, 12, section_rva)  # VirtualAddress
    struct.pack_into("<I", sec, 16, raw_size)  # SizeOfRawData
    struct.pack_into("<I", sec, 20, size_of_headers)  # PointerToRawData
    struct.pack_into("<I", sec, 36, 0x60000020)  # Characteristics (RX code)

    headers = dos + pe_sig + coff + opt + sec
    if len(headers) > size_of_headers:
        raise AssertionError("headers too large for chosen file alignment")
    headers = headers + b"\x00" * (size_of_headers - len(headers))

    body = text + b"\x00" * (raw_size - len(text))
    return bytes(headers + body)


def write_pe(tmp_path: Path, name: str, *, text: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(build_minimal_pe64(text=text))
    return p


import pytest


@pytest.fixture
def sample_binary(tmp_path):
    """Create a sample PE binary for testing."""
    # Code with recognizable patterns that won't match elsewhere
    code = (
        b"\x48\x89\x5C\x24\x08"          # mov [rsp+8], rbx
        b"\x48\x89\x74\x24\x10"          # mov [rsp+10], rsi
        b"\x48\x8B\x05\x12\x34\x56\x78"  # mov rax, [rip+0x78563412]
        b"\x85\xC0"                      # test eax, eax
        b"\x74\x05"                      # jz +5
        b"\xB8\x01\x00\x00\x00"          # mov eax, 1
        b"\xC3"                          # ret
        # Add unique padding that won't match patterns
        b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09"
        b"\x0A\x0B\x0C\x0D\x0E\x0F\x10\x11\x12\x13"
        b"\x14\x15\x16\x17\x18\x19\x1A\x1B\x1C\x1D"
        + bytes(range(0x1E, 0x100))       # More unique padding
    )
    return write_pe(tmp_path, "sample.exe", text=code)

