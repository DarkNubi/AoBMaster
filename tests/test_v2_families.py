"""
Tests for AoBMaster v2 Phase 5: Signature families.

Tests diagnose command, parent/child relationships, and deprecation functionality.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime

from aobmaster.database import SignatureDatabase, SignatureRecord

from .conftest import write_pe


def test_diagnose_signature_family(tmp_path):
    """Test diagnosing signature family lineage."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create signature family: parent -> child -> grandchild
    parent = SignatureRecord(
        id="sig_parent",
        name="Parent Sig",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range="1.0.0-1.5.0",
        metadata={},
        parent_id=None,
    )
    
    child = SignatureRecord(
        id="sig_child",
        name="Child Sig",
        pattern="48 83 EC 30",
        anchor_rva=0x1000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range="1.6.0-2.0.0",
        metadata={},
        parent_id="sig_parent",
    )
    
    grandchild = SignatureRecord(
        id="sig_grandchild",
        name="Grandchild Sig",
        pattern="48 83 EC 38",
        anchor_rva=0x1000,
        binary_hash="hash3",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range="2.1.0+",
        metadata={},
        parent_id="sig_child",
    )
    
    db.save_signature(parent)
    db.save_signature(child)
    db.save_signature(grandchild)
    db.close()
    
    # Diagnose child
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_child",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    assert out["target_signature_id"] == "sig_child"
    assert out["family_size"] == 3
    assert len(out["family"]) == 3


def test_diagnose_parent_child_relationships(tmp_path):
    """Test that parent-child relationships are correctly identified."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create parent and child
    parent = SignatureRecord(
        id="sig_v1",
        name="Version 1",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id=None,
    )
    
    child = SignatureRecord(
        id="sig_v2",
        name="Version 2",
        pattern="48 83 EC 30",
        anchor_rva=0x1000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id="sig_v1",
    )
    
    db.save_signature(parent)
    db.save_signature(child)
    db.close()
    
    # Diagnose child
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_v2",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Find parent and child in family
    family_ids = [sig["signature"]["id"] for sig in out["family"]]
    assert "sig_v1" in family_ids
    assert "sig_v2" in family_ids
    
    # Check that child has correct parent_id
    child_sig = next(s for s in out["family"] if s["signature"]["id"] == "sig_v2")
    assert child_sig["signature"]["parent_id"] == "sig_v1"


def test_diagnose_orphan_signature(tmp_path):
    """Test diagnosing signature with no family (orphan)."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create standalone signature
    sig = SignatureRecord(
        id="sig_orphan",
        name="Orphan Sig",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id=None,
    )
    db.save_signature(sig)
    db.close()
    
    # Diagnose
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_orphan",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Family size should be 1 (just itself)
    assert out["family_size"] == 1
    assert len(out["family"]) == 1
    assert out["family"][0]["signature"]["id"] == "sig_orphan"


def test_diagnose_with_test_results(tmp_path):
    """Test that diagnose includes test result statistics."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create parent and child
    parent = SignatureRecord(
        id="sig_parent_test",
        name="Parent with Tests",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id=None,
    )
    
    child = SignatureRecord(
        id="sig_child_test",
        name="Child with Tests",
        pattern="48 83 EC 30",
        anchor_rva=0x1000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id="sig_parent_test",
    )
    
    db.save_signature(parent)
    db.save_signature(child)
    
    # Add test results for both
    # Parent: 100% pass rate
    for i in range(5):
        db.record_test_result("sig_parent_test", f"/path/{i}.exe", f"hash_{i}", True, None)
    
    # Child: 80% pass rate
    for i in range(5):
        passed = (i < 4)
        db.record_test_result("sig_child_test", f"/path/{i}.exe", f"hash_{i}", passed, None if passed else "Failure")
    
    db.close()
    
    # Diagnose
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_child_test",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Check test statistics for each family member
    for sig_data in out["family"]:
        assert "test_count" in sig_data
        assert "pass_rate" in sig_data
    
    parent_data = next(s for s in out["family"] if s["signature"]["id"] == "sig_parent_test")
    child_data = next(s for s in out["family"] if s["signature"]["id"] == "sig_child_test")
    
    assert parent_data["test_count"] == 5
    assert parent_data["pass_rate"] == 1.0
    
    assert child_data["test_count"] == 5
    assert child_data["pass_rate"] == 0.8


def test_deprecate_signature(tmp_path):
    """Test marking a signature as deprecated."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create signature
    sig = SignatureRecord(
        id="sig_deprecate",
        name="To Be Deprecated",
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
    
    # Deprecate via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "deprecate",
        "--db", str(db_path),
        "--signature", "sig_deprecate",
        "--reason", "Pattern broken in v2.0",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    # Verify deprecation
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = db.get_signature("sig_deprecate")
    assert sig.deprecated is True
    assert sig.deprecation_reason == "Pattern broken in v2.0"
    
    db.close()


def test_deprecated_signature_in_family(tmp_path):
    """Test that deprecated signatures appear in family diagnosis."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create family with deprecated parent
    parent = SignatureRecord(
        id="sig_deprecated_parent",
        name="Deprecated Parent",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range="1.0.0",
        metadata={},
        parent_id=None,
        deprecated=True,
        deprecation_reason="Replaced by child",
    )
    
    child = SignatureRecord(
        id="sig_active_child",
        name="Active Child",
        pattern="48 83 EC 30",
        anchor_rva=0x1000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range="2.0.0",
        metadata={},
        parent_id="sig_deprecated_parent",
    )
    
    db.save_signature(parent)
    db.save_signature(child)
    db.close()
    
    # Diagnose family
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_active_child",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Both should be in family
    assert out["family_size"] == 2
    
    # Find deprecated parent
    parent_data = next(s for s in out["family"] if s["signature"]["id"] == "sig_deprecated_parent")
    assert parent_data["signature"]["deprecated"] is True
    assert parent_data["signature"]["deprecation_reason"] == "Replaced by child"


def test_diagnose_text_output(tmp_path):
    """Test diagnose output in text format."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create simple family
    parent = SignatureRecord(
        id="sig_text_parent",
        name="Text Parent",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id=None,
    )
    
    child = SignatureRecord(
        id="sig_text_child",
        name="Text Child",
        pattern="48 83 EC 30",
        anchor_rva=0x1000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id="sig_text_parent",
    )
    
    db.save_signature(parent)
    db.save_signature(child)
    db.close()
    
    # Diagnose with text format
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_text_child",
        "--format", "text",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = proc.stdout
    
    # Check for expected text elements
    assert "Text Child" in output or "sig_text_child" in output
    assert "Family" in output or "family" in output
    assert "Lineage" in output or "lineage" in output


def test_diagnose_multiple_children(tmp_path):
    """Test diagnosing family with multiple children."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create parent with multiple children
    parent = SignatureRecord(
        id="sig_multi_parent",
        name="Multi Parent",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id=None,
    )
    
    child1 = SignatureRecord(
        id="sig_child_a",
        name="Child A",
        pattern="48 83 EC 30",
        anchor_rva=0x1000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id="sig_multi_parent",
    )
    
    child2 = SignatureRecord(
        id="sig_child_b",
        name="Child B",
        pattern="48 83 EC 38",
        anchor_rva=0x1000,
        binary_hash="hash3",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        parent_id="sig_multi_parent",
    )
    
    db.save_signature(parent)
    db.save_signature(child1)
    db.save_signature(child2)
    db.close()
    
    # Diagnose one child - should see entire family
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_child_a",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Should have all 3 signatures in family
    assert out["family_size"] == 3
    
    family_ids = [s["signature"]["id"] for s in out["family"]]
    assert "sig_multi_parent" in family_ids
    assert "sig_child_a" in family_ids
    assert "sig_child_b" in family_ids


def test_query_deprecated_signatures(tmp_path):
    """Test querying for deprecated signatures."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create mix of active and deprecated
    active = SignatureRecord(
        id="sig_active",
        name="Active",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        deprecated=False,
    )
    
    deprecated = SignatureRecord(
        id="sig_deprecated",
        name="Deprecated",
        pattern="48 83 EC 30",
        anchor_rva=0x2000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
        deprecated=True,
        deprecation_reason="Test deprecation",
    )
    
    db.save_signature(active)
    db.save_signature(deprecated)
    
    # Query deprecated only using direct SQL
    conn = db._connect()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM signatures WHERE deprecated = 1")
    results = cursor.fetchall()
    assert len(results) == 1
    assert results[0]["id"] == "sig_deprecated"
    
    # Query active only
    cursor.execute("SELECT * FROM signatures WHERE deprecated = 0 OR deprecated IS NULL")
    results = cursor.fetchall()
    assert len(results) == 1
    assert results[0]["id"] == "sig_active"
    
    db.close()


def test_signature_evolution_metadata(tmp_path):
    """Test that signature evolution is tracked in metadata."""
    db_path = tmp_path / "test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create evolving signature with metadata
    v1 = SignatureRecord(
        id="sig_v1",
        name="Evolution Test v1",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author="user1",
        version_range="1.0.0",
        metadata={"generation": 1, "notes": "Initial version"},
    )
    
    v2 = SignatureRecord(
        id="sig_v2",
        name="Evolution Test v2",
        pattern="48 83 EC 30",
        anchor_rva=0x1000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author="user2",
        version_range="2.0.0",
        metadata={"generation": 2, "notes": "Updated for v2", "reason": "Stack frame changed"},
        parent_id="sig_v1",
    )
    
    db.save_signature(v1)
    db.save_signature(v2)
    db.close()
    
    # Diagnose to see evolution
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "diagnose",
        "--db", str(db_path),
        "--signature", "sig_v2",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    v1_data = next(s for s in out["family"] if s["signature"]["id"] == "sig_v1")
    v2_data = next(s for s in out["family"] if s["signature"]["id"] == "sig_v2")
    
    # Check metadata is preserved
    assert v1_data["signature"]["metadata"]["generation"] == 1
    assert v2_data["signature"]["metadata"]["generation"] == 2
    assert v2_data["signature"]["metadata"]["reason"] == "Stack frame changed"
