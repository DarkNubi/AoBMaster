"""
Tests for AoBMaster v2 Phase 1: Explainability (--explain flag).

Tests that --explain adds trace events to output and maintains backward compatibility.
"""

from __future__ import annotations

import json
import subprocess
import sys

from .conftest import write_pe


def test_explain_flag_adds_trace_events(tmp_path):
    """Test that --explain flag adds trace events to JSON output."""
    code = bytes.fromhex(
        "48 83 EC 28 "  # sub rsp,28h
        "48 8B 05 11 22 33 44 "  # mov rax,[rip+disp32]
        "48 85 C0 "  # test rax,rax
        "74 05 "  # je short
        "48 83 C4 28 "  # add rsp,28h
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--format", "json",
        "--explain",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    assert "trace" in out, "Expected trace field in output when --explain is used"
    
    trace = out["trace"]
    assert trace["enabled"] is True
    assert "event_count" in trace
    assert "events" in trace
    assert trace["event_count"] > 0, "Expected at least one trace event"
    assert len(trace["events"]) == trace["event_count"]


def test_explain_trace_event_structure(tmp_path):
    """Test that trace events contain expected fields."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--format", "json",
        "--explain",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    events = out["trace"]["events"]
    assert len(events) > 0
    
    # Check that each event has required fields
    for event in events:
        assert "event" in event
        assert "phase" in event
        assert "description" in event
        assert "details" in event
        assert isinstance(event["details"], dict)


def test_explain_anchor_resolution_event(tmp_path):
    """Test that anchor resolution events are captured."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--format", "json",
        "--explain",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    events = out["trace"]["events"]
    
    # Find anchor resolution event
    anchor_events = [e for e in events if e["event"] == "anchor_resolution"]
    assert len(anchor_events) > 0, "Expected anchor_resolution event"
    
    event = anchor_events[0]
    assert event["phase"] == "anchor_resolution"
    assert "resolved" in event["details"]
    assert "fo" in event["details"]["resolved"]
    assert "rva" in event["details"]["resolved"]


def test_explain_wildcarding_events(tmp_path):
    """Test that wildcarding decisions are captured (if implemented)."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "  # Has displacement that gets wildcarded
        "48 85 C0 "
        "74 05 "  # Has imm8 that gets wildcarded
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--format", "json",
        "--explain",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    events = out["trace"]["events"]
    
    # Find wildcarding events (may not be fully implemented yet)
    wildcard_events = [e for e in events if e["event"] == "wildcarding"]
    
    # If wildcarding events are implemented, check their structure
    if len(wildcard_events) > 0:
        for event in wildcard_events:
            assert event["phase"] == "normalization"
            assert "instruction_asm" in event["details"]
            assert "byte_positions" in event["details"]
            assert "reason" in event["details"]


def test_explain_scoring_events(tmp_path):
    """Test that scoring breakdown is captured."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--format", "json",
        "--explain",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    events = out["trace"]["events"]
    
    # Find scoring events
    scoring_events = [e for e in events if e["event"] == "scoring"]
    assert len(scoring_events) > 0, "Expected scoring events"
    
    event = scoring_events[0]
    assert event["phase"] == "scoring"
    assert "factors" in event["details"]
    
    factors = event["details"]["factors"]
    assert "uniqueness" in factors
    assert "presence" in factors
    assert "specificity" in factors
    assert "length_reg" in factors
    assert "anchor_prox" in factors
    
    assert "final_score" in event["details"]
    assert "confidence" in event["details"]


def test_backward_compatibility_no_explain(tmp_path):
    """Test that without --explain, output works as before (no trace field)."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    # Without --explain, trace field should not exist OR should be disabled
    if "trace" in out:
        assert out["trace"]["enabled"] is False
        assert out["trace"]["event_count"] == 0


def test_explain_with_versions(tmp_path):
    """Test that --explain captures alignment events across versions."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    ver = write_pe(tmp_path, "ver.exe", text=(b"\x90" * 0x50) + code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--versions", str(ver),
        "--format", "json",
        "--explain",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    events = out["trace"]["events"]
    
    # Find alignment events
    alignment_events = [e for e in events if e["event"] == "alignment"]
    assert len(alignment_events) > 0, "Expected alignment events with versions"
    
    event = alignment_events[0]
    assert event["phase"] == "alignment"
    assert "version_path" in event["details"]
    assert "drift" in event["details"]


def test_explain_with_multiple_candidates(tmp_path):
    """Test that --explain captures events for multiple candidates."""
    # Longer code to generate multiple candidates
    code = bytes.fromhex(
        "48 83 EC 28 "  # sub rsp,28h
        "48 8B 05 11 22 33 44 "  # mov rax,[rip+disp32]
        "48 85 C0 "  # test rax,rax
        "74 05 "  # je short
        "48 83 C4 28 "  # add rsp,28h
        "C3 "  # ret
        "90 90 90 90 "  # padding
        "55 "  # push rbp
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 20 "  # sub rsp, 20h
        "C9 "  # leave
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--format", "json",
        "--explain",
        "--context-variations", "on",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    # Should have scoring events for multiple candidates
    events = out["trace"]["events"]
    scoring_events = [e for e in events if e["event"] == "scoring"]
    
    # With context variations, should generate multiple candidates
    assert len(scoring_events) > 1, "Expected scoring events for multiple candidates"
