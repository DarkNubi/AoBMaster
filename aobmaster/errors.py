from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_ARGS = 1
    ANCHOR_FAILURE = 2
    DISASM_FAILURE = 3
    ALIGNMENT_FAILURE = 4
    INTERNAL_ERROR = 5


@dataclass(frozen=True)
class AoBMasterError(Exception):
    code: ExitCode
    kind: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


@dataclass(frozen=True)
class AoBMasterWarning:
    kind: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out

