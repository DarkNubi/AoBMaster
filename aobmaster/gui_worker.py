from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__ as SDK_VERSION
from .errors import AoBMasterError
from .sdk import Synthesizer, SignatureDatabase, SignatureTester, TemporalAnalyzer


PROTOCOL_VERSION = "1.0"
DEFAULT_TRACE_LIMIT_BYTES = 10 * 1024 * 1024


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data:
            payload["data"] = self.data
        return payload


def _emit_response(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _trace_limit_bytes() -> int:
    try:
        return int(os.environ.get("AOBMASTER_TRACE_LIMIT_BYTES", DEFAULT_TRACE_LIMIT_BYTES))
    except ValueError:
        return DEFAULT_TRACE_LIMIT_BYTES


def _truncate_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    serialized = json.dumps(trace)
    limit = _trace_limit_bytes()
    if len(serialized.encode("utf-8")) <= limit:
        return trace
    truncated = serialized.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    return {
        "truncated": True,
        "limit_bytes": limit,
        "payload": truncated,
        "warning": "Trace payload exceeded size limit and was truncated.",
        "original_size_bytes": len(serialized.encode("utf-8")),
    }


def _normalize_paths(params: Dict[str, Any], keys: list[str]) -> Dict[str, Any]:
    out = dict(params)
    for key in keys:
        if key in out and out[key] is not None:
            out[key] = str(Path(out[key]))
    return out


def _handle_synthesizer_generate(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["base_binary"])
    synth = Synthesizer(params["base_binary"])
    call_params = dict(params)
    call_params.pop("base_binary", None)
    result = synth.generate(**call_params)
    result_dict = result.to_dict()
    if result_dict.get("trace"):
        result_dict["trace"] = _truncate_trace(result_dict["trace"])
    return result_dict


def _handle_database_init(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    db = SignatureDatabase(params["db_path"])
    db.init()
    return {"ok": True}


def _handle_database_save(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    db = SignatureDatabase(params["db_path"])
    db.save_signature(
        signature_id=params["signature_id"],
        name=params["name"],
        pattern=params["pattern"],
        anchor_rva=params.get("anchor_rva"),
        binary_hash=params.get("binary_hash"),
        author=params.get("author"),
        version_range=params.get("version_range"),
        metadata=params.get("metadata"),
        parent_id=params.get("parent_id"),
    )
    return {"ok": True}


def _handle_database_query(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    db = SignatureDatabase(params["db_path"])
    return {"signature": db.query_signature(params["signature_id"])}


def _handle_database_list(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    db = SignatureDatabase(params["db_path"])
    return {"signatures": db.list_signatures(params.get("filter_text"))}


def _handle_database_export(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path", "output_path"])
    db = SignatureDatabase(params["db_path"])
    db.export_signatures(params["output_path"])
    return {"ok": True}


def _handle_database_import(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path", "input_path"])
    db = SignatureDatabase(params["db_path"])
    db.import_signatures(params["input_path"])
    return {"ok": True}


def _handle_database_deprecate(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    db = SignatureDatabase(params["db_path"])
    db.deprecate_signature(params["signature_id"], params["reason"])
    return {"ok": True}


def _handle_tester_signature(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path", "binary_path"])
    tester = SignatureTester(params["db_path"])
    result = tester.test_signature(
        signature_id=params["signature_id"],
        binary_path=params["binary_path"],
        record=bool(params.get("record", False)),
    )
    return {"result": result}


def _handle_tester_all(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    tester = SignatureTester(params["db_path"])
    result = tester.test_all(
        corpus_pattern=params["corpus_pattern"],
        signature_id=params.get("signature_id"),
        parallel=int(params.get("parallel", 1)),
        record=bool(params.get("record", False)),
    )
    return {"result": result}


def _handle_analyzer_signature(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    analyzer = TemporalAnalyzer(params["db_path"])
    return {"analysis": analyzer.analyze_signature(params["signature_id"])}


def _handle_analyzer_all(params: Dict[str, Any]) -> Dict[str, Any]:
    params = _normalize_paths(params, ["db_path"])
    analyzer = TemporalAnalyzer(params["db_path"])
    return {"analyses": analyzer.analyze_all()}


def _handle_system_versions(_: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "sdk_version": SDK_VERSION,
    }


METHODS = {
    "synthesizer.generate": _handle_synthesizer_generate,
    "database.init": _handle_database_init,
    "database.save_signature": _handle_database_save,
    "database.query_signature": _handle_database_query,
    "database.list_signatures": _handle_database_list,
    "database.export_signatures": _handle_database_export,
    "database.import_signatures": _handle_database_import,
    "database.deprecate_signature": _handle_database_deprecate,
    "tester.test_signature": _handle_tester_signature,
    "tester.test_all": _handle_tester_all,
    "analyzer.analyze_signature": _handle_analyzer_signature,
    "analyzer.analyze_all": _handle_analyzer_all,
    "system.versions": _handle_system_versions,
}


def _handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    if request.get("jsonrpc") != "2.0":
        raise JsonRpcError(code=-32600, message="Invalid JSON-RPC version.")
    protocol_version = request.get("protocol_version")
    if protocol_version != PROTOCOL_VERSION:
        raise JsonRpcError(
            code=-32010,
            message="Incompatible protocol version.",
            data={"expected": PROTOCOL_VERSION, "received": protocol_version},
        )
    sdk_version = request.get("sdk_version")
    if sdk_version and sdk_version.split(".")[0] != SDK_VERSION.split(".")[0]:
        raise JsonRpcError(
            code=-32011,
            message="Incompatible SDK version.",
            data={"expected": SDK_VERSION, "received": sdk_version},
        )
    method = request.get("method")
    if method not in METHODS:
        raise JsonRpcError(code=-32601, message=f"Method not found: {method}")
    params = request.get("params") or {}
    return METHODS[method](params)


def _emit_error_response(request_id: Any, error: JsonRpcError) -> None:
    _emit_response(
        {
            "jsonrpc": "2.0",
            "protocol_version": PROTOCOL_VERSION,
            "sdk_version": SDK_VERSION,
            "id": request_id,
            "error": error.to_dict(),
        }
    )


def _emit_exception_response(request_id: Any, exc: Exception) -> None:
    if isinstance(exc, AoBMasterError):
        error = JsonRpcError(code=-32000, message=exc.message, data=exc.to_dict())
        _emit_error_response(request_id, error)
        return
    error = JsonRpcError(
        code=-32001,
        message=str(exc),
        data={"traceback": traceback.format_exc()},
    )
    _emit_error_response(request_id, error)


def main() -> None:
    for raw_line in sys.stdin:
        if not raw_line.strip():
            continue
        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _emit_error_response(None, JsonRpcError(code=-32700, message=f"Parse error: {exc}"))
            continue
        request_id = request.get("id")
        try:
            result = _handle_request(request)
            _emit_response(
                {
                    "jsonrpc": "2.0",
                    "protocol_version": PROTOCOL_VERSION,
                    "sdk_version": SDK_VERSION,
                    "id": request_id,
                    "result": result,
                }
            )
        except JsonRpcError as exc:
            _emit_error_response(request_id, exc)
        except Exception as exc:
            _emit_exception_response(request_id, exc)


if __name__ == "__main__":
    main()
