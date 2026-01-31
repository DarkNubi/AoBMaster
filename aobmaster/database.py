"""
Persistent signature storage for AoBMaster v2.

SQLite-backed database for storing signatures, metadata, and test results.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# Database schema version for migrations
DB_SCHEMA_VERSION = 2


@dataclass
class SignatureRecord:
    """Signature database record."""
    
    id: str  # Unique signature ID
    name: str  # Human-readable name
    pattern: str  # CE-style pattern string
    anchor_rva: int
    binary_hash: str  # SHA256 of binary
    created_at: str  # ISO timestamp
    author: Optional[str]
    version_range: Optional[str]  # e.g., "1.0.0-1.5.3"
    metadata: dict[str, Any]  # JSON metadata (SignatureIR, etc.)
    parent_id: Optional[str] = None  # Parent signature (if evolved from another)
    deprecated: bool = False  # True if signature is known to be broken
    deprecation_reason: Optional[str] = None  # Why signature was deprecated
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "pattern": self.pattern,
            "anchor_rva": hex(self.anchor_rva),
            "binary_hash": self.binary_hash,
            "created_at": self.created_at,
            "author": self.author,
            "version_range": self.version_range,
            "metadata": self.metadata,
            "parent_id": self.parent_id,
            "deprecated": self.deprecated,
            "deprecation_reason": self.deprecation_reason,
        }


class SignatureDatabase:
    """
    SQLite-backed signature database.
    
    Thread-safe for single-process access.
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
    
    def _connect(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def init_database(self) -> None:
        """
        Initialize database schema.
        
        Safe to call multiple times (idempotent).
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        # Schema version table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        
        # Check current schema version
        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        current_version = row[0] if row else 0
        
        if current_version < DB_SCHEMA_VERSION:
            # Apply migrations
            self._apply_migrations(cursor, current_version)
            cursor.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                         (DB_SCHEMA_VERSION, datetime.utcnow().isoformat()))
        
        conn.commit()
    
    def _apply_migrations(self, cursor: sqlite3.Cursor, from_version: int) -> None:
        """Apply database migrations."""
        if from_version < 1:
            # Initial schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signatures (
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
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signatures_name ON signatures(name)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signatures_hash ON signatures(binary_hash)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signature_id TEXT NOT NULL,
                    binary_path TEXT NOT NULL,
                    binary_hash TEXT NOT NULL,
                    test_date TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    failure_reason TEXT,
                    FOREIGN KEY (signature_id) REFERENCES signatures(id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_test_results_signature ON test_results(signature_id)
            """)
        
        if from_version < 2:
            # Schema version 2: Add signature families
            cursor.execute("""
                ALTER TABLE signatures ADD COLUMN parent_id TEXT
            """)
            
            cursor.execute("""
                ALTER TABLE signatures ADD COLUMN deprecated INTEGER DEFAULT 0
            """)
            
            cursor.execute("""
                ALTER TABLE signatures ADD COLUMN deprecation_reason TEXT
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signatures_parent ON signatures(parent_id)
            """)
    
    def save_signature(self, signature: SignatureRecord) -> None:
        """
        Save or update a signature.
        
        Uses REPLACE to handle duplicates (upsert).
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            REPLACE INTO signatures (id, name, pattern, anchor_rva, binary_hash, 
                                    created_at, author, version_range, metadata_json,
                                    parent_id, deprecated, deprecation_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signature.id,
            signature.name,
            signature.pattern,
            signature.anchor_rva,
            signature.binary_hash,
            signature.created_at,
            signature.author,
            signature.version_range,
            json.dumps(signature.metadata, sort_keys=True),
            signature.parent_id,
            1 if signature.deprecated else 0,
            signature.deprecation_reason,
        ))
        
        conn.commit()
    
    def get_signature(self, signature_id: str) -> Optional[SignatureRecord]:
        """Get signature by ID."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM signatures WHERE id = ?", (signature_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return SignatureRecord(
            id=row["id"],
            name=row["name"],
            pattern=row["pattern"],
            anchor_rva=row["anchor_rva"],
            binary_hash=row["binary_hash"],
            created_at=row["created_at"],
            author=row["author"],
            version_range=row["version_range"],
            metadata=json.loads(row["metadata_json"]),
            parent_id=row.get("parent_id"),
            deprecated=bool(row.get("deprecated", 0)),
            deprecation_reason=row.get("deprecation_reason"),
        )
    
    def list_signatures(self, name_filter: Optional[str] = None) -> list[SignatureRecord]:
        """
        List all signatures.
        
        Args:
            name_filter: Optional substring to filter by name
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        if name_filter:
            cursor.execute("SELECT * FROM signatures WHERE name LIKE ? ORDER BY name",
                         (f"%{name_filter}%",))
        else:
            cursor.execute("SELECT * FROM signatures ORDER BY name")
        
        results = []
        for row in cursor.fetchall():
            results.append(SignatureRecord(
                id=row["id"],
                name=row["name"],
                pattern=row["pattern"],
                anchor_rva=row["anchor_rva"],
                binary_hash=row["binary_hash"],
                created_at=row["created_at"],
                author=row["author"],
                version_range=row["version_range"],
                metadata=json.loads(row["metadata_json"]),
                parent_id=row.get("parent_id"),
                deprecated=bool(row.get("deprecated", 0)),
                deprecation_reason=row.get("deprecation_reason"),
            ))
        
        return results
    
    def delete_signature(self, signature_id: str) -> bool:
        """
        Delete a signature.
        
        Returns True if signature was deleted, False if not found.
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM signatures WHERE id = ?", (signature_id,))
        conn.commit()
        
        return cursor.rowcount > 0
    
    def get_signature_family(self, signature_id: str) -> list[SignatureRecord]:
        """
        Get entire signature family (parent chain and children).
        
        Returns list ordered: root → parent → this → children
        """
        sig = self.get_signature(signature_id)
        if not sig:
            return []
        
        family = []
        
        # Walk up to root
        current = sig
        while current.parent_id:
            parent = self.get_signature(current.parent_id)
            if not parent:
                break
            family.insert(0, parent)
            current = parent
        
        # Add current signature
        family.append(sig)
        
        # Get all children (recursive)
        def get_children(parent_id: str) -> list[SignatureRecord]:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signatures WHERE parent_id = ?", (parent_id,))
            children = []
            for row in cursor.fetchall():
                child = SignatureRecord(
                    id=row["id"],
                    name=row["name"],
                    pattern=row["pattern"],
                    anchor_rva=row["anchor_rva"],
                    binary_hash=row["binary_hash"],
                    created_at=row["created_at"],
                    author=row["author"],
                    version_range=row["version_range"],
                    metadata=json.loads(row["metadata_json"]),
                    parent_id=row.get("parent_id"),
                    deprecated=bool(row.get("deprecated", 0)),
                    deprecation_reason=row.get("deprecation_reason"),
                )
                children.append(child)
                # Recursive: get children of children
                children.extend(get_children(child.id))
            return children
        
        family.extend(get_children(sig.id))
        
        return family
    
    def deprecate_signature(self, signature_id: str, reason: str) -> None:
        """Mark signature as deprecated (but don't delete it)."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE signatures 
            SET deprecated = 1, deprecation_reason = ?
            WHERE id = ?
        """, (reason, signature_id))
        
        conn.commit()
    
    def record_test_result(
        self,
        signature_id: str,
        binary_path: str,
        binary_hash: str,
        passed: bool,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Record a test result for a signature."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO test_results (signature_id, binary_path, binary_hash, 
                                     test_date, passed, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            signature_id,
            binary_path,
            binary_hash,
            datetime.utcnow().isoformat(),
            1 if passed else 0,
            failure_reason,
        ))
        
        conn.commit()
    
    def get_test_results(self, signature_id: str) -> list[dict[str, Any]]:
        """Get all test results for a signature."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM test_results 
            WHERE signature_id = ? 
            ORDER BY test_date DESC
        """, (signature_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row["id"],
                "binary_path": row["binary_path"],
                "binary_hash": row["binary_hash"],
                "test_date": row["test_date"],
                "passed": bool(row["passed"]),
                "failure_reason": row["failure_reason"],
            })
        
        return results
    
    def export_to_json(self, output_path: Path) -> None:
        """Export entire database to JSON file."""
        signatures = self.list_signatures()
        
        export_data = {
            "version": DB_SCHEMA_VERSION,
            "exported_at": datetime.utcnow().isoformat(),
            "signatures": [sig.to_dict() for sig in signatures],
        }
        
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2, sort_keys=True)
    
    def import_from_json(self, input_path: Path) -> int:
        """
        Import signatures from JSON file.
        
        Returns number of signatures imported.
        """
        with open(input_path, "r") as f:
            data = json.load(f)
        
        count = 0
        for sig_dict in data.get("signatures", []):
            sig = SignatureRecord(
                id=sig_dict["id"],
                name=sig_dict["name"],
                pattern=sig_dict["pattern"],
                anchor_rva=int(sig_dict["anchor_rva"], 16) if isinstance(sig_dict["anchor_rva"], str) else sig_dict["anchor_rva"],
                binary_hash=sig_dict["binary_hash"],
                created_at=sig_dict["created_at"],
                author=sig_dict.get("author"),
                version_range=sig_dict.get("version_range"),
                metadata=sig_dict.get("metadata", {}),
            )
            self.save_signature(sig)
            count += 1
        
        return count
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
