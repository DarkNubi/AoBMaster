from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json_dumps(obj: Any) -> str:
    # Use ASCII-only JSON for portability on Windows consoles/pipes.
    # Non-ASCII characters are escaped as \\uXXXX, preventing UnicodeEncodeError
    # when stdout is using a legacy code page.
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, indent=2)


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def round6(x: float) -> float:
    return float(f"{x:.6f}")


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out

