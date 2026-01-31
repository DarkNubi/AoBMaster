from __future__ import annotations

import json
import subprocess
import sys

from .conftest import write_pe


def test_synth_known_anchor_unique_aob(tmp_path):
    # 6 instructions total (meets default min-insns=6)
    code = bytes.fromhex(
        "48 83 EC 28 "  # sub rsp,28h
        "48 8B 05 11 22 33 44 "  # mov rax,[rip+disp32] (disp32 wildcarded)
        "48 85 C0 "  # test rax,rax
        "74 05 "  # je short (imm8 wildcarded)
        "48 83 C4 28 "  # add rsp,28h
        "C3"  # ret
    )
    base = write_pe(tmp_path, "base.exe", text=code)

    # Shift the same code by 0x100 bytes inside .text to exercise bytespan alignment and drift.
    ver = write_pe(tmp_path, "ver.exe", text=(b"\x90" * 0x100) + code)

    cmd = [
        sys.executable,
        "-m",
        "aobmaster",
        "synth",
        "--base",
        str(base),
        "--anchor-rva",
        "0x1000",
        "--versions",
        str(ver),
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    assert out["ok"] is True

    valid = [c for c in out["candidates"] if c.get("valid")]
    assert valid, "expected at least one valid candidate"
    top = valid[0]
    assert top["matches"][str(base)]["count"] == 1
    assert top["matches"][str(ver)]["count"] >= 1

