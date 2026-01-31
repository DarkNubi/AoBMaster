from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .errors import AoBMasterError, ExitCode
from .matcher import parse_ce_aob, scan_ranges
from .output import emit_json, emit_text
from .pe import PEFile
from .util import sha256_file


def run_scan(args: Any) -> int:
    pe = PEFile(args.file)
    pat = parse_ce_aob(args.aob)

    if args.scan_range == "module":
        ranges: list[tuple[int, bytes]] = []
        for s in pe.executable_sections():
            ranges.append((s.raw_ptr, pe.read_fo(s.raw_ptr, s.raw_size)))
    elif args.scan_range == "section":
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
        ranges = [(sec.raw_ptr, pe.read_fo(sec.raw_ptr, sec.raw_size))]
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown scan-range: {args.scan_range}")

    hits = scan_ranges(ranges, pat)

    obj = {
        "ok": True,
        "version": __version__,
        "file": str(args.file),
        "hashes": {str(args.file): {"sha256": sha256_file(Path(args.file))}},
        "pattern": {"aob": pat.to_ce_string(), "byte_len": pat.length, "wildcard_ratio": round(pat.wildcard_ratio, 6)},
        "scan_range": args.scan_range,
        "hits": {"count": len(hits), "hits_fo": [hex(x) for x in hits]},
        "warnings": [],
        "errors": [],
    }

    if args.format == "json":
        emit_json(obj)
    elif args.format == "text":
        lines = [
            f"AoBMaster v{__version__} scan",
            f"File: {args.file}",
            f"Pattern: {pat.to_ce_string()}",
            f"Hits: {len(hits)}",
        ]
        for h in hits[:50]:
            lines.append(f"  - FO {hex(h)}")
        if len(hits) > 50:
            lines.append(f"  ... ({len(hits) - 50} more)")
        emit_text(lines)
    elif args.format == "ce":
        # CE format isn't defined for scan; output the AoB string.
        emit_text([pat.to_ce_string()])
    else:
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown format: {args.format}")

    return int(ExitCode.SUCCESS)

