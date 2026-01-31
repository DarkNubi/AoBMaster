from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .errors import AoBMasterError, ExitCode
from .info import run_info
from .scan import run_scan
from .smart import run_smart
from .synth import run_synth
from .db_commands import run_db
from .test_command import run_test
from .analyze_command import run_analyze


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
    
    synth.add_argument(
        "--explain",
        action="store_true",
        help="Enable explainability mode: output detailed trace of all decisions (v2 feature)."
    )

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
    
    # Database commands (v2 feature)
    db = sub.add_parser("db", help="Manage signature database (v2 feature).")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)
    
    # db init
    db_init = db_sub.add_parser("init", help="Initialize signature database.")
    db_init.add_argument("--db", type=Path, required=True, help="Database path (e.g., signatures.db).")
    
    # db save
    db_save = db_sub.add_parser("save", help="Save signature to database.")
    db_save.add_argument("--db", type=Path, required=True, help="Database path.")
    db_save.add_argument("--id", type=str, required=True, help="Signature ID.")
    db_save.add_argument("--name", type=str, required=True, help="Signature name.")
    db_save.add_argument("--pattern", type=str, required=True, help="AoB pattern.")
    db_save.add_argument("--anchor-rva", type=str, required=True, help="Anchor RVA (hex).")
    db_save.add_argument("--binary-hash", type=str, required=True, help="SHA256 hash of binary.")
    db_save.add_argument("--author", type=str, help="Author name.")
    db_save.add_argument("--version-range", type=str, help="Version range (e.g., 1.0-1.5).")
    
    # db list
    db_list = db_sub.add_parser("list", help="List signatures in database.")
    db_list.add_argument("--db", type=Path, required=True, help="Database path.")
    db_list.add_argument("--filter", type=str, help="Filter by name substring.")
    _add_common_output_args(db_list)
    
    # db query
    db_query = db_sub.add_parser("query", help="Query signature by ID.")
    db_query.add_argument("--db", type=Path, required=True, help="Database path.")
    db_query.add_argument("--id", type=str, required=True, help="Signature ID.")
    _add_common_output_args(db_query)
    
    # db export
    db_export = db_sub.add_parser("export", help="Export database to JSON.")
    db_export.add_argument("--db", type=Path, required=True, help="Database path.")
    db_export.add_argument("--output", type=Path, required=True, help="Output JSON file.")
    
    # db import
    db_import = db_sub.add_parser("import", help="Import signatures from JSON.")
    db_import.add_argument("--db", type=Path, required=True, help="Database path.")
    db_import.add_argument("--input", type=Path, required=True, help="Input JSON file.")
    
    # Test command (v2 feature - signature replay & regression testing)
    test = sub.add_parser("test", help="Test signatures against binary corpus (v2 feature).")
    test.add_argument("--db", type=Path, required=True, help="Database path.")
    test.add_argument("--signature-id", type=str, help="Test specific signature (default: all).")
    test.add_argument("--binary", type=Path, help="Test against single binary.")
    test.add_argument("--corpus", type=str, nargs="+", help="Test against corpus (glob patterns).")
    test.add_argument("--parallel", type=int, default=1, help="Parallel workers (default: 1).")
    test.add_argument("--record", action="store_true", help="Record results in database.")
    _add_common_output_args(test)
    
    # Analyze command (v2 feature - temporal analysis)
    analyze = sub.add_parser("analyze", help="Analyze signature stability using historical data (v2 feature).")
    analyze.add_argument("--db", type=Path, required=True, help="Database path.")
    analyze.add_argument("--signature-id", type=str, help="Analyze specific signature (default: all).")
    _add_common_output_args(analyze)

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
        if args.cmd == "db":
            return run_db(args)
        if args.cmd == "test":
            return run_test(args)
        if args.cmd == "analyze":
            return run_analyze(args)
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

