from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .errors import AoBMasterError, ExitCode
from .info import run_info
from .scan import run_scan
from .smart import run_smart
from .synth import run_synth


def _add_common_output_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--format",
        choices=["json", "text", "ce"],
        default="json",
        help="Output format (default: json).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aobmaster", add_help=True)
    parser.add_argument("--version", action="version", version=f"aobmaster {__version__}")

    sub = parser.add_subparsers(dest="cmd", required=True)

    synth = sub.add_parser("synth", help="Synthesize stable AoB signatures from an anchor.")
    synth.add_argument("--base", type=Path, required=True, help="Base PE x64 binary (.exe/.dll).")
    anchor = synth.add_mutually_exclusive_group(required=True)
    anchor.add_argument("--anchor-rva", type=str, help="Anchor RVA (hex).")
    anchor.add_argument("--anchor-fo", type=str, help="Anchor file offset (hex).")
    anchor.add_argument("--anchor-va", type=str, help="Anchor virtual address (hex).")
    synth.add_argument("--versions", type=Path, nargs="*", default=[], help="Additional version binaries.")
    synth.add_argument(
        "--anchor-shift",
        type=int,
        default=0,
        help="Try anchor ±N instructions to find stable regions (0=off, N=shift range). Example: 2 tries ±2 instructions."
    )

    synth.add_argument("--align", choices=["anchor-rva", "bytespan"], default="bytespan")
    synth.add_argument("--seed-bytes", type=int, default=32)
    synth.add_argument("--seed-scan", choices=["section", "module"], default="section")
    synth.add_argument("--seed-allow-multi", choices=["true", "false"], default="false")

    synth.add_argument("--context-before", type=int, default=8)
    synth.add_argument("--context-after", type=int, default=8)
    synth.add_argument("--max-context-insns", type=int, default=32)
    synth.add_argument(
        "--context-variations",
        choices=["off", "on"],
        default="off",
        help="Generate candidates with multiple context window sizes (off=single context, on=multiple variations)."
    )

    synth.add_argument(
        "--profile",
        choices=["minimal", "default", "strict", "balanced", "aggressive", "stack-only", "global-only", "memory-heavy"],
        default="default",
        help="Wildcard profile: minimal (branches only), default (balanced), strict (minimal), "
             "balanced (default+globals), aggressive (all), stack-only (stack offsets), "
             "global-only (RIP-relative), memory-heavy (all memory)."
    )

    synth.add_argument("--min-insns", type=int, default=6)
    synth.add_argument("--max-insns", type=int, default=14)

    synth.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top-ranked candidates to include in text/CE output (default: 5). JSON includes all."
    )

    synth.add_argument("--scan-range", choices=["section", "module"], default=None)

    synth.add_argument("--require-unique", choices=["true", "false"], default="true")
    synth.add_argument("--require-present-all", choices=["true", "false"], default="true")

    _add_common_output_args(synth)

    # Smart analyze command
    smart = sub.add_parser("smart", help="Analyze binary region and suggest stable anchor points.")
    smart.add_argument("--base", type=Path, required=True, help="PE x64 binary to analyze.")
    smart.add_argument("--rva", type=str, required=True, help="RVA to start analysis (hex).")
    smart.add_argument("--insns", type=int, default=50, help="Number of instructions to analyze (default: 50).")
    smart.add_argument("--top-n", type=int, default=5, help="Number of top anchor suggestions (default: 5).")
    _add_common_output_args(smart)

    scan = sub.add_parser("scan", help="Scan a PE file for a CE-style AoB pattern.")
    scan.add_argument("--file", type=Path, required=True, help="PE x64 binary to scan.")
    scan.add_argument("--aob", type=str, required=True, help='AoB pattern, e.g. "48 8B ?? ??".')
    scan.add_argument("--scan-range", choices=["section", "module"], default="module")
    scan.add_argument("--section", type=str, default=None, help="Section name if scan-range=section.")
    _add_common_output_args(scan)

    info = sub.add_parser("info", help="Display basic PE x64 metadata.")
    info.add_argument("--file", type=Path, required=True, help="PE x64 binary.")
    _add_common_output_args(info)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.cmd == "synth":
            return run_synth(args)
        if args.cmd == "smart":
            return run_smart(args)
        if args.cmd == "scan":
            return run_scan(args)
        if args.cmd == "info":
            return run_info(args)
        raise AoBMasterError(ExitCode.INVALID_ARGS, "invalid_args", f"Unknown command: {args.cmd}")
    except AoBMasterError as e:
        # Best-effort: return machine-readable JSON if requested.
        if getattr(args, "format", "json") == "json":
            from .output import emit_json

            emit_json(
                {
                    "ok": False,
                    "version": __version__,
                    "errors": [e.to_dict()],
                    "warnings": [],
                }
            )
        else:
            print(f"ERROR[{int(e.code)}] {e.kind}: {e.message}")
        return int(e.code)
    except Exception as e:  # noqa: BLE001
        if getattr(args, "format", "json") == "json":
            from .output import emit_json

            emit_json(
                {
                    "ok": False,
                    "version": __version__,
                    "errors": [{"kind": "internal_error", "message": str(e)}],
                    "warnings": [],
                }
            )
        else:
            print(f"ERROR[{int(ExitCode.INTERNAL_ERROR)}] internal_error: {e}")
        return int(ExitCode.INTERNAL_ERROR)

