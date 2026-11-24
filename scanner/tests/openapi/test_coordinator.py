import subprocess
from datetime import date
from pathlib import Path

import pytest

from dogwatch.config import DogwatchConfig
from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Diagnostic
from dogwatch.openapi import coordinator
from dogwatch.openapi.git import resolve_baseline_ref as real_resolve
from dogwatch.openapi.runner import RunnerResult
from dogwatch.openapi.tool import ToolResult
from dogwatch.openapi_policy import OpenApiSeverityDecl
from dogwatch.report import derive_status

VALID = b'{"openapi":"3.0.3","info":{"title":"Example","version":"1"},"paths":{}}'
DECLS = (
    OpenApiContractDecl("one", "api/one.json"),
    OpenApiContractDecl("two", "api/two.json"),
)
RECORD = {
    "id": "api-path-removed",
    "text": "removed operation",
    "level": 3,
    "fingerprint": "abcdef123456",
    "operation": "GET /pets",
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=True, text=True
    ).stdout.strip()


def _repository(root: Path) -> tuple[Path, str]:
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.test")
    _git(root, "config", "user.name", "Test")
    for decl in DECLS:
        path = root / decl.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(VALID)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")
    return root, _git(root, "rev-parse", "HEAD")


def _config(
    contracts: tuple[OpenApiContractDecl, ...] = DECLS,
    severities: tuple[OpenApiSeverityDecl, ...] = (),
) -> DogwatchConfig:
    return DogwatchConfig("dogwatch.toml", b"", (), (), (), contracts, severities)


def _tool(
    monkeypatch: pytest.MonkeyPatch, records: tuple[dict[str, object], ...]
) -> list[tuple[bytes, bytes]]:
    calls: list[tuple[bytes, bytes]] = []
    monkeypatch.setattr(
        coordinator,
        "resolve_verified_oasdiff",
        lambda cache: ToolResult(Path("/verified/oasdiff"), ()),
    )

    def run(executable: Path, base: bytes, candidate: bytes) -> RunnerResult:
        assert executable == Path("/verified/oasdiff")
        calls.append((base, candidate))
        return RunnerResult(records, ())

    monkeypatch.setattr(coordinator, "run_oasdiff", run)
    return calls


def test_no_declarations_preserve_empty_scan(tmp_path: Path) -> None:
    result = coordinator.compare_openapi_contracts(_config(()), None, tmp_path)
    assert result.comparisons == ()
    assert result.findings == ()
    assert result.diagnostics == ()


def test_missing_ref_is_report_diagnostic_without_git_or_tool(tmp_path: Path) -> None:
    result = coordinator.compare_openapi_contracts(_config(), None, tmp_path)
    assert len(result.comparisons) == 2
    assert {item.state for item in result.comparisons} == {"inconclusive"}
    assert result.findings == ()
    assert all(
        item.id == "openapi-baseline-ref-required" for item in result.diagnostics
    )
    assert derive_status(result.findings, result.diagnostics) == "inconclusive"


def test_baseline_is_resolved_once_and_no_change_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, commit = _repository(tmp_path / "repo")
    calls = _tool(monkeypatch, ())
    refs: list[str] = []

    def resolve(path: Path, supplied_ref: str) -> object:
        refs.append(supplied_ref)
        return real_resolve(path, supplied_ref)

    monkeypatch.setattr(coordinator, "resolve_baseline_ref", resolve)
    result = coordinator.compare_openapi_contracts(_config(), "HEAD", root)
    assert refs == ["HEAD"]
    assert len(calls) == 2
    assert all(base == candidate for base, candidate in calls)
    assert {
        item.baseline.resolved_commit for item in result.comparisons if item.baseline
    } == {commit}
    assert [item.state for item in result.comparisons] == ["no-change", "no-change"]
    assert result.findings == ()
    assert result.diagnostics == ()
    assert derive_status(result.findings, result.diagnostics) == "pass"


def test_valid_change_has_provenance_and_policy_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, commit = _repository(tmp_path / "repo")
    _tool(monkeypatch, (RECORD,))
    result = coordinator.compare_openapi_contracts(_config(DECLS[:1]), "HEAD", root)
    finding = result.findings[0]
    assert result.comparisons[0].state == "policy-failed"
    assert finding.source == "openapi"
    assert finding.provenance is not None
    assert finding.provenance.base.commit == commit
    assert finding.provenance.base.ref == "HEAD"
    assert finding.provenance.base.path == DECLS[0].path
    assert finding.provenance.candidate.path == DECLS[0].path
    assert result.diagnostics == ()
    assert derive_status(result.findings, result.diagnostics) == "fail"


def test_reclassification_completes_without_gate_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _repository(tmp_path / "repo")
    _tool(monkeypatch, (RECORD,))
    config = _config(
        DECLS[:1], (OpenApiSeverityDecl("api-path-removed", "warning", "allowed"),)
    )
    result = coordinator.compare_openapi_contracts(
        config, "HEAD", root, evaluation_date=date(2026, 11, 24)
    )
    assert result.comparisons[0].state == "completed"
    assert result.findings[0].severity == "warning"
    assert derive_status(result.findings, result.diagnostics) == "pass"


def test_failed_comparison_does_not_emit_partial_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _repository(tmp_path / "repo")
    (root / DECLS[1].path).write_text("broken")
    calls = _tool(monkeypatch, (RECORD,))
    result = coordinator.compare_openapi_contracts(_config(), "HEAD", root)
    assert len(calls) == 1
    assert [item.state for item in result.comparisons] == [
        "policy-failed",
        "inconclusive",
    ]
    assert len(result.findings) == 1
    assert result.comparisons[1].findings == ()
    assert result.diagnostics[0].id == "openapi-input-invalid"
    assert derive_status(result.findings, result.diagnostics) == "inconclusive"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("missing-baseline", "openapi-baseline-invalid"),
        ("missing-tool", "openapi-tool-unavailable"),
        ("runner", "openapi-tool-timeout"),
        ("normalize", "openapi-tool-failed"),
    ],
)
def test_stage_failures_are_inconclusive_without_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected: str,
) -> None:
    root, _ = _repository(tmp_path / "repo")
    if failure == "missing-baseline":
        _git(root, "rm", DECLS[0].path)
        _git(root, "commit", "-m", "remove")
        (root / DECLS[0].path).write_bytes(VALID)
    elif failure == "missing-tool":
        monkeypatch.setattr(
            coordinator,
            "resolve_verified_oasdiff",
            lambda cache: ToolResult(
                None, (Diagnostic("openapi", expected, "error", "missing"),)
            ),
        )
    elif failure == "runner":
        _tool(monkeypatch, ())
        monkeypatch.setattr(
            coordinator,
            "run_oasdiff",
            lambda executable, base, candidate: RunnerResult(
                None, (Diagnostic("openapi", expected, "error", "timeout"),)
            ),
        )
    else:
        _tool(monkeypatch, (RECORD, {**RECORD, "operation": "bad"}))
    result = coordinator.compare_openapi_contracts(_config(DECLS[:1]), "HEAD", root)
    assert result.comparisons[0].state == "inconclusive"
    assert result.findings == ()
    assert result.diagnostics[0].id == expected
    assert derive_status(result.findings, result.diagnostics) == "inconclusive"
