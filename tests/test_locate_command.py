from __future__ import annotations

import json
import subprocess
import sys

from .conftest import write_pe


def test_locate_finds_shifted_anchor(tmp_path):
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    target = write_pe(tmp_path, "target.exe", text=(b"\x90" * 0x80) + code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "locate",
        "--base",
        str(base),
        "--anchor-rva",
        "0x1000",
        "--target",
        str(target),
        "--top-n",
        "3",
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    assert out["ok"] is True
    results = out["targets"][0]["results"]
    assert results, "expected at least one locate result"
    assert results[0]["target_rva"] == "0x1080"


def test_locate_penalizes_multiple_hits(tmp_path):
    code = bytes.fromhex(
        "48 83 EC 28 "
        "48 8B 05 11 22 33 44 "
        "48 85 C0 "
        "74 05 "
        "48 83 C4 28 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)
    target = write_pe(tmp_path, "target.exe", text=code + (b"\x90" * 0x40) + code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "locate",
        "--base",
        str(base),
        "--anchor-rva",
        "0x1000",
        "--target",
        str(target),
        "--allow-multiple",
        "--profile",
        "minimal",
        "--candidate-limit",
        "3",
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    results = out["targets"][0]["results"]
    assert results, "expected locate results"
    assert any(r["match_count"] > 1 for r in results)
