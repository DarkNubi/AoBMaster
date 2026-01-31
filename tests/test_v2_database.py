"""
Tests for AoBMaster v2 Phase 2: Database operations.

Tests db init, save, list, query, export/import, and schema migrations.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from aobmaster.database import DB_SCHEMA_VERSION, SignatureDatabase, SignatureRecord

from .conftest import write_pe


def test_db_init_creates_database(tmp_path):
    """Test that db init creates a new database."""
    db_path = tmp_path / "test.db"
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "init",
        "--db", str(db_path),
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    # Database file should exist
    assert db_path.exists()
    
    # Should be able to open and query schema
    db = SignatureDatabase(db_path)
    conn = db._connect()
    cursor = conn.cursor()
    
    # Check schema_version table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    assert cursor.fetchone() is not None
    
    # Check current schema version
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == DB_SCHEMA_VERSION
    
    db.close()


def test_db_init_idempotent(tmp_path):
    """Test that db init can be called multiple times safely."""
    db_path = tmp_path / "test.db"
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "init",
        "--db", str(db_path),
    ]
    
    # Initialize twice
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    # Should still be valid
    db = SignatureDatabase(db_path)
    db.init_database()
    assert db_path.exists()
    db.close()


def test_db_save_signature(tmp_path):
    """Test saving a signature to database."""
    db_path = tmp_path / "test.db"
    
    # Initialize database
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create test signature
    sig = SignatureRecord(
        id="sig_test_001",
        name="Test Signature",
        pattern="48 83 EC 28 ?? ?? ?? ?? 48 85 C0",
        anchor_rva=0x1000,
        binary_hash="abc123",
        created_at=datetime.utcnow().isoformat(),
        author="test_user",
        version_range="1.0.0-1.5.0",
        metadata={"test_key": "test_value"},
    )
    
    db.save_signature(sig)
    
    # Retrieve and verify
    retrieved = db.get_signature("sig_test_001")
    assert retrieved is not None
    assert retrieved.id == sig.id
    assert retrieved.name == sig.name
    assert retrieved.pattern == sig.pattern
    assert retrieved.anchor_rva == sig.anchor_rva
    assert retrieved.binary_hash == sig.binary_hash
    assert retrieved.author == sig.author
    assert retrieved.metadata == sig.metadata
    
    db.close()


def test_db_list_signatures(tmp_path):
    """Test listing signatures from database."""
    db_path = tmp_path / "test.db"
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Add multiple signatures
    for i in range(3):
        sig = SignatureRecord(
            id=f"sig_{i:03d}",
            name=f"Test Signature {i}",
            pattern=f"48 83 EC {i:02X}",
            anchor_rva=0x1000 + i * 0x100,
            binary_hash=f"hash_{i}",
            created_at=datetime.utcnow().isoformat(),
            author="test_user",
            version_range=None,
            metadata={},
        )
        db.save_signature(sig)
    
    # List all
    signatures = db.list_signatures()
    assert len(signatures) == 3
    
    db.close()


def test_db_query_by_name(tmp_path):
    """Test querying signatures by name pattern."""
    db_path = tmp_path / "test.db"
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Add test signatures
    sig1 = SignatureRecord(
        id="sig_001",
        name="PlayerController::Update",
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
        name="EnemyController::Update",
        pattern="48 83 EC 30",
        anchor_rva=0x2000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    
    db.save_signature(sig1)
    db.save_signature(sig2)
    
    # Query by name pattern using list_signatures with name_filter
    results = db.list_signatures(name_filter="Controller")
    assert len(results) == 2
    
    results = db.list_signatures(name_filter="Player")
    assert len(results) == 1
    assert results[0].name == "PlayerController::Update"
    
    db.close()


def test_db_query_by_hash(tmp_path):
    """Test querying signatures by binary hash (via metadata or custom query)."""
    db_path = tmp_path / "test.db"
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig1 = SignatureRecord(
        id="sig_001",
        name="Sig1",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="specific_hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    
    sig2 = SignatureRecord(
        id="sig_002",
        name="Sig2",
        pattern="48 83 EC 30",
        anchor_rva=0x2000,
        binary_hash="different_hash",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    
    db.save_signature(sig1)
    db.save_signature(sig2)
    
    # Query by hash directly with SQL
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signatures WHERE binary_hash = ?", ("specific_hash",))
    results = cursor.fetchall()
    assert len(results) == 1
    assert results[0]["id"] == "sig_001"
    
    db.close()


def test_db_upsert_behavior(tmp_path):
    """Test that saving with same ID updates existing record."""
    db_path = tmp_path / "test.db"
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Save initial
    sig = SignatureRecord(
        id="sig_001",
        name="Original Name",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # Update with same ID
    sig_updated = SignatureRecord(
        id="sig_001",
        name="Updated Name",
        pattern="48 83 EC 30",
        anchor_rva=0x2000,
        binary_hash="hash2",
        created_at=datetime.utcnow().isoformat(),
        author="new_author",
        version_range="2.0.0",
        metadata={"updated": True},
    )
    db.save_signature(sig_updated)
    
    # Should have only one record with updated values
    signatures = db.list_signatures()
    assert len(signatures) == 1
    
    retrieved = db.get_signature("sig_001")
    assert retrieved.name == "Updated Name"
    assert retrieved.pattern == "48 83 EC 30"
    assert retrieved.author == "new_author"
    
    db.close()


def test_db_export_import(tmp_path):
    """Test exporting and importing database."""
    db_path = tmp_path / "test.db"
    export_path = tmp_path / "export.json"
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Add test data
    sig = SignatureRecord(
        id="sig_001",
        name="Test Export",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author="exporter",
        version_range="1.0.0",
        metadata={"exported": True},
    )
    db.save_signature(sig)
    
    # Export
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "export",
        "--db", str(db_path),
        "--output", str(export_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    assert export_path.exists()
    
    # Verify export format
    with open(export_path, "r") as f:
        export_data = json.load(f)
    
    assert "version" in export_data
    assert "exported_at" in export_data
    assert "signatures" in export_data
    assert len(export_data["signatures"]) == 1
    
    db.close()
    
    # Import to new database
    db_path2 = tmp_path / "test2.db"
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "import",
        "--db", str(db_path2),
        "--input", str(export_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    # Verify imported data
    db2 = SignatureDatabase(db_path2)
    db2.init_database()
    
    imported = db2.get_signature("sig_001")
    assert imported is not None
    assert imported.name == sig.name
    assert imported.pattern == sig.pattern
    
    db2.close()


def test_db_test_result_storage(tmp_path):
    """Test storing and retrieving test results."""
    db_path = tmp_path / "test.db"
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Create signature
    sig = SignatureRecord(
        id="sig_001",
        name="Test Sig",
        pattern="48 83 EC 28",
        anchor_rva=0x1000,
        binary_hash="hash1",
        created_at=datetime.utcnow().isoformat(),
        author=None,
        version_range=None,
        metadata={},
    )
    db.save_signature(sig)
    
    # Save test results using record_test_result
    db.record_test_result(
        signature_id="sig_001",
        binary_path="/path/to/binary.exe",
        binary_hash="binary_hash_1",
        passed=True,
        failure_reason=None,
    )
    
    db.record_test_result(
        signature_id="sig_001",
        binary_path="/path/to/binary2.exe",
        binary_hash="binary_hash_2",
        passed=False,
        failure_reason="Pattern not found",
    )
    
    # Retrieve results
    results = db.get_test_results("sig_001")
    assert len(results) == 2
    
    passed_results = [r for r in results if r["passed"]]
    failed_results = [r for r in results if not r["passed"]]
    
    assert len(passed_results) == 1
    assert len(failed_results) == 1
    assert failed_results[0]["failure_reason"] == "Pattern not found"
    
    db.close()


def test_db_schema_migration(tmp_path):
    """Test that schema migrations work correctly."""
    db_path = tmp_path / "test.db"
    
    # Create database with old schema (version 1)
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create schema version 1 (without parent_id, deprecated fields)
    cursor.execute("""
        CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (1, ?)",
                  (datetime.utcnow().isoformat(),))
    
    cursor.execute("""
        CREATE TABLE signatures (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pattern TEXT NOT NULL,
            anchor_rva INTEGER NOT NULL,
            binary_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            author TEXT,
            version_range TEXT,
            metadata_json TEXT NOT NULL
        )
    """)
    
    # Insert test data
    cursor.execute("""
        INSERT INTO signatures (id, name, pattern, anchor_rva, binary_hash, created_at, author, version_range, metadata_json)
        VALUES ('sig_001', 'Old Sig', '48 83 EC 28', 4096, 'hash1', ?, NULL, NULL, '{}')
    """, (datetime.utcnow().isoformat(),))
    
    conn.commit()
    conn.close()
    
    # Open with new SignatureDatabase (should trigger migration)
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Check schema was upgraded
    conn = db._connect()
    cursor = conn.cursor()
    
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cursor.fetchone()
    assert row[0] == DB_SCHEMA_VERSION
    
    # Check new columns exist
    cursor.execute("PRAGMA table_info(signatures)")
    columns = [col[1] for col in cursor.fetchall()]
    assert "parent_id" in columns
    assert "deprecated" in columns
    assert "deprecation_reason" in columns
    
    # Old data should still be accessible
    sig = db.get_signature("sig_001")
    assert sig is not None
    assert sig.name == "Old Sig"
    assert sig.parent_id is None
    assert sig.deprecated is False
    
    db.close()


def test_db_save_with_cli(tmp_path):
    """Test saving signature via CLI."""
    db_path = tmp_path / "test.db"
    
    # Initialize database
    cmd_init = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "init",
        "--db", str(db_path),
    ]
    subprocess.run(cmd_init, capture_output=True, text=True, check=True)
    
    # Save signature via CLI
    cmd_save = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "save",
        "--db", str(db_path),
        "--id", "sig_cli_001",
        "--name", "CLI Test Signature",
        "--pattern", "48 83 EC 28 ?? ?? ?? ??",
        "--anchor-rva", "0x1000",
        "--binary-hash", "cli_hash",
    ]
    subprocess.run(cmd_save, capture_output=True, text=True, check=True)
    
    # Verify via database API
    db = SignatureDatabase(db_path)
    db.init_database()
    
    sig = db.get_signature("sig_cli_001")
    assert sig is not None
    assert sig.name == "CLI Test Signature"
    assert sig.pattern == "48 83 EC 28 ?? ?? ?? ??"
    assert sig.anchor_rva == 0x1000
    
    db.close()


def test_db_list_via_cli(tmp_path):
    """Test listing signatures via CLI."""
    db_path = tmp_path / "test.db"
    
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Add test signatures
    for i in range(3):
        sig = SignatureRecord(
            id=f"sig_{i:03d}",
            name=f"Test Sig {i}",
            pattern=f"48 83 EC {i:02X}",
            anchor_rva=0x1000 + i,
            binary_hash=f"hash_{i}",
            created_at=datetime.utcnow().isoformat(),
            author=None,
            version_range=None,
            metadata={},
        )
        db.save_signature(sig)
    
    db.close()
    
    # List via CLI
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "db",
        "list",
        "--db", str(db_path),
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    assert "signatures" in out
    assert len(out["signatures"]) == 3
