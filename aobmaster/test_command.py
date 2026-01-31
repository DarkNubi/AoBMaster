"""
Signature replay and regression testing for AoBMaster v2.

Tests signatures against binary corpora, records results in database.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from .database import SignatureDatabase
from .errors import AoBMasterError, ExitCode
from .matcher import AoBPattern, parse_ce_aob, scan_bytes
from .output import emit_json, emit_text
from .pe import PEFile


def _compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def _test_signature_against_binary(
    signature_id: str,
    pattern_string: str,
    binary_path: Path,
    expected_unique: bool = True,
) -> dict[str, Any]:
    """
    Test a single signature against a binary.
    
    Returns test result dict.
    """
    try:
        # Parse pattern
        pattern = parse_ce_aob(pattern_string)
        
        # Load binary
        pe = PEFile(binary_path)
        
        # Scan all executable sections
        all_matches = []
        for section in pe.executable_sections():
            section_data = pe.read_fo(section.raw_ptr, section.raw_size)
            matches = scan_bytes(section_data, pattern)
            # Convert section-relative offsets to file offsets
            all_matches.extend([section.raw_ptr + m for m in matches])
        
        # Determine pass/fail
        match_count = len(all_matches)
        
        if expected_unique:
            passed = (match_count == 1)
            if not passed:
                if match_count == 0:
                    failure_reason = "Pattern not found in binary"
                else:
                    failure_reason = f"Pattern matched {match_count} times (expected 1)"
            else:
                failure_reason = None
        else:
            passed = (match_count > 0)
            failure_reason = "Pattern not found in binary" if not passed else None
        
        return {
            "signature_id": signature_id,
            "binary_path": str(binary_path),
            "binary_hash": _compute_sha256(binary_path),
            "passed": passed,
            "match_count": match_count,
            "match_offsets": [hex(m) for m in all_matches[:10]],  # Limit to 10
            "failure_reason": failure_reason,
        }
    
    except Exception as e:
        return {
            "signature_id": signature_id,
            "binary_path": str(binary_path),
            "binary_hash": _compute_sha256(binary_path) if binary_path.exists() else "unknown",
            "passed": False,
            "match_count": 0,
            "match_offsets": [],
            "failure_reason": f"Test error: {str(e)}",
        }


def run_test(args: Any) -> int:
    """
    Test signatures against binary corpus.
    
    Usage:
        aobmaster test --db signatures.db --corpus binaries/*.exe
        aobmaster test --db signatures.db --signature sig_abc --binary game.exe
    """
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
    
    # Get signatures to test
    if hasattr(args, 'signature_id') and args.signature_id:
        # Test specific signature
        sig = db.get_signature(args.signature_id)
        if not sig:
            db.close()
            raise AoBMasterError(
                ExitCode.INVALID_ARGS,
                "signature_not_found",
                f"Signature not found: {args.signature_id}",
            )
        signatures = [sig]
    else:
        # Test all signatures
        signatures = db.list_signatures()
    
    if not signatures:
        db.close()
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "no_signatures",
            "No signatures found in database",
        )
    
    # Get binaries to test against
    if hasattr(args, 'binary') and args.binary:
        binaries = [Path(args.binary)]
    elif hasattr(args, 'corpus') and args.corpus:
        # Expand glob patterns and explicit paths
        corpus_patterns = args.corpus if isinstance(args.corpus, list) else [args.corpus]
        binaries = []
        for pattern in corpus_patterns:
            p = Path(pattern)
            # Check if it's an explicit file path
            if p.exists() and p.is_file():
                binaries.append(p)
            else:
                # Try as glob pattern
                # For absolute paths, use parent directory
                if p.is_absolute():
                    parent = p.parent
                    glob_pattern = p.name
                    matches = list(parent.glob(glob_pattern))
                else:
                    matches = list(Path().glob(pattern))
                binaries.extend(matches)
        # Deduplicate while preserving order (Python 3.7+)
        binaries = list(dict.fromkeys(binaries))
    else:
        db.close()
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "no_binaries",
            "No binaries specified (use --binary or --corpus)",
        )
    
    if not binaries:
        db.close()
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "no_binaries_found",
            "No binaries found matching pattern",
        )
    
    # Run tests (parallel if --parallel enabled)
    test_results = []
    max_workers = getattr(args, 'parallel', 1)
    allow_multiple = getattr(args, 'allow_multiple', False)
    
    if max_workers > 1:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for sig in signatures:
                for binary in binaries:
                    future = executor.submit(
                        _test_signature_against_binary,
                        sig.id,
                        sig.pattern,
                        binary,
                        expected_unique=not allow_multiple,
                    )
                    futures.append(future)
            
            for future in as_completed(futures):
                test_results.append(future.result())
    else:
        # Sequential execution
        for sig in signatures:
            for binary in binaries:
                result = _test_signature_against_binary(
                    sig.id,
                    sig.pattern,
                    binary,
                    expected_unique=not allow_multiple,
                )
                test_results.append(result)
    
    # Store results in database if --record flag is set
    if getattr(args, 'record', False):
        for result in test_results:
            db.record_test_result(
                signature_id=result["signature_id"],
                binary_path=result["binary_path"],
                binary_hash=result["binary_hash"],
                passed=result["passed"],
                failure_reason=result.get("failure_reason"),
            )
    
    db.close()
    
    # Output results
    passed_count = sum(1 for r in test_results if r["passed"])
    failed_count = len(test_results) - passed_count
    
    if args.format == "json":
        emit_json({
            "ok": True,
            "summary": {
                "total_tests": len(test_results),
                "total": len(test_results),  # Backward compat
                "passed": passed_count,
                "failed": failed_count,
            },
            "results": test_results,
        })
    else:
        lines = [
            f"Test Summary:",
            f"  Total: {len(test_results)}",
            f"  Passed: {passed_count}",
            f"  Failed: {failed_count}",
            "",
        ]
        
        if failed_count > 0:
            lines.append("Failures:")
            for result in test_results:
                if not result["passed"]:
                    lines.append(f"  ✗ {result['signature_id']} @ {Path(result['binary_path']).name}")
                    lines.append(f"    Reason: {result['failure_reason']}")
        
        emit_text(lines)
    
    # Always return 0 for successful execution
    # (Test failures are reported in output, not via exit code)
    return 0
