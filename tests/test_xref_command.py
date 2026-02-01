from __future__ import annotations

import json
import subprocess
import sys

from .conftest import write_pe


def test_xref_call_jmp(tmp_path):
    code = bytes.fromhex(
        "E8 1B 00 00 00 "
        "90 90 90 "
        "E9 13 00 00 00 "
        "90 90 90 90 90 "
        "90 90 90 90 90 "
        "90 90 90 90 90 "
        "90 90 90 90 "
        "C3"
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "xref",
        "--file",
        str(base),
        "--to-rva",
        "0x1020",
        "--type",
        "all",
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    assert out["ok"] is True
    refs = out["refs"]
    assert len(refs) == 2
    assert refs[0]["from_rva"] == "0x1000"
    assert refs[1]["from_rva"] == "0x1008"
