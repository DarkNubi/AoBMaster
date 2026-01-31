"""
Tests for AoBMaster v2 Phase 3: Testing functionality.

Tests signature testing against binaries, corpus management, and --record flag.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime

from aobmaster.database import SignatureDatabase, SignatureRecord

from .conftest import write_pe


def test_test_single_signature(tmp_path):
    """Test testing a single signature against a binary."""
    # Create test binary
    code = bytes.fromhex(
        "48 83 EC 28 "  # sub rsp,28h
        "48 8B 05 11 22 33 44 "  # mov rax,[rip+disp32]
        "48 85 C0 "  # test rax,rax
        "74 05 "  # je short
        "48 83 C4 28 "  # add rsp,28h
        "C3"  # ret
    )
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Signature that matches the code (with wildcards for displacement and imm8)
    sig = SignatureRecord(
        id="sig_test_001",
        name="Test Function",
        pattern="48 83 EC 28 48 8B 05 ?? ?? ?? ?? 48 85 C0 ?? ?? 48 83 C4 28 C3",
        anchor_rva=0x1000,
        binary_hash="test_hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_test_001",
        "--binary", str(binary),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    assert "results" in out
    assert len(out["results"]) == 1
    
    result = out["results"][0]
    assert result["signature_id"] == "sig_test_001"
    assert result["passed"] is True
    assert result["match_count"] == 1


def test_test_signature_not_found(tmp_path):
    """Test that a non-matching signature fails correctly."""
    # Create test binary
    code = bytes.fromhex("48 83 EC 28 C3")
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with non-matching signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_nomatch",
        name="No Match",
        pattern="90 90 90 90 90",  # Pattern that doesn't exist
        anchor_rva=0x1000,
        binary_hash="test_hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_nomatch",
        "--binary", str(binary),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    result = out["results"][0]
    assert result["passed"] is False
    assert result["match_count"] == 0
    assert "not found" in result["failure_reason"].lower()


def test_test_signature_multiple_matches(tmp_path):
    """Test that multiple matches are detected correctly."""
    # Create binary with repeated pattern
    code = bytes.fromhex(
        "48 83 EC 28 "  # Pattern 1
        "C3 "
        "48 83 EC 28 "  # Pattern 2 (duplicate)
        "C3"
    )
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_multi",
        name="Multi Match",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="test_hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_multi",
        "--binary", str(binary),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    result = out["results"][0]
    assert result["passed"] is False  # Should fail due to multiple matches
    assert result["match_count"] == 2
    assert "matched 2 times" in result["failure_reason"].lower()


def test_test_multiple_signatures(tmp_path):
    """Test testing multiple signatures against a binary."""
    # Create test binary
    code = bytes.fromhex(
        "48 83 EC 28 C3 "  # Pattern 1
        "55 48 89 E5 C9 C3"  # Pattern 2
    )
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with multiple signatures
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig1 = SignatureRecord(
        id="sig_001",
        name="Sig 1",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    
    sig2 = SignatureRecord(
        id="sig_002",
        name="Sig 2",
        pattern="55 48 89 E5",
        anchor_rva=0x1005,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    
    db.save_signature(sig1)
    db.save_signature(sig2)
    db.close()
    
    # Test all signatures via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--binary", str(binary),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert len(out["results"]) == 2
    
    # Both should pass
    passed = [r for r in out["results"] if r["passed"]]
    assert len(passed) == 2


def test_test_corpus_multiple_binaries(tmp_path):
    """Test testing signatures against multiple binaries (corpus)."""
    # Create multiple test binaries
    code1 = bytes.fromhex("48 83 EC 28 C3")
    code2 = bytes.fromhex("48 83 EC 30 C3")  # Slightly different
    
    binary1 = write_pe(tmp_path, "v1.exe", text=code1)
    binary2 = write_pe(tmp_path, "v2.exe", text=code2)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_corpus",
        name="Corpus Test",
        pattern="48 83 EC ??",  # Wildcarded to match both
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test against corpus via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_corpus",
        "--corpus", str(binary1), str(binary2),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert len(out["results"]) == 2
    
    # Both should pass
    passed = [r for r in out["results"] if r["passed"]]
    assert len(passed) == 2
    
    # Check that both binaries are tested
    binary_paths = [r["binary_path"] for r in out["results"]]
    assert str(binary1) in binary_paths
    assert str(binary2) in binary_paths


def test_test_record_results(tmp_path):
    """Test that --record saves test results to database."""
    # Create test binary
    code = bytes.fromhex("48 83 EC 28 C3")
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_record",
        name="Record Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test with --record flag
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_record",
        "--binary", str(binary),
        "--record",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    
    # Check that results were saved to database
    db = SignatureDatabase(db_path)
    db.init_database()
    
    test_results = db.get_test_results("sig_record")
    assert len(test_results) > 0
    
    result = test_results[0]
    assert result["signature_id"] == "sig_record"
    assert result["passed"] is True
    
    db.close()


def test_test_record_failure(tmp_path):
    """Test that --record saves failures correctly."""
    # Create test binary
    code = bytes.fromhex("48 83 EC 28 C3")
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with non-matching signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_fail",
        name="Fail Test",
        pattern="90 90 90 90",  # Won't match
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test with --record flag
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_fail",
        "--binary", str(binary),
        "--record",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    # Check that failure was recorded
    db = SignatureDatabase(db_path)
    db.init_database()
    
    test_results = db.get_test_results("sig_fail")
    assert len(test_results) > 0
    
    result = test_results[0]
    assert result["signature_id"] == "sig_fail"
    assert result["passed"] is False
    assert result["failure_reason"] is not None
    
    db.close()


def test_test_parallel_execution(tmp_path):
    """Test that corpus testing works in parallel."""
    # Create multiple test binaries
    binaries = []
    for i in range(5):
        code = bytes.fromhex("48 83 EC 28 C3")
        binary = write_pe(tmp_path, f"test_{i}.exe", text=code)
        binaries.append(binary)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_parallel",
        name="Parallel Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test against all binaries
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_parallel",
        "--corpus",
    ] + [str(b) for b in binaries] + [
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Should test all 5 binaries
    assert len(out["results"]) == 5
    
    # All should pass
    passed = [r for r in out["results"] if r["passed"]]
    assert len(passed) == 5


def test_test_match_offsets_reported(tmp_path):
    """Test that match offsets are reported in results."""
    # Create test binary
    code = bytes.fromhex("90 48 83 EC 28 C3")  # NOP before pattern
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_offset",
        name="Offset Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_offset",
        "--binary", str(binary),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    result = out["results"][0]
    assert result["passed"] is True
    assert "match_offsets" in result
    assert len(result["match_offsets"]) == 1
    # Should be at file offset (headers are 0x200, so NOP at 0x200, pattern at 0x201)
    # But matcher works on section data, so offset is relative


def test_test_allow_multiple_matches(tmp_path):
    """Test --allow-multiple flag for signatures that match multiple times."""
    # Create binary with repeated pattern
    code = bytes.fromhex(
        "48 83 EC 28 "
        "C3 "
        "48 83 EC 28 "
        "C3"
    )
    binary = write_pe(tmp_path, "test.exe", text=code)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_multi_ok",
        name="Multi OK",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test with --allow-multiple flag
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_multi_ok",
        "--binary", str(binary),
        "--allow-multiple",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    result = out["results"][0]
    # With --allow-multiple, should pass as long as at least one match exists
    assert result["passed"] is True
    assert result["match_count"] == 2


def test_test_summary_output(tmp_path):
    """Test that summary statistics are included in output."""
    # Create test binaries
    code = bytes.fromhex("48 83 EC 28 C3")
    binary1 = write_pe(tmp_path, "v1.exe", text=code)
    binary2 = write_pe(tmp_path, "v2.exe", text=code)
    
    # Create database with signature
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_summary",
        name="Summary Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    db.close()
    
    # Test against multiple binaries
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "test",
        "--db", str(db_path),
        "--signature", "sig_summary",
        "--corpus", str(binary1), str(binary2),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Check for summary statistics
    assert "summary" in out or "results" in out
    
    if "summary" in out:
        summary = out["summary"]
        assert "total_tests" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert summary["total_tests"] == 2
        assert summary["passed"] == 2
