from __future__ import annotations

from pathlib import Path
from typing import Any

from iced_x86 import Code, Decoder, DecoderOptions

from . import __version__
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text
from .pe import PEFile, parse_hex_int
from .util import sha256_file


def _resolve_target(pe: PEFile, args: Any) -> tuple[int, int, int]:
    if args.to_rva:
        rva = parse_hex_int(args.to_rva)
    elif args.to_fo:
        fo = parse_hex_int(args.to_fo)
        rva = pe.fo_to_rva(fo)
    elif args.to_va:
        va = parse_hex_int(args.to_va)
        rva = pe.va_to_rva(va)
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "Missing destination")
    fo = pe.rva_to_fo(rva)
    va = pe.rva_to_va(rva)
    return rva, fo, va


def _decode_section(pe: PEFile, base_fo: int, buf: bytes) -> list[tuple[int, int, object]]:
    bitness = 64 if pe.info.is_64bit else 32
    decoder = Decoder(bitness, buf, ip=pe.rva_to_va(pe.fo_to_rva(base_fo)), options=DecoderOptions.NONE)
    out: list[tuple[int, int, object]] = []
    cur_fo = base_fo
    while decoder.can_decode:
        insn = decoder.decode()
        if insn.code == Code.INVALID:
            break
        out.append((cur_fo, insn.len, insn))
        cur_fo += insn.len
        if cur_fo - base_fo >= len(buf):
            break
    return out


def _matches_type(insn, ref_type: str) -> bool:
    if ref_type == "all":
        return insn.is_call_near or insn.is_jmp_short_or_near or insn.is_jcc_short_or_near
    if ref_type == "branch":
        return insn.is_jmp_short_or_near or insn.is_jcc_short_or_near
    if ref_type == "jmp":
        return insn.is_jmp_short_or_near
    if ref_type == "call,jmp":
        return insn.is_call_near or insn.is_jmp_short_or_near
    return insn.is_call_near


def run_xref(args: Any) -> int:
    pe = PEFile(args.file)
    target_rva, target_fo, target_va = _resolve_target(pe, args)

    if args.scan_range == "section":
        if not args.section:
            raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", "--section is required when --scan-range=section")
        sec = pe.section_by_name(args.section)
        if not sec:
            raise AoBMasterError(
                ExitCode.INVALID_ARGS,
                "invalid_args",
                "Section not found",
                {"section": args.section},
            )
        sections = [sec]
    elif args.scan_range == "module":
        sections = list(pe.executable_sections())
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown scan-range: {args.scan_range}")

    refs: list[dict[str, Any]] = []
    for sec in sections:
        buf = pe.read_fo(sec.raw_ptr, sec.raw_size)
        decoded = _decode_section(pe, sec.raw_ptr, buf)
        for fo, size, insn in decoded:
            if not _matches_type(insn, args.type):
                continue
            target = insn.near_branch_target
            if target == 0:
                continue
            if target != target_va:
                continue
            from_rva = pe.fo_to_rva(fo)
            from_va = pe.rva_to_va(from_rva)
            refs.append(
                {
                    "from_fo": hex(fo),
                    "from_rva": hex(from_rva),
                    "from_va": hex(from_va),
                    "instruction": str(insn),
                    "to_rva": hex(target_rva),
                    "to_va": hex(target_va),
                }
            )

    refs.sort(key=lambda r: int(r["from_rva"], 16))
    refs = refs[: max(1, args.limit)]

    out_obj = {
        "ok": True,
        "version": __version__,
        "file": str(args.file),
        "destination": {"rva": hex(target_rva), "fo": hex(target_fo), "va": hex(target_va)},
        "refs": refs,
        "scan_range": args.scan_range,
        "hashes": {str(args.file): {"sha256": sha256_file(Path(args.file))}},
        "warnings": [],
        "errors": [],
    }

    if args.format == "json":
        emit_json(out_obj)
    elif args.format == "text":
        lines = []
        lines.append(f"AoBMaster xref v{__version__}")
        lines.append(f"File: {args.file}")
        lines.append(f"Target RVA: {hex(target_rva)}")
        lines.append("")
        if not refs:
            lines.append("No references found.")
        else:
            for i, ref in enumerate(refs, 1):
                lines.append(
                    f"{i}. {ref['instruction']} @ RVA {ref['from_rva']} (FO {ref['from_fo']})"
                )
        emit_text(lines)
    elif args.format == "ce":
        emit_text([ref["instruction"] for ref in refs] or ["; AoBMaster xref: no refs"])
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown format: {args.format}")

    return int(ExitCode.SUCCESS)
