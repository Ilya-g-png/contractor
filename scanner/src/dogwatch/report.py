import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from dogwatch.config import DogwatchConfig
from dogwatch.diagnostics import (
    EXIT_ERROR,
    EXIT_GATE_FAILED,
    EXIT_OK,
    Diagnostic,
    Severity,
)

SCHEMA_VERSION = "0.2"
SCANNER_NAME = "dogwatch"

Status = Literal["pass", "fail", "inconclusive"]

_EXIT_CODES: dict[Status, int] = {
    "pass": EXIT_OK,
    "fail": EXIT_GATE_FAILED,
    "inconclusive": EXIT_ERROR,
}


@dataclass(frozen=True)
class Locator:
    path: str
    line: int | None = None
    column: int | None = None
    source_module: str | None = None
    target_module: str | None = None


@dataclass(frozen=True)
class Finding:
    source: str
    check_id: str
    severity: Severity
    message: str
    fingerprint: str
    locator: Locator
    waiver: None = None


def derive_status(
    findings: Sequence[Finding], diagnostics: Sequence[Diagnostic]
) -> Status:
    if any(d.severity == "error" for d in diagnostics):
        return "inconclusive"
    if any(f.severity == "error" and f.waiver is None for f in findings):
        return "fail"
    return "pass"


def exit_code_for_status(status: Status) -> int:
    return _EXIT_CODES[status]


def build_report(
    cfg: DogwatchConfig,
    version: str,
    findings: Sequence[Finding] = (),
    diagnostics: Sequence[Diagnostic] = (),
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": derive_status(findings, diagnostics),
        "scanner": {"name": SCANNER_NAME, "version": version},
        "policy": {
            "path": os.path.basename(cfg.path_arg),
            "digest": {"sha256": hashlib.sha256(cfg.raw).hexdigest()},
        },
        "findings": [_finding_json(f) for f in _sort_findings(findings)],
        "diagnostics": [_diagnostic_json(d) for d in sort_diagnostics(diagnostics)],
    }


def _sort_findings(findings: Sequence[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (
            f.locator.path,
            f.locator.line or 0,
            f.locator.column or 0,
            f.check_id,
            f.fingerprint,
            f.source,
        ),
    )


def sort_diagnostics(diagnostics: Sequence[Diagnostic]) -> list[Diagnostic]:
    return sorted(diagnostics, key=lambda d: (d.source, d.id, d.message))


def _finding_json(finding: Finding) -> dict[str, Any]:
    return {
        "source": finding.source,
        "check_id": finding.check_id,
        "severity": finding.severity,
        "message": finding.message,
        "fingerprint": finding.fingerprint,
        "waiver": None,
        "locator": _locator_json(finding.locator),
    }


def _locator_json(locator: Locator) -> dict[str, Any]:
    optional = {
        "line": locator.line,
        "column": locator.column,
        "source_module": locator.source_module,
        "target_module": locator.target_module,
    }
    return {"path": locator.path} | {k: v for k, v in optional.items() if v is not None}


def _diagnostic_json(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "source": diagnostic.source,
        "id": diagnostic.id,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
    }


def serialize_canonical(obj: Any) -> bytes:
    return (
        json.dumps(
            obj, sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": ")
        )
        + "\n"
    ).encode("utf-8")
