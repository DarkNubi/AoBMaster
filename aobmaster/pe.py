from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import AoBMasterError, ExitCode


IMAGE_FILE_MACHINE_AMD64 = 0x8664
PE32_PLUS_MAGIC = 0x20B

IMAGE_SCN_MEM_EXECUTE = 0x20000000


@dataclass(frozen=True)
class Section:
    name: str
    virtual_address: int
    virtual_size: int
    raw_ptr: int
    raw_size: int
    characteristics: int

    def contains_rva(self, rva: int) -> bool:
        # Use virtual_size when available; fall back to raw_size.
        size = self.virtual_size if self.virtual_size else self.raw_size
        return self.virtual_address <= rva < self.virtual_address + size

    def contains_fo(self, fo: int) -> bool:
        return self.raw_ptr <= fo < self.raw_ptr + self.raw_size

    def rva_to_fo(self, rva: int) -> int:
        if not self.contains_rva(rva):
            raise ValueError("RVA not in section")
        return (rva - self.virtual_address) + self.raw_ptr

    def fo_to_rva(self, fo: int) -> int:
        if not self.contains_fo(fo):
            raise ValueError("FO not in section")
        return (fo - self.raw_ptr) + self.virtual_address

    @property
    def is_executable(self) -> bool:
        return (self.characteristics & IMAGE_SCN_MEM_EXECUTE) != 0


@dataclass(frozen=True)
class PEInfo:
    image_base: int
    entry_point_rva: int
    size_of_image: int
    sections: tuple[Section, ...]


class PEFile:
    def __init__(self, path: Path):
        self.path = path
        self._data = path.read_bytes()
        self.info = _parse_pe64(self._data, path=path)

    @property
    def data(self) -> bytes:
        return self._data

    def section_by_name(self, name: str) -> Section | None:
        for s in self.info.sections:
            if s.name == name:
                return s
        return None

    def section_containing_rva(self, rva: int) -> Section | None:
        for s in self.info.sections:
            if s.contains_rva(rva):
                return s
        return None

    def section_containing_fo(self, fo: int) -> Section | None:
        for s in self.info.sections:
            if s.contains_fo(fo):
                return s
        return None

    def rva_to_fo(self, rva: int) -> int:
        s = self.section_containing_rva(rva)
        if not s:
            raise AoBMasterError(
                ExitCode.ANCHOR_FAILURE,
                "anchor_out_of_range",
                "RVA not within any section",
                {"rva": hex(rva)},
            )
        return s.rva_to_fo(rva)

    def fo_to_rva(self, fo: int) -> int:
        s = self.section_containing_fo(fo)
        if not s:
            raise AoBMasterError(
                ExitCode.ANCHOR_FAILURE,
                "anchor_out_of_range",
                "File offset not within any section",
                {"fo": hex(fo)},
            )
        return s.fo_to_rva(fo)

    def va_to_rva(self, va: int) -> int:
        return va - self.info.image_base

    def rva_to_va(self, rva: int) -> int:
        return self.info.image_base + rva

    def read_fo(self, fo: int, size: int) -> bytes:
        if fo < 0 or fo + size > len(self._data):
            raise AoBMasterError(
                ExitCode.ANCHOR_FAILURE,
                "read_out_of_range",
                "Requested bytes out of range",
                {"fo": hex(fo), "size": size},
            )
        return self._data[fo : fo + size]

    def executable_sections(self) -> Iterable[Section]:
        return [s for s in self.info.sections if s.is_executable and s.raw_size > 0]


def parse_hex_int(s: str) -> int:
    s = s.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if not s:
        raise ValueError("empty hex")
    return int(s, 16)


def _read_u16(b: bytes, off: int) -> int:
    return struct.unpack_from("<H", b, off)[0]


def _read_u32(b: bytes, off: int) -> int:
    return struct.unpack_from("<I", b, off)[0]


def _read_u64(b: bytes, off: int) -> int:
    return struct.unpack_from("<Q", b, off)[0]


def _parse_pe64(data: bytes, *, path: Path) -> PEInfo:
    if len(data) < 0x100:
        raise AoBMasterError(ExitCode.ANCHOR_FAILURE, "invalid_pe", "File too small to be a PE", {"path": str(path)})

    if data[:2] != b"MZ":
        raise AoBMasterError(ExitCode.ANCHOR_FAILURE, "invalid_pe", "Missing MZ header", {"path": str(path)})

    e_lfanew = _read_u32(data, 0x3C)
    if e_lfanew <= 0 or e_lfanew + 4 + 20 > len(data):
        raise AoBMasterError(ExitCode.ANCHOR_FAILURE, "invalid_pe", "Invalid e_lfanew", {"path": str(path)})

    if data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        raise AoBMasterError(ExitCode.ANCHOR_FAILURE, "invalid_pe", "Missing PE signature", {"path": str(path)})

    coff = e_lfanew + 4
    machine = _read_u16(data, coff + 0)
    num_sections = _read_u16(data, coff + 2)
    size_opt = _read_u16(data, coff + 16)
    opt = coff + 20

    if machine != IMAGE_FILE_MACHINE_AMD64:
        raise AoBMasterError(
            ExitCode.ANCHOR_FAILURE,
            "unsupported_machine",
            "Only PE x64 (AMD64) is supported",
            {"machine": hex(machine)},
        )
    if opt + size_opt > len(data):
        raise AoBMasterError(ExitCode.ANCHOR_FAILURE, "invalid_pe", "Optional header out of range", {"path": str(path)})

    magic = _read_u16(data, opt + 0)
    if magic != PE32_PLUS_MAGIC:
        raise AoBMasterError(
            ExitCode.ANCHOR_FAILURE,
            "unsupported_pe",
            "Only PE32+ (x64) is supported",
            {"magic": hex(magic)},
        )

    entry_point_rva = _read_u32(data, opt + 16)
    image_base = _read_u64(data, opt + 24)
    size_of_image = _read_u32(data, opt + 56)

    sec_table = opt + size_opt
    sec_size = 40
    if sec_table + num_sections * sec_size > len(data):
        raise AoBMasterError(ExitCode.ANCHOR_FAILURE, "invalid_pe", "Section table out of range", {"path": str(path)})

    sections: list[Section] = []
    for i in range(num_sections):
        off = sec_table + i * sec_size
        name_raw = data[off : off + 8]
        name = name_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        virtual_size = _read_u32(data, off + 8)
        virtual_address = _read_u32(data, off + 12)
        raw_size = _read_u32(data, off + 16)
        raw_ptr = _read_u32(data, off + 20)
        characteristics = _read_u32(data, off + 36)
        sections.append(
            Section(
                name=name,
                virtual_address=virtual_address,
                virtual_size=virtual_size,
                raw_ptr=raw_ptr,
                raw_size=raw_size,
                characteristics=characteristics,
            )
        )

    return PEInfo(image_base=image_base, entry_point_rva=entry_point_rva, size_of_image=size_of_image, sections=tuple(sections))

