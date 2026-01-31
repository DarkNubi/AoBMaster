from __future__ import annotations

from aobmaster.matcher import parse_ce_aob, scan_bytes


def test_masked_scan():
    buf = bytes.fromhex("48 8B 05 11 22 33 44 85 C0 74 05")
    pat = parse_ce_aob("48 8B 05 ?? ?? ?? ?? 85 C0 74 ??")
    hits = scan_bytes(buf, pat)
    assert hits == [0]

