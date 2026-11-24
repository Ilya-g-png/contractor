import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Diagnostic, Severity
from dogwatch.report import Finding, Locator, OpenApiProvenance

_METHODS = frozenset(
    {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)
_TOOL_FINGERPRINT = re.compile(r"[0-9a-f]{12}\Z")
_LEVELS: dict[int, Severity] = {1: "info", 2: "warning", 3: "error"}


@dataclass(frozen=True)
class NormalizationResult:
    findings: tuple[Finding, ...]
    diagnostics: tuple[Diagnostic, ...]


def normalize_openapi_changes(
    contract: OpenApiContractDecl,
    records: Sequence[Mapping[str, object]],
    provenance: OpenApiProvenance,
) -> NormalizationResult:
    findings: list[Finding] = []
    try:
        for record in records:
            check_id = record["id"]
            message = record["text"]
            level = record["level"]
            tool_identity = record["fingerprint"]
            if (
                not isinstance(check_id, str)
                or not check_id
                or not isinstance(message, str)
                or not message
                or type(level) is not int
                or level not in _LEVELS
                or not isinstance(tool_identity, str)
                or _TOOL_FINGERPRINT.fullmatch(tool_identity) is None
            ):
                raise ValueError("invalid required change fields")
            locator = _locator(contract.path, record)
            identity = [
                contract.id,
                check_id,
                {
                    "path": locator.path,
                    "operation": locator.operation,
                    "json_pointer": locator.json_pointer,
                },
                tool_identity,
            ]
            canonical = json.dumps(
                identity, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            findings.append(
                Finding(
                    source="openapi",
                    check_id=check_id,
                    severity=_LEVELS[level],
                    message=message,
                    fingerprint=f"openapi/v1:{hashlib.sha256(canonical).hexdigest()}",
                    locator=locator,
                    provenance=provenance,
                )
            )
    except (KeyError, ValueError, TypeError):
        return NormalizationResult(
            (),
            (
                Diagnostic(
                    "openapi",
                    "openapi-tool-failed",
                    "error",
                    f"{contract.path}: oasdiff returned an unrecognized change record",
                ),
            ),
        )
    return NormalizationResult(
        tuple(
            sorted(
                findings,
                key=lambda f: (f.locator.operation or "", f.check_id, f.fingerprint),
            )
        ),
        (),
    )


def _locator(contract_path: str, record: Mapping[str, object]) -> Locator:
    operation = record.get("operation")
    path = record.get("path")
    if operation is not None and not isinstance(operation, str):
        raise ValueError("invalid operation")
    if path is not None and not isinstance(path, str):
        raise ValueError("invalid path")
    if operation:
        parts = operation.strip().split(maxsplit=1)
        if len(parts) == 2:
            method, api_path = parts
        elif len(parts) == 1 and path:
            method, api_path = parts[0], path
        else:
            raise ValueError("invalid operation")
        method = method.upper()
        if (
            method not in _METHODS
            or not api_path.startswith("/")
            or any(c.isspace() for c in api_path)
        ):
            raise ValueError("invalid operation")
        normalized = f"{method} {api_path}"
        pointer = f"/paths/{_escape(api_path)}/{method.lower()}"
        return Locator(contract_path, operation=normalized, json_pointer=pointer)
    if path and path.startswith("/"):
        pointer = f"/paths/{_escape(path)}"
        return Locator(contract_path, operation="document", json_pointer=pointer)
    return Locator(contract_path, operation="document")


def _escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")
