"""
Database command handlers for AoBMaster v2.

Handles db init, save, query, list, export, import commands.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .database import SignatureDatabase, SignatureRecord
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text
from .pe import parse_hex_int


def run_db_init(args: Any) -> int:
    """Initialize signature database."""
    db_path = Path(args.db)
    
    if db_path.exists():
        # Fail if database already exists (safety check)
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "database_exists",
            f"Database already exists: {db_path}",
            {"path": str(db_path)},
        )
    
    db = SignatureDatabase(db_path)
    db.init_database()
    db.close()
    
    print(f"Database initialized: {db_path}")
    return 0


def run_db_save(args: Any) -> int:
    """Save signature to database."""
    db_path = Path(args.db)
    
    if not db_path.exists():
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "database_not_found",
            f"Database not found: {db_path}. Run 'db init' first.",
            {"path": str(db_path)},
        )
    
    # Parse anchor RVA
    anchor_rva = parse_hex_int(args.anchor_rva)
    
    # Create signature record
    signature = SignatureRecord(
        id=args.id,
        name=args.name,
        pattern=args.pattern,
        anchor_rva=anchor_rva,
        binary_hash=args.binary_hash,
        created_at=datetime.utcnow().isoformat(),
        author=getattr(args, 'author', None),
        version_range=getattr(args, 'version_range', None),
        metadata={},  # Can be extended later
    )
    
    db = SignatureDatabase(db_path)
    db.init_database()  # Ensure schema exists
    db.save_signature(signature)
    db.close()
    
    print(f"Signature saved: {args.id}")
    return 0


def run_db_list(args: Any) -> int:
    """List signatures in database."""
    db_path = Path(args.db)
    
    if not db_path.exists():
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "database_not_found",
            f"Database not found: {db_path}",
            {"path": str(db_path)},
        )
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    name_filter = getattr(args, 'filter', None)
    signatures = db.list_signatures(name_filter=name_filter)
    db.close()
    
    if args.format == "json":
        emit_json({
            "ok": True,
            "count": len(signatures),
            "signatures": [sig.to_dict() for sig in signatures],
        })
    else:
        lines = [f"Found {len(signatures)} signature(s):"]
        for sig in signatures:
            lines.append(f"  • {sig.id}: {sig.name}")
            lines.append(f"    Pattern: {sig.pattern}")
            lines.append(f"    Anchor RVA: {hex(sig.anchor_rva)}")
            lines.append(f"    Created: {sig.created_at}")
        emit_text(lines)
    
    return 0


def run_db_query(args: Any) -> int:
    """Query signature by ID."""
    db_path = Path(args.db)
    
    if not db_path.exists():
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "database_not_found",
            f"Database not found: {db_path}",
            {"path": str(db_path)},
        )
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    signature = db.get_signature(args.id)
    
    if not signature:
        db.close()
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "signature_not_found",
            f"Signature not found: {args.id}",
            {"id": args.id},
        )
    
    # Get test results
    test_results = db.get_test_results(args.id)
    db.close()
    
    if args.format == "json":
        emit_json({
            "ok": True,
            "signature": signature.to_dict(),
            "test_results": test_results,
        })
    else:
        lines = [
            f"Signature: {signature.name}",
            f"ID: {signature.id}",
            f"Pattern: {signature.pattern}",
            f"Anchor RVA: {hex(signature.anchor_rva)}",
            f"Binary Hash: {signature.binary_hash}",
            f"Created: {signature.created_at}",
        ]
        if signature.author:
            lines.append(f"Author: {signature.author}")
        if signature.version_range:
            lines.append(f"Version Range: {signature.version_range}")
        
        if test_results:
            lines.append(f"\nTest Results ({len(test_results)}):")
            for result in test_results[:5]:  # Show last 5
                status = "✓ PASS" if result["passed"] else "✗ FAIL"
                lines.append(f"  {result['test_date']}: {status}")
                if not result["passed"]:
                    lines.append(f"    Reason: {result['failure_reason']}")
        
        emit_text(lines)
    
    return 0


def run_db_export(args: Any) -> int:
    """Export database to JSON."""
    db_path = Path(args.db)
    output_path = Path(args.output)
    
    if not db_path.exists():
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "database_not_found",
            f"Database not found: {db_path}",
            {"path": str(db_path)},
        )
    
    db = SignatureDatabase(db_path)
    db.init_database()
    db.export_to_json(output_path)
    db.close()
    
    print(f"Database exported to: {output_path}")
    return 0


def run_db_import(args: Any) -> int:
    """Import signatures from JSON."""
    db_path = Path(args.db)
    input_path = Path(args.input)
    
    if not input_path.exists():
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "file_not_found",
            f"Input file not found: {input_path}",
            {"path": str(input_path)},
        )
    
    db = SignatureDatabase(db_path)
    db.init_database()
    count = db.import_from_json(input_path)
    db.close()
    
    print(f"Imported {count} signature(s) from: {input_path}")
    return 0


def run_db(args: Any) -> int:
    """Route to appropriate database subcommand."""
    if args.db_cmd == "init":
        return run_db_init(args)
    elif args.db_cmd == "save":
        return run_db_save(args)
    elif args.db_cmd == "list":
        return run_db_list(args)
    elif args.db_cmd == "query":
        return run_db_query(args)
    elif args.db_cmd == "export":
        return run_db_export(args)
    elif args.db_cmd == "import":
        return run_db_import(args)
    else:
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "invalid_args",
            f"Unknown db subcommand: {args.db_cmd}",
        )
