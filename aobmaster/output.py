from __future__ import annotations

import sys
from typing import Any

from .util import stable_json_dumps


def _safe_write(s: str) -> None:
    try:
        sys.stdout.write(s)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write(s.encode(enc, errors="backslashreplace"))


def emit_json(obj: Any) -> None:
    _safe_write(stable_json_dumps(obj))
    _safe_write("\n")


def emit_text(lines: list[str]) -> None:
    for line in lines:
        _safe_write(line)
        _safe_write("\n")

