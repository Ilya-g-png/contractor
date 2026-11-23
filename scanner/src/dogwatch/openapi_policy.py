import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import cast

from dogwatch._validate import (
    config_invalid,
    key_path,
    optional_str,
    require_str,
    table_array,
)
from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Severity

_SEVERITIES = "openapi.severity"
_WAIVERS = "openapi.waivers"
_FINGERPRINT = re.compile(r"openapi/v1:[0-9a-f]{64}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION = re.compile(
    r"(?:document|(?:DELETE|GET|HEAD|OPTIONS|PATCH|POST|PUT|TRACE) /[^\s]+)\Z"
)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


@dataclass(frozen=True)
class OpenApiSeverityDecl:
    check_id: str
    severity: Severity
    reason: str


@dataclass(frozen=True)
class OpenApiWaiverDecl:
    contract_id: str
    check_id: str
    operation: str
    fingerprint: str
    baseline_sha256: str
    reason: str
    expires: str | None


def parse_openapi_policy(
    severity_value: object,
    waiver_value: object,
    contracts: Sequence[OpenApiContractDecl],
) -> tuple[tuple[OpenApiSeverityDecl, ...], tuple[OpenApiWaiverDecl, ...]]:
    severities = _parse_severities(severity_value)
    waivers = _parse_waivers(waiver_value, contracts)
    return severities, waivers


def _parse_severities(value: object) -> tuple[OpenApiSeverityDecl, ...]:
    if value is None:
        return ()
    declarations: list[OpenApiSeverityDecl] = []
    for index, entry in enumerate(table_array(value, _SEVERITIES)):
        path = key_path(_SEVERITIES, index)
        check_id = _require_target(entry, path, "check_id")
        if any(other.check_id == check_id for other in declarations):
            earlier = next(
                position
                for position, other in enumerate(declarations)
                if other.check_id == check_id
            )
            raise config_invalid(
                f"{key_path(path, 'check_id')} '{check_id}' duplicates "
                f"{key_path(_SEVERITIES, earlier, 'check_id')}"
            )
        severity = require_str(entry, path, "severity")
        if severity not in {"error", "warning", "info"}:
            raise config_invalid(
                f"{key_path(path, 'severity')} '{severity}' "
                "must be error, warning or info"
            )
        declarations.append(
            OpenApiSeverityDecl(
                check_id,
                cast(Severity, severity),
                _require_target(entry, path, "reason"),
            )
        )
    return tuple(declarations)


def _parse_waivers(
    value: object, contracts: Sequence[OpenApiContractDecl]
) -> tuple[OpenApiWaiverDecl, ...]:
    if value is None:
        return ()
    contract_ids = {contract.id for contract in contracts}
    declarations: list[OpenApiWaiverDecl] = []
    for index, entry in enumerate(table_array(value, _WAIVERS)):
        path = key_path(_WAIVERS, index)
        contract_id = _require_target(entry, path, "contract_id")
        if contract_id not in contract_ids:
            raise config_invalid(
                f"{key_path(path, 'contract_id')} '{contract_id}' does not name "
                "a configured OpenAPI contract"
            )
        operation = require_str(entry, path, "operation")
        if _OPERATION.fullmatch(operation) is None:
            raise config_invalid(
                f"{key_path(path, 'operation')} '{operation}' "
                "must be a normalized operation locator"
            )
        fingerprint = require_str(entry, path, "fingerprint")
        if _FINGERPRINT.fullmatch(fingerprint) is None:
            raise config_invalid(
                f"{key_path(path, 'fingerprint')} must be an openapi/v1 fingerprint"
            )
        baseline_sha256 = require_str(entry, path, "baseline_sha256")
        if _SHA256.fullmatch(baseline_sha256) is None:
            raise config_invalid(
                f"{key_path(path, 'baseline_sha256')} must be a lowercase SHA-256 hash"
            )
        declaration = OpenApiWaiverDecl(
            contract_id=contract_id,
            check_id=_require_target(entry, path, "check_id"),
            operation=operation,
            fingerprint=fingerprint,
            baseline_sha256=baseline_sha256,
            reason=_require_target(entry, path, "reason"),
            expires=_expires(entry, path),
        )
        duplicate = next(
            (
                position
                for position, other in enumerate(declarations)
                if _waiver_identity(other) == _waiver_identity(declaration)
            ),
            None,
        )
        if duplicate is not None:
            raise config_invalid(f"{path} duplicates {key_path(_WAIVERS, duplicate)}")
        declarations.append(declaration)
    return tuple(declarations)


def _require_target(table: Mapping[str, object], path: str, key: str) -> str:
    value = require_str(table, path, key)
    if not value.strip():
        raise config_invalid(f"{key_path(path, key)} must not be empty")
    return value


def _expires(table: Mapping[str, object], path: str) -> str | None:
    expires = optional_str(table, path, "expires")
    if expires is None:
        return None
    if _DATE.fullmatch(expires) is None:
        raise config_invalid(
            f"{key_path(path, 'expires')} must be an ISO-8601 calendar date"
        )
    try:
        date.fromisoformat(expires)
    except ValueError:
        raise config_invalid(
            f"{key_path(path, 'expires')} must be an ISO-8601 calendar date"
        ) from None
    return expires


def _waiver_identity(declaration: OpenApiWaiverDecl) -> tuple[str, str, str, str, str]:
    return (
        declaration.contract_id,
        declaration.check_id,
        declaration.operation,
        declaration.fingerprint,
        declaration.baseline_sha256,
    )
