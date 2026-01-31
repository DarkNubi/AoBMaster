"""
SDK Integration Tests (Phase 2 - v2.1)

Tests that verify all SDK classes work together correctly.
Uses real test binaries from conftest.py fixtures.
"""

import pytest
import json
from pathlib import Path
from aobmaster.sdk import (
    Synthesizer,
    SignatureDatabase,
    SignatureTester,
    TemporalAnalyzer,
    SynthesisConfig,
    SynthesisResult
)


def test_sdk_end_to_end_workflow(tmp_path, sample_binary):
    """
    Test complete SDK workflow: generate → save → test → analyze.
    
    This is the key integration test that validates all SDK components work together.
    """
    # Setup
    db_path = tmp_path / "test.db"
    
    # Step 1: Initialize database
    db = SignatureDatabase(db_path)
    db.init()
    
    # Step 2: Generate signature using SDK
    synth = Synthesizer(sample_binary)
    result = synth.generate(anchor_rva="0x1000")
    
    assert result.ok
    assert len(result.candidates) > 0
    
    # Step 3: Save signature to database
    top = result.get_top_candidate()
    assert top is not None
    
    db.save_signature(
        signature_id="test_sig_1",
        name="Test Signature",
        pattern=top["aob"],
        anchor_rva="0x1000",
        version_range="1.0.0+",
        metadata={"test": True}
    )
    
    # Step 4: Query signature back
    sig = db.query_signature("test_sig_1")
    assert sig is not None
    assert sig["id"] == "test_sig_1"
    assert sig["name"] == "Test Signature"
    assert sig["pattern"] == top["aob"]
    
    # Step 5: List signatures
    sigs = db.list_signatures()
    assert len(sigs) == 1
    assert sigs[0]["id"] == "test_sig_1"
    
    # Step 6: Test signature
    tester = SignatureTester(db_path)
    test_result = tester.test_signature(
        signature_id="test_sig_1",
        binary_path=sample_binary,
        record=True
    )
    
    assert test_result["passed"] is True
    assert test_result["match_count"] >= 1
    
    # Step 7: Temporal analysis
    analyzer = TemporalAnalyzer(db_path)
    analysis = analyzer.analyze_signature("test_sig_1")
    
    assert "pass_rate" in analysis
    assert "confidence_interval" in analysis
    

def test_sdk_database_operations(tmp_path):
    """Test SignatureDatabase CRUD operations."""
    db_path = tmp_path / "crud_test.db"
    db = SignatureDatabase(db_path)
    
    # Init
    db.init()
    assert db_path.exists()
    
    # Save
    db.save_signature(
        signature_id="sig1",
        name="Signature 1",
        pattern="48 8B ?? ?? 85 C0",
        anchor_rva="0x1234",
        metadata={"key": "value"}
    )
    
    db.save_signature(
        signature_id="sig2",
        name="Signature 2",
        pattern="90 90 90 90",
        anchor_rva="0x5678"
    )
    
    # Query
    sig1 = db.query_signature("sig1")
    assert sig1["id"] == "sig1"
    assert sig1["pattern"] == "48 8B ?? ?? 85 C0"
    
    # List
    all_sigs = db.list_signatures()
    assert len(all_sigs) == 2
    
    # List with filter
    filtered = db.list_signatures(filter_text="Signature 1")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "sig1"
    
    # Export/Import
    export_path = tmp_path / "export.json"
    db.export_signatures(export_path)
    assert export_path.exists()
    
    # Create new DB and import
    db2_path = tmp_path / "imported.db"
    db2 = SignatureDatabase(db2_path)
    db2.init()
    db2.import_signatures(export_path)
    
    imported_sigs = db2.list_signatures()
    assert len(imported_sigs) == 2


def test_sdk_signature_tester(tmp_path, sample_binary):
    """Test SignatureTester class."""
    db_path = tmp_path / "tester.db"
    
    # Setup database with signature
    db = SignatureDatabase(db_path)
    db.init()
    db.save_signature(
        signature_id="test_sig",
        name="Test",
        pattern="48 8B 05 ?? ?? ?? ??",  # Pattern that should match in test binary
        anchor_rva="0x1000"
    )
    
    # Test signature
    tester = SignatureTester(db_path)
    result = tester.test_signature(
        signature_id="test_sig",
        binary_path=sample_binary,
        record=True
    )
    
    assert "passed" in result
    assert "match_count" in result
    

def test_sdk_temporal_analyzer(tmp_path, sample_binary):
    """Test TemporalAnalyzer class."""
    db_path = tmp_path / "temporal.db"
    
    # Setup
    db = SignatureDatabase(db_path)
    db.init()
    db.save_signature(
        signature_id="temporal_sig",
        name="Temporal Test",
        pattern="48 8B 05 ?? ?? ?? ??",
        anchor_rva="0x1000"
    )
    
    # Record some test results
    tester = SignatureTester(db_path)
    tester.test_signature("temporal_sig", sample_binary, record=True)
    
    # Analyze
    analyzer = TemporalAnalyzer(db_path)
    analysis = analyzer.analyze_signature("temporal_sig")
    
    assert analysis is not None
    assert "pass_rate" in analysis
    assert "drift_analysis" in analysis
    assert "confidence_interval" in analysis
    
    # Test analyze_all
    all_analyses = analyzer.analyze_all()
    assert len(all_analyses) >= 1


def test_sdk_synthesis_with_versions(tmp_path, sample_binary):
    """Test synthesis with multiple binary versions."""
    # Create a copy as "version 2"
    version2 = tmp_path / "version2.exe"
    import shutil
    shutil.copy(sample_binary, version2)
    
    # Synthesize with versions
    synth = Synthesizer(sample_binary)
    result = synth.generate(
        anchor_rva="0x1000",
        version_binaries=[version2],
        profile="balanced"
    )
    
    assert result.ok
    assert len(result.alignment) == 2  # Base + 1 version
    

def test_sdk_synthesis_with_explain(tmp_path, sample_binary):
    """Test synthesis with explainability mode."""
    synth = Synthesizer(sample_binary)
    result = synth.generate(
        anchor_rva="0x1000",
        explain=True
    )
    
    assert result.ok
    assert result.trace is not None
    assert "events" in result.trace
    assert len(result.trace["events"]) > 0
    
    # Verify trace event types
    event_types = [e.get("event", e.get("type")) for e in result.trace["events"]]
    assert "anchor_resolution" in event_types


def test_sdk_synthesis_result_to_dict(tmp_path, sample_binary):
    """Test SynthesisResult to_dict() method."""
    synth = Synthesizer(sample_binary)
    result = synth.generate(anchor_rva="0x1000")
    
    # Convert to dict
    result_dict = result.to_dict()
    
    assert isinstance(result_dict, dict)
    assert "ok" in result_dict
    assert "version" in result_dict
    assert "candidates" in result_dict
    assert "warnings" in result_dict
    assert "errors" in result_dict
    
    # Verify JSON serializable
    json_str = json.dumps(result_dict)
    assert len(json_str) > 0


def test_sdk_synthesis_config_validation():
    """Test SynthesisConfig dataclass validation."""
    # Valid config
    config = SynthesisConfig(
        base_binary=Path("/path/to/binary.exe"),
        anchor_rva="0x1000",
        profile="balanced"
    )
    
    assert config.base_binary == Path("/path/to/binary.exe")
    assert config.anchor_rva == "0x1000"
    assert config.profile == "balanced"
    assert config.context_before == 8  # Default
    assert config.context_after == 8  # Default
    

def test_sdk_error_handling(tmp_path):
    """Test SDK error handling."""
    # Non-existent binary
    with pytest.raises(FileNotFoundError):
        Synthesizer("/nonexistent/binary.exe")
    
    # Non-existent signature
    db_path = tmp_path / "error_test.db"
    db = SignatureDatabase(db_path)
    db.init()
    
    sig = db.query_signature("nonexistent")
    assert sig is None  # Returns None, doesn't raise


def test_sdk_signature_families(tmp_path):
    """Test signature family relationships (Phase 5 feature)."""
    db_path = tmp_path / "families.db"
    db = SignatureDatabase(db_path)
    db.init()
    
    # Save parent signature
    db.save_signature(
        signature_id="parent_sig",
        name="Parent Signature",
        pattern="48 8B ?? ??",
        version_range="1.0-1.5"
    )
    
    # Save child signature with parent reference
    db.save_signature(
        signature_id="child_sig",
        name="Child Signature",
        pattern="48 8B ?? ?? ?? ??",
        version_range="1.6+",
        parent_id="parent_sig"
    )
    
    # Query child
    child = db.query_signature("child_sig")
    assert child is not None
    assert child["parent_id"] == "parent_sig"


def test_sdk_concurrent_access(tmp_path, sample_binary):
    """Test that multiple SDK instances can access same database."""
    db_path = tmp_path / "concurrent.db"
    
    # First instance
    db1 = SignatureDatabase(db_path)
    db1.init()
    db1.save_signature(
        signature_id="concurrent_sig",
        name="Concurrent Test",
        pattern="48 8B 05"
    )
    
    # Second instance
    db2 = SignatureDatabase(db_path)
    sig = db2.query_signature("concurrent_sig")
    assert sig is not None
    assert sig["name"] == "Concurrent Test"
    
    # Third instance (tester)
    tester = SignatureTester(db_path)
    result = tester.test_signature(
        signature_id="concurrent_sig",
        binary_path=sample_binary,
        record=True
    )
    
    assert "passed" in result


def test_sdk_metadata_handling(tmp_path):
    """Test metadata JSON serialization/deserialization."""
    db_path = tmp_path / "metadata.db"
    db = SignatureDatabase(db_path)
    db.init()
    
    # Complex metadata
    metadata = {
        "description": "Test signature with metadata",
        "tags": ["important", "stable"],
        "created_by": "test_user",
        "notes": {
            "version": "1.0",
            "tested_on": ["Windows 10", "Windows 11"]
        }
    }
    
    db.save_signature(
        signature_id="meta_sig",
        name="Metadata Test",
        pattern="90 90 90",
        metadata=metadata
    )
    
    # Retrieve and verify
    sig = db.query_signature("meta_sig")
    assert sig is not None
    
    # Metadata should be JSON string in DB, parse it
    if isinstance(sig.get("metadata"), str):
        parsed_meta = json.loads(sig["metadata"])
    else:
        parsed_meta = sig.get("metadata", {})
    
    assert parsed_meta.get("tags") == ["important", "stable"]
    assert parsed_meta["notes"]["version"] == "1.0"
