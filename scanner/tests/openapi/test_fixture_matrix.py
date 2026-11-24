import difflib
import hashlib
import json
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dogwatch.openapi import runner
from dogwatch.report import exit_code_for_status
from tests.openapi.matrix_harness import (
    FIXTURES,
    POLICY_NAME,
    REPORT_NAME,
    FixtureCase,
    discover_cases,
    materialize,
    run_case,
)

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "report-0.3.schema.json"
CASES = discover_cases()
REQUIRED_CATEGORIES = {
    "no-change",
    "removed-operation",
    "optional-to-required-field",
    "enum-or-constraint-break",
    "invalid-specification",
    "missing-baseline",
    "timeout-or-tool-failure",
    "ignored-or-reclassified",
}
PINNED_CASES = {
    "baseline-ref-unavailable": "missing-baseline",
    "enum-constraint-break": "enum-or-constraint-break",
    "invalid-specification": "invalid-specification",
    "missing-baseline": "missing-baseline",
    "no-change": "no-change",
    "optional-to-required": "optional-to-required-field",
    "reclassified-finding": "ignored-or-reclassified",
    "removed-operation": "removed-operation",
    "tool-malformed-output": "timeout-or-tool-failure",
    "tool-nonzero-exit": "timeout-or-tool-failure",
    "tool-stderr-limit": "timeout-or-tool-failure",
    "tool-stdout-limit": "timeout-or-tool-failure",
    "tool-timeout": "timeout-or-tool-failure",
    "waived-finding": "ignored-or-reclassified",
}
ARGV_PROFILE = [
    "{substitute}",
    "changelog",
    "--format=json",
    "--level=INFO",
    "--allow-external-refs=false",
    "--",
    "{private}/base.json",
    "{private}/candidate.json",
]
EXECUTION_CASES = [case for case in CASES if case.tool is not None]


def _case_id(case: FixtureCase) -> str:
    return case.name


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(directory).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _diff(name: str, expected: bytes, actual: bytes) -> str:
    return "".join(
        difflib.unified_diff(
            expected.decode("utf-8", "replace").splitlines(keepends=True),
            actual.decode("utf-8", "replace").splitlines(keepends=True),
            name,
            "actual",
        )
    )


def _contract_path(case: FixtureCase) -> str:
    policy = tomllib.loads((case.directory / POLICY_NAME).read_text("utf-8"))
    contracts: list[dict[str, str]] = policy["openapi"]["contracts"]
    assert len(contracts) == 1
    return contracts[0]["path"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.golden
def test_matrix_covers_every_required_category() -> None:
    assert {case.name: case.category for case in CASES} == PINNED_CASES
    assert sorted(path.name for path in FIXTURES.iterdir() if path.is_dir()) == [
        case.name for case in CASES
    ]
    assert set(PINNED_CASES.values()) == REQUIRED_CATEGORIES


@pytest.mark.golden
@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_fixture_runs_twice_with_pinned_outputs(case: FixtureCase) -> None:
    before = _snapshot(case.directory)
    expected_report = case.report_path.read_bytes()
    expected_invocations = (
        (case.invocation_path.read_bytes(),) if case.invocation_path.exists() else ()
    )

    runs = [run_case(case), run_case(case)]

    for result in runs:
        assert result.exit_code == case.exit_code, result.stderr
        if result.report != expected_report:
            pytest.fail(_diff(REPORT_NAME, expected_report, result.report))
        assert result.invocations == expected_invocations
    assert runs[0].report == runs[1].report
    assert runs[0].baseline_commit == runs[1].baseline_commit
    assert _snapshot(case.directory) == before
    if case.tool is None:
        assert runs[0].tool_inputs is None
        return
    contract = _contract_path(case)
    for result in runs:
        assert result.tool_inputs is not None
        for side in ("base", "candidate"):
            source = yaml.safe_load((case.directory / side / contract).read_bytes())
            assert json.loads(result.tool_inputs[side]) == source


@pytest.mark.golden
@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_expected_report_satisfies_contract(case: FixtureCase) -> None:
    report: dict[str, Any] = json.loads(case.report_path.read_bytes())
    Draft202012Validator(json.loads(SCHEMA_PATH.read_bytes())).validate(report)
    assert exit_code_for_status(report["status"]) == case.exit_code
    assert report["policy"]["digest"]["sha256"] == _sha256(case.directory / POLICY_NAME)
    assert [item["check_id"] for item in report["findings"]] == list(case.check_ids)

    if case.diagnostic_ids:
        assert report["status"] == "inconclusive"
        assert case.exit_code == 2
        assert report["findings"] == []
        assert [item["id"] for item in report["diagnostics"]] == list(
            case.diagnostic_ids
        )
        assert all(
            item["source"] == "openapi" and item["severity"] == "error"
            for item in report["diagnostics"]
        )
        return

    assert report["diagnostics"] == []
    contract = _contract_path(case)
    with tempfile.TemporaryDirectory(prefix="dogwatch-openapi-matrix-") as tmp:
        commit = materialize(case, Path(tmp) / "repo")
    for finding in report["findings"]:
        assert finding["source"] == "openapi"
        assert finding["severity"] in {"error", "warning", "info"}
        assert finding["check_id"]
        assert finding["message"]
        assert finding["fingerprint"].startswith("openapi/v1:")
        assert finding["locator"]["path"] == contract
        assert finding["locator"]["operation"]
        assert finding["provenance"] == {
            "base": {
                "ref": case.baseline_ref,
                "commit": commit,
                "path": contract,
                "sha256": _sha256(case.directory / "base" / contract),
            },
            "candidate": {
                "path": contract,
                "sha256": _sha256(case.directory / "candidate" / contract),
            },
        }
    fingerprints = [finding["fingerprint"] for finding in report["findings"]]
    assert len(set(fingerprints)) == len(fingerprints)


@pytest.mark.golden
@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_execution_path_is_pinned_only_when_oasdiff_runs(case: FixtureCase) -> None:
    assert case.invocation_path.exists() == (case.tool is not None)


@pytest.mark.golden
@pytest.mark.parametrize("case", EXECUTION_CASES, ids=_case_id)
def test_expected_invocation_proves_safe_execution(case: FixtureCase) -> None:
    record: dict[str, Any] = json.loads(case.invocation_path.read_bytes())

    assert record["argv"] == ARGV_PROFILE
    assert record["argv"].count("--allow-external-refs=false") == 1
    assert record["cwd"] == "{private}"
    assert record["observed"]["cwd"] == "{private}"
    assert record["observed"]["private_directory_mode"] == "0700"
    assert record["observed"]["stdin_bytes"] == 0
    for side in ("base", "candidate"):
        assert record["observed"]["inputs"][side]["mode"] == "0400"
    assert record["environment"]["HOME"] == record["environment"]["TMPDIR"]
    assert record["environment"]["HOME"] == "{private}"
    assert record["limits"] == {
        "timeout_seconds": 60,
        "stdout_bytes": 16 * 1024 * 1024,
        "stderr_bytes": 1024 * 1024,
    }
    assert record["limits"] == {
        "timeout_seconds": runner.TIMEOUT_SECONDS,
        "stdout_bytes": runner.STDOUT_LIMIT,
        "stderr_bytes": runner.STDERR_LIMIT,
    }
