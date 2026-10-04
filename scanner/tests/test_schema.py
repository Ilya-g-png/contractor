import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dogwatch.config import PackageDecl, PolicyConfig
from dogwatch.report import build_report

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "report-0.1.schema.json"
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


def _schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_bytes())
    return schema


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def _report() -> dict[str, Any]:
    cfg = PolicyConfig(
        path_arg="fixtures/minimal/dogwatch.toml",
        raw=b'[[python.packages]]\nname = "acme"\nroot = "src"\n',
        packages=(PackageDecl("acme", "src"),),
    )
    return build_report(cfg, "0.1.0")


def test_schema_is_valid_draft_2020_12() -> None:
    schema = _schema()

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "urn:dogwatch:schema:report:0.1"


def test_build_report_output_validates() -> None:
    assert list(_validator().iter_errors(_report())) == []


@pytest.mark.parametrize("field", FORBIDDEN_FIELDS)
def test_forbidden_provenance_field_is_rejected(field: str) -> None:
    report = _report()
    report[field] = "x"

    assert not _validator().is_valid(report)


def test_non_empty_findings_is_rejected() -> None:
    report = _report()
    report["findings"] = [{}]

    assert not _validator().is_valid(report)


@pytest.mark.parametrize("level", [(), ("scanner",), ("policy",), ("policy", "digest")])
def test_extra_key_is_rejected_at_every_object_level(level: tuple[str, ...]) -> None:
    report = _report()
    target = report
    for key in level:
        target = target[key]
    target["extra"] = "x"

    assert not _validator().is_valid(report)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "0.2"),
        (("scanner", "name"), "other"),
        (("scanner", "version"), "v0.1.0"),
        (("policy", "path"), ""),
        (("policy", "path"), "dir/dogwatch.toml"),
        (("policy", "path"), "dir\\dogwatch.toml"),
        (("policy", "path"), "dog\nwatch.toml"),
        (("policy", "digest", "sha256"), "A" * 64),
        (("policy", "digest", "sha256"), "a" * 63),
    ],
)
def test_invalid_field_value_is_rejected(path: tuple[str, ...], value: str) -> None:
    report = _report()
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    assert not _validator().is_valid(report)


@pytest.mark.parametrize("field", ["schema_version", "scanner", "policy", "findings"])
def test_missing_required_field_is_rejected(field: str) -> None:
    report = _report()
    del report[field]

    assert not _validator().is_valid(report)
