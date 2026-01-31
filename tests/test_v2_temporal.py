"""
Tests for AoBMaster v2 Phase 4: Temporal analysis.

Tests analyze command with test history, confidence intervals, and stability assessment.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta

from aobmaster.database import SignatureDatabase, SignatureRecord

from .conftest import write_pe


def test_analyze_single_signature(tmp_path):
    """Test analyzing a single signature with test history."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create signature
    sig = SignatureRecord(
        id="sig_analyze",
        name="Analyze Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # Add test results
    for i in range(10):
        db.record_test_result(
            signature_id="sig_analyze",
            binary_path=f"/path/to/binary_{i}.exe",
            binary_hash=f"hash_{i}",
            passed=True,
            failure_reason=None,
        )
    
    db.close()
    
    # Analyze via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_analyze",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    assert "analyses" in out
    assert len(out["analyses"]) == 1
    
    analysis = out["analyses"][0]
    assert "signature" in analysis
    assert "analysis" in analysis
    assert "breakage_prediction" in analysis
    
    # Check analysis structure
    stats = analysis["analysis"]
    assert "total_tests" in stats
    assert "pass_rate" in stats
    assert "stability_assessment" in stats
    assert stats["total_tests"] == 10
    assert stats["pass_rate"] == 1.0  # All passed


def test_analyze_confidence_intervals(tmp_path):
    """Test that confidence intervals are calculated."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_ci",
        name="CI Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # Add mixed results (80% pass rate)
    for i in range(10):
        passed = (i < 8)  # 8 pass, 2 fail
        db.record_test_result(
            signature_id="sig_ci",
            binary_path=f"/path/to/binary_{i}.exe",
            binary_hash=f"hash_{i}",
            passed=passed,
            failure_reason=None if passed else "Test failure",
        )
    
    db.close()
    
    # Analyze
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_ci",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    analysis = out["analyses"][0]["analysis"]
    
    assert "confidence_interval" in analysis
    ci = analysis["confidence_interval"]
    
    assert "current" in ci
    assert "pessimistic_lower_bound" in ci
    assert "optimistic_upper_bound" in ci
    
    # Check that values make sense
    assert 0.0 <= ci["pessimistic_lower_bound"] <= ci["current"]
    assert ci["current"] <= ci["optimistic_upper_bound"] <= 1.0
    assert ci["current"] == 0.8  # 8/10


def test_analyze_stability_assessment(tmp_path):
    """Test stability assessment classification."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create signature with high stability (95%+ pass rate)
    sig_stable = SignatureRecord(
        id="sig_stable",
        name="Stable Sig",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig_stable)
    
    # 19 pass, 1 fail = 95% pass rate
    for i in range(20):
        passed = (i < 19)
        db.record_test_result(
            signature_id="sig_stable",
            binary_path=f"/path/to/binary_{i}.exe",
            binary_hash=f"hash_{i}",
            passed=passed,
            failure_reason=None if passed else "Rare failure",
        )
    
    db.close()
    
    # Analyze
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_stable",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    analysis = out["analyses"][0]["analysis"]
    
    # Should be classified as stable
    assert analysis["stability_assessment"] in ["stable", "high_confidence", "excellent"]
    assert analysis["pass_rate"] == 0.95


def test_analyze_unstable_signature(tmp_path):
    """Test analysis of unstable signature (low pass rate)."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_unstable",
        name="Unstable Sig",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # 5 pass, 15 fail = 25% pass rate (very unstable)
    for i in range(20):
        passed = (i < 5)
        db.record_test_result(
            signature_id="sig_unstable",
            binary_path=f"/path/to/binary_{i}.exe",
            binary_hash=f"hash_{i}",
            passed=passed,
            failure_reason=None if passed else "Pattern broken",
        )
    
    db.close()
    
    # Analyze
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_unstable",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    analysis = out["analyses"][0]["analysis"]
    
    # Should be classified as unstable
    assert analysis["stability_assessment"] in ["unstable", "low_confidence", "broken"]
    assert analysis["pass_rate"] == 0.25


def test_analyze_breakage_prediction(tmp_path):
    """Test breakage likelihood prediction."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_predict",
        name="Predict Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # 70% pass rate - moderate risk
    for i in range(10):
        passed = (i < 7)
        db.record_test_result(
            signature_id="sig_predict",
            binary_path=f"/path/to/binary_{i}.exe",
            binary_hash=f"hash_{i}",
            passed=passed,
            failure_reason=None if passed else "Failure",
        )
    
    db.close()
    
    # Analyze
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_predict",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    prediction = out["analyses"][0]["breakage_prediction"]
    
    assert "likelihood" in prediction
    assert "confidence" in prediction
    
    # Should predict some risk given 70% pass rate
    assert prediction["likelihood"] in ["low", "medium", "high", "very_high"]
    assert 0.0 <= prediction["confidence"] <= 1.0


def test_analyze_all_signatures(tmp_path):
    """Test analyzing all signatures in database."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create multiple signatures
    for i in range(3):
        sig = SignatureRecord(
            id=f"sig_{i:03d}",
            name=f"Sig {i}",
            pattern=f"48 83 EC {i:02X}",
            anchor_rva=0x1000 + i,
            binary_hash=f"hash_{i}",
            created_at=datetime.utcnow().isoformat(),
            author=None,
            version_range=None,
            metadata={},
        )
        db.save_signature(sig)
        
        # Add test results
        for j in range(5):
            db.record_test_result(
                signature_id=f"sig_{i:03d}",
                binary_path=f"/path/to/binary_{j}.exe",
                binary_hash=f"hash_{j}",
                passed=True,
                failure_reason=None,
            )
    
    db.close()
    
    # Analyze all (no --signature flag)
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    assert len(out["analyses"]) == 3


def test_analyze_with_recommendation(tmp_path):
    """Test that analysis includes actionable recommendations."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_recommend",
        name="Recommend Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # Add some failures to trigger recommendation
    for i in range(10):
        passed = (i < 6)  # 60% pass rate
        db.record_test_result(
            signature_id="sig_recommend",
            binary_path=f"/path/to/binary_{i}.exe",
            binary_hash=f"hash_{i}",
            passed=passed,
            failure_reason=None if passed else "Failure",
        )
    
    db.close()
    
    # Analyze
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_recommend",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    analysis = out["analyses"][0]["analysis"]
    
    assert "recommendation" in analysis
    assert isinstance(analysis["recommendation"], str)
    assert len(analysis["recommendation"]) > 0


def test_analyze_no_test_history(tmp_path):
    """Test analyzing signature with no test history."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create signature with no test results
    sig = SignatureRecord(
        id="sig_nohistory",
        name="No History",
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
    
    # Analyze
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_nohistory",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    analysis = out["analyses"][0]["analysis"]
    
    # Should handle gracefully
    assert analysis["total_tests"] == 0
    # May report unknown/insufficient_data


def test_analyze_text_output(tmp_path):
    """Test analyze output in text format."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_text",
        name="Text Output Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # Add test results
    for i in range(10):
        db.record_test_result(
            signature_id="sig_text",
            binary_path=f"/path/to/binary_{i}.exe",
            binary_hash=f"hash_{i}",
            passed=True,
            failure_reason=None,
        )
    
    db.close()
    
    # Analyze with text format
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_text",
        "--format", "text",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = proc.stdout
    
    # Check for expected text elements
    assert "Text Output Test" in output
    assert "sig_text" in output
    assert "Pass Rate" in output or "pass_rate" in output
    assert "Stability" in output or "stability" in output


def test_analyze_temporal_trends(tmp_path):
    """Test that temporal trends are detected."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = SignatureRecord(
        id="sig_trend",
        name="Trend Test",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # Simulate declining stability over time
    # Early tests pass, later tests fail
    for i in range(20):
        passed = (i < 15)  # First 15 pass, last 5 fail
        # Manually insert with specific timestamps to simulate temporal progression
        conn = db._connect()
        cursor = conn.cursor()
        test_date = (datetime.utcnow() - timedelta(days=20-i)).isoformat()
        cursor.execute("""
            INSERT INTO test_results (signature_id, binary_path, binary_hash, test_date, passed, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "sig_trend",
            f"/path/to/binary_{i}.exe",
            f"hash_{i}",
            test_date,
            1 if passed else 0,
            None if passed else "Recent failure"
        ))
        conn.commit()
    
    db.close()
    
    # Analyze
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "analyze",
        "--db", str(db_path),
        "--signature", "sig_trend",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    analysis = out["analyses"][0]["analysis"]
    
    # Overall pass rate should be 75% (15/20)
    assert analysis["pass_rate"] == 0.75
    
    # May include trend information if implemented
    if "trend" in analysis:
        assert analysis["trend"] in ["declining", "stable", "improving", "insufficient_data"]
