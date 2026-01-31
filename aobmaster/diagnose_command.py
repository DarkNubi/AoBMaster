"""
Diagnose command for signature families and lineage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .database import SignatureDatabase
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text


def run_diagnose(args: Any) -> int:
    """
    Diagnose signature family lineage and evolution.
    
    Usage:
        aobmaster diagnose --db signatures.db --signature sig_abc
    """
    db_path = Path(args.db)
    
    if not db_path.exists():
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "database_not_found",
            f"Database not found: {db_path}",
            {"path": str(db_path)},
        )
    
    signature_id = args.signature_id
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Get signature family
    family = db.get_signature_family(signature_id)
    
    if not family:
        db.close()
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "signature_not_found",
            f"Signature not found: {signature_id}",
        )
    
    # Find the target signature in family
    target_sig = None
    for sig in family:
        if sig.id == signature_id:
            target_sig = sig
            break
    
    if not target_sig:
        db.close()
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "signature_not_found",
            f"Signature not found in family: {signature_id}",
        )
    
    # Get test results for family members
    family_with_tests = []
    for sig in family:
        test_results = db.get_test_results(sig.id)
        family_with_tests.append({
            "signature": sig.to_dict(),
            "test_count": len(test_results),
            "pass_rate": sum(1 for r in test_results if r["passed"]) / len(test_results) if test_results else 0.0,
        })
    
    db.close()
    
    # Output
    if args.format == "json":
        emit_json({
            "ok": True,
            "target_signature_id": signature_id,
            "family_size": len(family),
            "family": family_with_tests,
        })
    else:
        lines = [
            f"Signature Family Diagnosis",
            f"Target: {target_sig.name} ({target_sig.id})",
            f"Family Size: {len(family)} signature(s)",
            "",
        ]
        
        # Show lineage
        lines.append("Lineage:")
        # Calculate proper depth for each signature
        depth_map = {}
        for sig_item in family_with_tests:
            sig = sig_item["signature"]
            # Calculate depth by walking parent chain
            depth = 0
            current_id = sig["id"]
            seen = set()
            while True:
                if current_id in seen:
                    break  # Circular reference protection
                seen.add(current_id)
                # Find parent in family
                parent_id = sig.get("parent_id")
                if not parent_id:
                    break
                depth += 1
                # Find parent sig
                parent_found = False
                for p_item in family_with_tests:
                    if p_item["signature"]["id"] == parent_id:
                        current_id = parent_id
                        parent_found = True
                        break
                if not parent_found:
                    break
            depth_map[sig["id"]] = depth
        
        for i, item in enumerate(family_with_tests):
            sig = item["signature"]
            marker = "  ← TARGET" if sig["id"] == signature_id else ""
            deprecated_mark = " [DEPRECATED]" if sig.get("deprecated") else ""
            
            depth = depth_map.get(sig["id"], 0)
            indent = "  " * depth
            lines.append(f"{indent}{i+1}. {sig['name']} ({sig['id']}){deprecated_mark}{marker}")
            lines.append(f"{indent}   Pattern: {sig['pattern']}")
            lines.append(f"{indent}   Version Range: {sig.get('version_range', 'unknown')}")
            
            if item["test_count"] > 0:
                lines.append(f"{indent}   Tests: {item['test_count']}, Pass Rate: {item['pass_rate']:.1%}")
            
            if sig.get("deprecated"):
                lines.append(f"{indent}   Deprecation: {sig.get('deprecation_reason', 'No reason given')}")
            
            if sig.get("parent_id"):
                lines.append(f"{indent}   Parent: {sig['parent_id']}")
            
            lines.append("")
        
        emit_text(lines)
    
    return 0
