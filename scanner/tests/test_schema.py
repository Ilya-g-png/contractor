import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dogwatch.config import DogwatchConfig, PackageDecl
from dogwatch.diagnostics import SOURCE_SYNTAX_INVALID, Diagnostic
from dogwatch.report import Finding, Locator, build_report

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "report-0.2.schema.json"
FORBIDDEN_FIELDS = (
    "commit_sha",
    "object_format",
    "dirty",
    "base_sha",
    "evaluation_date",
    "scan_started_at",
    "scan_finished_at",
    "report_id",
)
ERROR_FINDING = Finding(
    "python", "no-db", "error", "acme.a imports acme.db", "fp-1", Locator("src/a.py")
)
SYNTAX_DIAGNOSTIC = Diagnostic(
    "dogwatch", SOURCE_SYNTAX_INVALID, "error", "src/a.py:3: invalid syntax"
)
ADAPTER_DIAGNOSTIC = Diagnostic("openapi", "openapi-tool-failed", "error", "exit 3")


def _schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_bytes())
    return schema


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def _report(
    findings: Sequence[Finding] = (), diagnostics: Sequence[Diagnostic] = ()
) -> dict[str, Any]:
    cfg = DogwatchConfig(
        path_arg="fixtures/minimal/dogwatch.toml",
        raw=b'[[python.packages]]\nname = "acme"\nroot = "src"\n',
        packages=(PackageDecl("acme", "src"),),
        exclusions=(),
        rules=(),
        contracts=(),
    )
    return build_report(cfg, "0.1.0", findings, diagnostics)


def _reported() -> dict[str, Any]:
    return _report([ERROR_FINDING], [ADAPTER_DIAGNOSTIC])


def test_schema_is_valid_draft_2020_12() -> None:
    schema = _schema()

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "urn:dogwatch:schema:report:0.2"


CONSTRUCTED: dict[str, tuple[Sequence[Finding], Sequence[Diagnostic], str]] = {
    "pass": ((), (), "pass"),
    "fail": ((ERROR_FINDING,), (), "fail"),
    "inconclusive-source-syntax": ((), (SYNTAX_DIAGNOSTIC,), "inconclusive"),
    "inconclusive-adapter": ((ERROR_FINDING,), (ADAPTER_DIAGNOSTIC,), "inconclusive"),
    "non-ascii": (
        (
            Finding(
                "python",
                "kein-db",
                "error",
                "Überprüfung — 日本語",
                "fp-ü",
                Locator("src/ü.py", source_module="acme.ü"),
            ),
        ),
        (Diagnostic("dogwatch", SOURCE_SYNTAX_INVALID, "info", "répertoire"),),
        "fail",
    ),
    "warning-info": (
        (
            Finding("python", "no-db", "warning", "w", "fp-1", Locator("a.py")),
            Finding("python", "no-db", "info", "i", "fp-2", Locator("b.py")),
        ),
        (
            Diagnostic("openapi", "openapi-tool-timeout", "warning", "slow"),
            Diagnostic("dogwatch", SOURCE_SYNTAX_INVALID, "info", "note"),
        ),
        "pass",
    ),
    "all-optional-locator": (
        (
            Finding(
                "python",
                "no-db",
                "error",
                "m",
                "fp-1",
                Locator("src/a.py", 1, 1, "acme.a", "acme.db"),
            ),
        ),
        (),
        "fail",
    ),
}


@pytest.mark.parametrize("case", CONSTRUCTED)
def test_constructed_report_validates(case: str) -> None:
    findings, diagnostics, status = CONSTRUCTED[case]

    report = _report(findings, diagnostics)

    assert report["status"] == status
    assert list(_validator().iter_errors(report)) == []


@pytest.mark.parametrize("field", FORBIDDEN_FIELDS)
def test_forbidden_provenance_field_is_rejected(field: str) -> None:
    report = _report()
    report[field] = "x"

    assert not _validator().is_valid(report)


def test_non_null_waiver_is_rejected() -> None:
    report = _reported()
    report["findings"][0]["waiver"] = {"reason": "accepted"}

    assert not _validator().is_valid(report)


def test_finding_with_id_key_is_rejected() -> None:
    report = _reported()
    report["findings"][0]["id"] = "no-db"

    assert not _validator().is_valid(report)


def test_diagnostic_with_check_id_key_is_rejected() -> None:
    report = _reported()
    report["diagnostics"][0]["check_id"] = "no-db"

    assert not _validator().is_valid(report)


def test_null_locator_value_is_rejected() -> None:
    report = _reported()
    report["findings"][0]["locator"]["line"] = None

    assert not _validator().is_valid(report)


@pytest.mark.parametrize(
    "level",
    [
        (),
        ("scanner",),
        ("policy",),
        ("policy", "digest"),
        ("findings", 0),
        ("findings", 0, "locator"),
        ("diagnostics", 0),
    ],
)
def test_extra_key_is_rejected_at_every_object_level(
    level: tuple[str | int, ...],
) -> None:
    report = _reported()
    target: Any = report
    for key in level:
        target = target[key]
    target["extra"] = "x"

    assert not _validator().is_valid(report)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "0.1"),
        (("status",), "error"),
        (("scanner", "name"), "other"),
        (("scanner", "version"), "v0.1.0"),
        (("policy", "path"), ""),
        (("policy", "path"), "dir/dogwatch.toml"),
        (("policy", "path"), "dir\\dogwatch.toml"),
        (("policy", "path"), "dog\nwatch.toml"),
        (("policy", "digest", "sha256"), "A" * 64),
        (("policy", "digest", "sha256"), "a" * 63),
        (("findings", 0, "source"), ""),
        (("findings", 0, "check_id"), ""),
        (("findings", 0, "fingerprint"), ""),
        (("findings", 0, "severity"), "fatal"),
        (("findings", 0, "locator", "path"), ""),
        (("findings", 0, "locator", "line"), 0),
        (("findings", 0, "locator", "column"), 0),
        (("findings", 0, "locator", "source_module"), ""),
        (("diagnostics", 0, "source"), ""),
        (("diagnostics", 0, "id"), "Not-Kebab"),
        (("diagnostics", 0, "id"), "dogwatch:config-invalid"),
        (("diagnostics", 0, "severity"), "fatal"),
    ],
)
def test_invalid_field_value_is_rejected(
    path: tuple[str | int, ...], value: str | int
) -> None:
    report = _reported()
    target: Any = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    assert not _validator().is_valid(report)


@pytest.mark.parametrize(
    "field",
    ["schema_version", "status", "scanner", "policy", "findings", "diagnostics"],
)
def test_missing_required_field_is_rejected(field: str) -> None:
    report = _report()
    del report[field]

    assert not _validator().is_valid(report)


@pytest.mark.parametrize(
    "field",
    ["source", "check_id", "severity", "message", "fingerprint", "waiver", "locator"],
)
def test_missing_finding_field_is_rejected(field: str) -> None:
    report = _reported()
    del report["findings"][0][field]

    assert not _validator().is_valid(report)


@pytest.mark.parametrize("field", ["source", "id", "severity", "message"])
def test_missing_diagnostic_field_is_rejected(field: str) -> None:
    report = _reported()
    del report["diagnostics"][0][field]

    assert not _validator().is_valid(report)
