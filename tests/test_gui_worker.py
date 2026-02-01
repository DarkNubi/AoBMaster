from aobmaster.gui_worker import _handle_request, PROTOCOL_VERSION, _truncate_trace
from tests.conftest import build_minimal_pe64


def test_gui_worker_versions():
    request = {
        "jsonrpc": "2.0",
        "protocol_version": PROTOCOL_VERSION,
        "sdk_version": "2.0.0",
        "id": "1",
        "method": "system.versions",
        "params": {},
    }
    result = _handle_request(request)
    assert result["protocol_version"] == PROTOCOL_VERSION
    assert "sdk_version" in result


def test_gui_worker_trace_truncation(monkeypatch):
    monkeypatch.setenv("AOBMASTER_TRACE_LIMIT_BYTES", "10")
    trace = {"events": [{"data": "x" * 50}]}
    truncated = _truncate_trace(trace)
    assert truncated["truncated"] is True
    assert truncated["limit_bytes"] == 10
    assert truncated["original_size_bytes"] > truncated["limit_bytes"]


def test_gui_worker_synthesizer_generate(tmp_path):
    binary_path = tmp_path / "sample.exe"
    code = (
        b"\x48\x89\x5C\x24\x08"
        b"\x48\x89\x74\x24\x10"
        b"\x48\x8B\x05\x12\x34\x56\x78"
        b"\x85\xC0"
        + b"\x00" * 64
    )
    binary_path.write_bytes(build_minimal_pe64(text=code))
    request = {
        "jsonrpc": "2.0",
        "protocol_version": PROTOCOL_VERSION,
        "sdk_version": "2.0.0",
        "id": "1",
        "method": "synthesizer.generate",
        "params": {
            "base_binary": str(binary_path),
            "anchor_rva": "0x1000",
            "explain": False,
        },
    }
    result = _handle_request(request)
    assert result["ok"] is True
    assert result["candidates"]
