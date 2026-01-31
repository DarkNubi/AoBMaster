from __future__ import annotations

import sys
from typing import Any

from .util import stable_json_dumps


def emit_json(obj: Any) -> None:
    sys.stdout.write(stable_json_dumps(obj))
    sys.stdout.write("\n")


def emit_text(lines: list[str]) -> None:
    for line in lines:
        sys.stdout.write(line)
        sys.stdout.write("\n")

