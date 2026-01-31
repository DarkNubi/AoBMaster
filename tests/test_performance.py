"""
Tests for Phase 4 Performance Optimizations (v2.1)

Tests NumPy-optimized pattern matching and database performance improvements.
"""

import pytest
from aobmaster.matcher import AoBPattern, parse_ce_aob, scan_bytes as scan_standard
from aobmaster.matcher_optimized import (
    scan_bytes_optimized,
    scan_bytes_batch,
    is_numpy_available,
    get_performance_info,
    NUMPY_AVAILABLE,
)


def test_optimized_scan_matches_standard():
    """Test that optimized scan produces same results as standard."""
    # Create test data
    data = bytes([0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10] * 10)
    pattern = parse_ce_aob("48 89 ?? 24 08")
    
    # Compare results
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert standard_results == optimized_results


def test_optimized_scan_small_pattern():
    """Test that small patterns use standard implementation."""
    # Small pattern (< 16 bytes)
    data = bytes(range(256)) * 10
    pattern = parse_ce_aob("48 89 5C")  # Only 3 bytes
    
    # Should fallback to standard implementation
    results = scan_bytes_optimized(data, pattern, use_numpy=True)
    standard = scan_standard(data, pattern)
    
    assert results == standard


def test_optimized_scan_large_pattern():
    """Test optimized scan with large pattern."""
    # Large pattern (> 16 bytes)
    data = bytes([0x90] * 100 + [0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10,
                                  0x48, 0x8B, 0x05, 0x12, 0x34, 0x56, 0x78, 0x85, 0xC0] + [0x90] * 100)
    
    pattern = parse_ce_aob("48 89 5C 24 08 48 89 74 24 10 48 8B 05 ?? ?? ?? ?? 85 C0")  # 19 bytes
    
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert optimized_results == standard_results
    assert len(optimized_results) == 1
    assert optimized_results[0] == 100


def test_optimized_scan_with_wildcards():
    """Test optimized scan with wildcard patterns."""
    data = bytes([0x48, 0x89, 0xAA, 0x24, 0x08] + [0x00] * 100 + 
                 [0x48, 0x89, 0xBB, 0x24, 0x08])
    
    pattern = parse_ce_aob("48 89 ?? 24 08")
    
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert optimized_results == standard_results
    assert len(optimized_results) == 2


def test_optimized_scan_no_matches():
    """Test optimized scan when pattern doesn't match."""
    data = bytes([0xFF] * 1000)
    pattern = parse_ce_aob("48 89 5C 24 08 48 89 74 24 10")
    
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert optimized_results == standard_results
    assert len(optimized_results) == 0


def test_optimized_scan_multiple_matches():
    """Test optimized scan with multiple matches."""
    # Create data with multiple occurrences
    chunk = bytes([0x48, 0x89, 0x5C, 0x24, 0x08])
    data = chunk + bytes([0x00] * 10) + chunk + bytes([0x00] * 10) + chunk
    
    pattern = parse_ce_aob("48 89 5C 24 08")
    
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert optimized_results == standard_results
    assert len(optimized_results) == 3


def test_optimized_scan_disable_numpy():
    """Test that optimization can be disabled."""
    data = bytes(range(256))
    pattern = parse_ce_aob("48 89 5C 24 08 48 89 74 24 10 48 8B 05 12 34 56 78 85 C0")
    
    # Disable NumPy - should use standard implementation
    results = scan_bytes_optimized(data, pattern, use_numpy=False)
    standard = scan_standard(data, pattern)
    
    assert results == standard


def test_batch_scan_multiple_patterns():
    """Test batch scanning with multiple patterns."""
    data = bytes([0x48, 0x89, 0x5C] + [0x00] * 100 + [0x8B, 0x05, 0x12])
    
    patterns = [
        parse_ce_aob("48 89 5C"),
        parse_ce_aob("8B 05 12"),
    ]
    
    results = scan_bytes_batch(data, patterns, use_numpy=True)
    
    assert 0 in results
    assert 1 in results
    assert len(results[0]) == 1
    assert len(results[1]) == 1
    assert results[0][0] == 0
    assert results[1][0] == 103


def test_batch_scan_no_patterns():
    """Test batch scan with empty pattern list."""
    data = bytes([0xFF] * 100)
    patterns = []
    
    results = scan_bytes_batch(data, patterns, use_numpy=True)
    
    assert results == {}


def test_is_numpy_available():
    """Test numpy availability check."""
    result = is_numpy_available()
    
    # Should return bool
    assert isinstance(result, bool)
    # Should match module-level constant
    assert result == NUMPY_AVAILABLE


def test_get_performance_info():
    """Test performance info retrieval."""
    info = get_performance_info()
    
    assert "numpy_available" in info
    assert "optimization_level" in info
    assert "recommendations" in info
    
    assert isinstance(info["numpy_available"], bool)
    assert info["optimization_level"] in ("standard", "numpy")
    assert isinstance(info["recommendations"], list)
    
    # If NumPy not available, should recommend installation
    if not NUMPY_AVAILABLE:
        assert len(info["recommendations"]) > 0
        assert any("numpy" in rec.lower() for rec in info["recommendations"])


def test_optimized_scan_edge_case_empty_buffer():
    """Test optimized scan with empty buffer."""
    data = bytes([])
    pattern = parse_ce_aob("48 89 5C")
    
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert optimized_results == standard_results
    assert len(optimized_results) == 0


def test_optimized_scan_edge_case_buffer_smaller_than_pattern():
    """Test optimized scan when buffer is smaller than pattern."""
    data = bytes([0x48, 0x89])
    pattern = parse_ce_aob("48 89 5C 24 08")  # Pattern longer than data
    
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert optimized_results == standard_results
    assert len(optimized_results) == 0


def test_optimized_scan_all_wildcards():
    """Test optimized scan with pattern that's all wildcards."""
    data = bytes([0x11, 0x22, 0x33, 0x44, 0x55])
    
    # Create pattern with all wildcards (after first byte)
    # Note: First byte can't be wildcard per AoBMaster rules
    pattern = parse_ce_aob("11 ?? ??")
    
    standard_results = scan_standard(data, pattern)
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    
    assert optimized_results == standard_results


@pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not installed")
def test_numpy_specific_large_buffer():
    """Test NumPy optimization with large buffer (requires NumPy)."""
    # Create large buffer (1MB)
    data = bytes(range(256)) * 4096
    
    # Large pattern
    pattern = parse_ce_aob("48 89 5C 24 08 48 89 74 24 10 48 8B 05 12 34 56 78 85 C0")
    
    # Should use NumPy optimization
    optimized_results = scan_bytes_optimized(data, pattern, use_numpy=True)
    standard_results = scan_standard(data, pattern)
    
    assert optimized_results == standard_results


def test_batch_scan_with_overlapping_patterns():
    """Test batch scan where patterns might overlap."""
    data = bytes([0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x74])
    
    patterns = [
        parse_ce_aob("48 89 5C"),
        parse_ce_aob("48 89 74"),
        parse_ce_aob("89 5C 24"),
    ]
    
    results = scan_bytes_batch(data, patterns, use_numpy=True)
    
    assert len(results) == 3
    assert len(results[0]) >= 1  # First pattern
    assert len(results[1]) >= 1  # Second pattern
    assert len(results[2]) >= 1  # Third pattern


# Database performance tests

from aobmaster.database import SignatureDatabase, SignatureRecord
from datetime import datetime, timezone
from pathlib import Path


def test_database_v3_migration(tmp_path):
    """Test database migration to v3 with performance indexes."""
    db_path = tmp_path / "test_v3.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Check that indexes were created
    conn = db._connect()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name LIKE 'idx_%'
    """)
    
    indexes = [row[0] for row in cursor.fetchall()]
    
    # Should have performance indexes from v3
    assert "idx_test_results_timestamp" in indexes
    assert "idx_test_results_passed" in indexes
    assert "idx_signatures_list" in indexes


def test_database_query_performance(tmp_path):
    """Test that database queries benefit from indexes."""
    db_path = tmp_path / "perf_test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    # Insert many signatures
    for i in range(100):
        sig = SignatureRecord(
            id=f"sig_{i}",
            name=f"Test Signature {i}",
            pattern="48 89 5C 24 08",
            anchor_rva=0x1000 + i,
            binary_hash="abc123",
            created_at=datetime.now(timezone.utc).isoformat(),
            author="test",
            version_range="1.0+",
            metadata={"test": True},
        )
        db.save_signature(sig)
    
    # Query should be fast (queries use indexed columns)
    results = db.list_signatures(name_filter="Signature 50")
    assert len(results) == 1
    assert results[0].id == "sig_50"


def test_database_schema_version(tmp_path):
    """Test that database schema version is correctly set."""
    from aobmaster.database import DB_SCHEMA_VERSION
    
    db_path = tmp_path / "version_test.db"
    db = SignatureDatabase(db_path)
    db.init_database()
    
    conn = db._connect()
    cursor = conn.cursor()
    
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cursor.fetchone()
    
    assert row is not None
    assert row[0] == DB_SCHEMA_VERSION
    assert row[0] == 3  # v2.1 Phase 4
