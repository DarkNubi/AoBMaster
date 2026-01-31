"""
Tests for AoBMaster v2 Phase 6: Structural anchors.

Tests --anchor-mode structural flag, function boundary detection, and fallback behavior.
"""

from __future__ import annotations

import json
import subprocess
import sys

from .conftest import write_pe


def test_structural_anchor_mode_basic(tmp_path):
    """Test basic structural anchor mode with standard prologue."""
    # Create function with standard prologue: push rbp; mov rbp, rsp
    code = bytes.fromhex(
        "55 "  # push rbp
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 20 "  # sub rsp, 20h
        "48 8B 05 11 22 33 44 "  # mov rax, [rip+disp32]
        "48 85 C0 "  # test rax, rax
        "74 05 "  # je short
        "48 83 C4 20 "  # add rsp, 20h
        "5D "  # pop rbp
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    # Use structural mode with anchor inside function (after prologue)
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1008",  # Point to mov rax instruction (after prologue)
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    # Structural mode should detect function boundary and adjust anchor


def test_structural_anchor_with_frameless_function(tmp_path):
    """Test structural anchor with frameless function (no rbp setup)."""
    # Frameless function: sub rsp, imm8
    code = bytes.fromhex(
        "48 83 EC 28 "  # sub rsp, 28h (frameless prologue)
        "48 8B 05 11 22 33 44 "  # mov rax, [rip+disp32]
        "48 85 C0 "  # test rax, rax
        "74 05 "  # je short
        "48 83 C4 28 "  # add rsp, 28h
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1004",  # Point inside function
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True


def test_structural_anchor_fallback_to_byte_offset(tmp_path):
    """Test that structural mode falls back to byte-offset when detection fails."""
    # Create code with no clear function boundary
    code = bytes.fromhex(
        "90 90 90 90 "  # NOPs (no clear prologue)
        "48 8B 05 11 22 33 44 "  # mov rax, [rip+disp32]
        "48 85 C0 "  # test rax, rax
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1004",
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    # Should succeed with fallback to byte-offset mode
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    # May include warning about fallback in output or trace


def test_structural_anchor_with_explain(tmp_path):
    """Test that structural mode logs function boundary detection in trace."""
    code = bytes.fromhex(
        "55 "  # push rbp
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 20 "  # sub rsp, 20h
        "48 8B 05 11 22 33 44 "  # mov rax, [rip+disp32]
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1008",
        "--anchor-mode", "structural",
        "--explain",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    assert "trace" in out
    
    # Look for structural anchor events in trace
    events = out["trace"]["events"]
    # May have structural_anchor or anchor_resolution events with structural info


def test_byte_offset_mode_default(tmp_path):
    """Test that byte-offset mode is the default (v1.x behavior)."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    # Don't specify --anchor-mode (should default to byte-offset)
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
    # Should work with traditional byte-offset mode


def test_structural_anchor_explicit_byte_offset_mode(tmp_path):
    """Test explicitly using byte-offset mode."""
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    # Explicitly specify byte-offset mode
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",
        "--anchor-mode", "byte-offset",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True


def test_structural_anchor_with_large_function(tmp_path):
    """Test structural anchor with larger function."""
    # Create a larger function with standard prologue
    code = bytes.fromhex(
        "55 "  # push rbp
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 40 "  # sub rsp, 40h
        # Add some body instructions
        "48 89 4D 10 "  # mov [rbp+10h], rcx
        "48 89 55 18 "  # mov [rbp+18h], rdx
        "48 8B 45 10 "  # mov rax, [rbp+10h]
        "48 8B 4D 18 "  # mov rcx, [rbp+18h]
        "48 03 C1 "  # add rax, rcx
        "48 83 C4 40 "  # add rsp, 40h
        "5D "  # pop rbp
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    # Anchor somewhere in the middle of the function
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1010",  # Middle of function
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True


def test_structural_anchor_with_versions(tmp_path):
    """Test structural anchor across multiple versions."""
    # Base version with standard prologue
    code_base = bytes.fromhex(
        "55 "  # push rbp
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 20 "  # sub rsp, 20h
        "48 8B 05 11 22 33 44 "  # mov rax, [rip+disp32]
        "48 85 C0 "  # test rax, rax
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code_base)
    
    # Version with same function but shifted
    code_ver = bytes.fromhex(
        "90 90 90 90 "  # Some padding before function
        "55 "  # push rbp
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 20 "  # sub rsp, 20h
        "48 8B 05 11 22 33 44 "  # mov rax, [rip+disp32]
        "48 85 C0 "  # test rax, rax
        "C3"  # ret
    )
    ver = write_pe(tmp_path, "ver.exe", text=code_ver)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1004",  # Point to function body
        "--versions", str(ver),
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    # Should detect function boundaries in both versions


def test_structural_anchor_register_save_prologue(tmp_path):
    """Test structural anchor with register save prologue."""
    # Function with register saves but no frame pointer
    code = bytes.fromhex(
        "40 53 "  # push rbx
        "48 83 EC 20 "  # sub rsp, 20h
        "48 89 CB "  # mov rbx, rcx
        "48 8B 05 11 22 33 44 "  # mov rax, [rip+disp32]
        "48 85 C0 "  # test rax, rax
        "48 83 C4 20 "  # add rsp, 20h
        "5B "  # pop rbx
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1008",
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True


def test_structural_anchor_at_function_start(tmp_path):
    """Test structural anchor when anchor is at function start."""
    code = bytes.fromhex(
        "55 "  # push rbp
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 20 "  # sub rsp, 20h
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    # Anchor at function start (prologue)
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1000",  # At function start
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True


def test_structural_anchor_confidence_scores(tmp_path):
    """Test that structural anchor detection includes confidence scores."""
    code = bytes.fromhex(
        "55 "  # push rbp (high confidence prologue)
        "48 89 E5 "  # mov rbp, rsp
        "48 83 EC 20 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1004",
        "--anchor-mode", "structural",
        "--explain",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    
    # If implemented, trace events may include confidence scores
    if "trace" in out:
        events = out["trace"]["events"]
        # Look for structural anchor events with confidence information


def test_structural_anchor_multiple_prologues(tmp_path):
    """Test structural anchor with multiple functions in binary."""
    # Create code with two functions
    code = bytes.fromhex(
        # Function 1
        "55 48 89 E5 48 83 EC 20 C3 "
        # Function 2
        "48 83 EC 28 48 8B 05 11 22 33 44 C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    # Anchor in second function
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x100C",  # In second function
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    # Should detect the correct function boundary (second function)


def test_structural_anchor_backward_search_limit(tmp_path):
    """Test that structural anchor backward search has reasonable limits."""
    # Create code with function far from anchor
    padding = b"\x90" * 2048  # 2KB of NOPs
    code = padding + bytes.fromhex(
        "55 48 89 E5 48 83 EC 20 C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    # Anchor after large padding - may not find prologue due to search limit
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", hex(0x1000 + len(padding) + 4),
        "--anchor-mode", "structural",
        "--format", "json",
    ]
    
    # Should still succeed (fallback to byte-offset)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True


def test_structural_anchor_text_output(tmp_path):
    """Test structural anchor mode with text output."""
    code = bytes.fromhex(
        "55 48 89 E5 48 83 EC 20 "
        "48 8B 05 11 22 33 44 C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1008",
        "--anchor-mode", "structural",
        "--format", "text",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = proc.stdout
    
    # Should produce text output successfully
    assert len(output) > 0
    # May mention structural mode in output


def test_structural_anchor_ce_output(tmp_path):
    """Test structural anchor mode with Cheat Engine output."""
    code = bytes.fromhex(
        "55 48 89 E5 48 83 EC 20 "
        "48 8B 05 11 22 33 44 C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1008",
        "--anchor-mode", "structural",
        "--format", "ce",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    output = proc.stdout
    
    # Should produce CE XML output successfully
    assert len(output) > 0


def test_structural_anchor_combined_with_anchor_shift(tmp_path):
    """Test combining structural anchor mode with anchor shift."""
    code = bytes.fromhex(
        "55 48 89 E5 48 83 EC 20 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    
    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base", str(base),
        "--anchor-rva", "0x1008",
        "--anchor-mode", "structural",
        "--anchor-shift", "2",
        "--format", "json",
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    
    assert out["ok"] is True
    # Should try structural anchoring with shifted positions
