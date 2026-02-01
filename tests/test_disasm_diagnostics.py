from __future__ import annotations

import pytest

import aobmaster.disasm as disasm
from aobmaster.errors import AoBMasterError, ExitCode
from aobmaster.pe import PEFile

from .conftest import write_pe


def test_decode_anchor_context_failure_includes_diagnostics(tmp_path, monkeypatch):
    # Force decode_anchor_context() down its "best=None" failure path to verify
    # it includes structured diagnostics, without depending on specific x86 byte
    # sequences.
    base = write_pe(tmp_path, "t.exe", text=b"\x90" * 64)
    pe = PEFile(base)
    sec = pe.section_by_name(".text")
    assert sec is not None

    anchor_fo = sec.raw_ptr + 8

    monkeypatch.setattr(disasm, "resync_anchor_to_insn_start", lambda *_args, **_kwargs: (anchor_fo, None))
    monkeypatch.setattr(disasm, "_decode_stream_diag", lambda *_args, **_kwargs: ([], None))

    with pytest.raises(AoBMasterError) as ei:
        disasm.decode_anchor_context(
            pe,
            sec,
            anchor_fo=anchor_fo,
            context_before=8,
            context_after=8,
            max_context_insns=32,
        )

    err = ei.value
    assert err.code == ExitCode.DISASM_FAILURE
    assert err.kind == "disasm_failed"
    assert err.details is not None
    assert err.details.get("anchor_fo") == hex(anchor_fo)
    assert "attempts" in err.details
    assert "section" in err.details
