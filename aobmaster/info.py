from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text
from .pe import PEFile
from .util import sha256_file


def run_info(args: Any) -> int:
    pe = PEFile(args.file)
    info = pe.info

    obj = {
        "ok": True,
        "version": __version__,
        "file": str(args.file),
        "hashes": {str(args.file): {"sha256": sha256_file(Path(args.file))}},
        "pe": {
            "image_base": hex(info.image_base),
            "entry_point_rva": hex(info.entry_point_rva),
            "entry_point_va": hex(info.image_base + info.entry_point_rva),
            "size_of_image": hex(info.size_of_image),
            "sections": [
                {
                    "name": s.name,
                    "rva": hex(s.virtual_address),
                    "vsize": hex(s.virtual_size),
                    "fo": hex(s.raw_ptr),
                    "raw_size": hex(s.raw_size),
                    "executable": bool(s.is_executable),
                    "characteristics": hex(s.characteristics),
                }
                for s in info.sections
            ],
        },
        "warnings": [],
        "errors": [],
    }

    if args.format == "json":
        emit_json(obj)
    elif args.format == "text":
        lines: list[str] = []
        lines.append(f"AoBMaster v{__version__} info")
        lines.append(f"File: {args.file}")
        lines.append(f"ImageBase: {obj['pe']['image_base']}")
        lines.append(f"EntryPoint: RVA {obj['pe']['entry_point_rva']} VA {obj['pe']['entry_point_va']}")
        lines.append("Sections:")
        for s in obj["pe"]["sections"]:
            lines.append(
                f"  {s['name']:8} RVA {s['rva']:>10} FO {s['fo']:>10} RAW {s['raw_size']:>8} EXEC={s['executable']}"
            )
        emit_text(lines)
    elif args.format == "ce":
        # CE format isn't defined for info; output a minimal comment block.
        emit_text([f"; {args.file}", f"; ImageBase {obj['pe']['image_base']}"])
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown format: {args.format}")

    return int(ExitCode.SUCCESS)

