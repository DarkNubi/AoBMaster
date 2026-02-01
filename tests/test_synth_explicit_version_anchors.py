from __future__ import annotations

import json
import subprocess
import sys

from .conftest import write_pe


def test_synth_with_explicit_version_anchors(tmp_path):
    base_code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    version_code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 55 66 77 88 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=base_code)
    version = write_pe(tmp_path, "ver.exe", text=(b"\x90" * 0x100) + version_code)

    versions_map = tmp_path / "anchors.json"
    versions_map.write_text(
        json.dumps(
            {"versions": [{"path": str(version), "anchor_rva": "0x1100"}]},
            indent=2,
        ),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base",
        str(base),
        "--anchor-rva",
        "0x1000",
        "--versions-map",
        str(versions_map),
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    assert out["ok"] is True
    assert out["alignment"][1]["anchor"]["rva"] == "0x1100"
    valid = [c for c in out["candidates"] if c.get("valid")]
    assert valid, "expected valid candidates with explicit anchors"
