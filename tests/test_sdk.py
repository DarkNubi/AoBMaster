"""
Tests for SDK (Phase 1 - v2.1)

These tests verify that the SDK works programmatically after synth.py refactoring.
"""

import pytest
from pathlib import Path
from aobmaster.sdk import Synthesizer, SynthesisResult, SynthesisConfig
from .conftest import build_minimal_pe64


def test_sdk_synthesizer_basic(tmp_path):
    """Test basic SDK synthesis using Synthesizer class."""
    # Create a minimal test binary using proper PE builder
    test_bin = tmp_path / "test.exe"
    
    # Code section with recognizable pattern
    code = (
        b"\x48\x89\x5C\x24\x08"          # mov [rsp+8], rbx
        b"\x48\x89\x74\x24\x10"          # mov [rsp+10], rsi
        b"\x48\x8B\x05\x12\x34\x56\x78"  # mov rax, [rip+0x78563412] <-- anchor here
        b"\x85\xC0"                      # test eax, eax
        + b"\x00" * 480                  # Padding
    )
    
    # Write proper PE file
    test_bin.write_bytes(build_minimal_pe64(text=code))
    
    # Test SDK
    synth = Synthesizer(test_bin)
    
    # RVA of the "mov rax, [rip+...]" instruction
    anchor_rva = 0x1000 + 10  # VirtualAddress + offset in code
    
    result = synth.generate(anchor_rva=hex(anchor_rva))
    
    # Verify result structure
    assert isinstance(result, SynthesisResult)
    assert result.ok == True
    assert result.version == "2.0.0"
    assert len(result.candidates) > 0
    
    # Verify we can get top pattern
    top_pattern = result.get_top_pattern()
    assert top_pattern is not None
    assert "48 8B" in top_pattern  # Should contain mov rax opcode


def test_sdk_synthesis_result_methods(tmp_path):
    """Test SynthesisResult helper methods."""
    # Create test binary using proper PE builder
    test_bin = tmp_path / "test.exe"
    code = (
        b"\x48\x89\x5C\x24\x08"          # mov [rsp+8], rbx
        b"\x48\x89\x74\x24\x10"          # mov [rsp+10], rsi
        b"\x48\x8B\x05\x12\x34\x56\x78"  # mov rax, [rip+0x78563412]
        b"\x85\xC0"                      # test eax, eax
        + b"\x00" * 480                  # Padding
    )
    
    test_bin.write_bytes(build_minimal_pe64(text=code))
    
    synth = Synthesizer(test_bin)
    result = synth.generate(anchor_rva="0x100A")
    
    # Test get_top_candidate()
    top = result.get_top_candidate()
    assert top is not None
    assert top.get("valid") == True
    assert "aob" in top
    
    # Test get_top_pattern()
    pattern = result.get_top_pattern()
    assert pattern is not None
    assert isinstance(pattern, str)
    
    # Test to_dict()
    result_dict = result.to_dict()
    assert isinstance(result_dict, dict)
    assert "ok" in result_dict
    assert "candidates" in result_dict


def test_sdk_with_explain_mode(tmp_path):
    """Test SDK with explainability mode enabled."""
    test_bin = tmp_path / "test.exe"
    code = (
        b"\x48\x89\x5C\x24\x08"          # mov [rsp+8], rbx
        b"\x48\x89\x74\x24\x10"          # mov [rsp+10], rsi
        b"\x48\x8B\x05\x12\x34\x56\x78"  # mov rax, [rip+0x78563412]
        b"\x85\xC0"                      # test eax, eax
        + b"\x00" * 480                  # Padding
    )
    
    test_bin.write_bytes(build_minimal_pe64(text=code))
    
    synth = Synthesizer(test_bin)
    result = synth.generate(anchor_rva="0x100A", explain=True)
    
    # Verify trace data is present
    assert result.trace is not None
    assert "events" in result.trace
    assert len(result.trace["events"]) > 0


def test_sdk_config_dataclass():
    """Test SynthesisConfig dataclass creation."""
    config = SynthesisConfig(
        base_binary="/path/to/binary.exe",
        anchor_rva="0x1000",
        profile="balanced",
        explain=True,
    )
    
    assert config.base_binary == "/path/to/binary.exe"
    assert config.anchor_rva == "0x1000"
    assert config.profile == "balanced"
    assert config.explain == True
    assert config.context_before == 8  # default value


def test_sdk_error_handling(tmp_path):
    """Test SDK error handling for invalid inputs."""
    # Test with non-existent binary
    with pytest.raises(FileNotFoundError):
        Synthesizer("/nonexistent/binary.exe")
    
    # Test with missing anchor
    test_bin = tmp_path / "test.exe"
    dos_stub = b"MZ" + b"\x90" * 58 + b"\x80\x00\x00\x00"
    pe_header = (
        b"PE\x00\x00" + b"\x64\x86" + b"\x01\x00" + b"\x00" * 12 +
        b"\xF0\x00" + b"\x22\x00" + b"\x0B\x02" + b"\x00" * 222
    )
    section_header = (
        b".text\x00\x00\x00" + b"\x00\x10\x00\x00" + b"\x00\x10\x00\x00" +
        b"\x00\x02\x00\x00" + b"\x00\x02\x00\x00" + b"\x00" * 12 + b"\x20\x00\x00\x60"
    )
    code = b"\x90" * 512
    
    with open(test_bin, "wb") as f:
        f.write(dos_stub + pe_header + section_header + code)
    
    synth = Synthesizer(test_bin)
    
    # Test without any anchor specified
    from aobmaster.errors import AoBMasterError
    with pytest.raises(AoBMasterError):
        result = synth.generate()  # No anchor specified
