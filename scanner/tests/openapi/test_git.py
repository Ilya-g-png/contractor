import subprocess
from pathlib import Path

import pytest

from dogwatch.contracts import OpenApiContractDecl
from dogwatch.openapi.git import read_baseline, resolve_baseline_ref
from dogwatch.openapi.model import BaselineReference
from dogwatch.openapi.preflight import MAX_RAW_BYTES

DECLARATION = OpenApiContractDecl("public-api", "api/openapi.yaml")
VALID = b'{"openapi":"3.0.3","info":{"title":"Example","version":"1"},"paths":{}}'


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "dogwatch@example.test")
    _git(repo, "config", "user.name", "Dogwatch")
    path = repo / DECLARATION.path
    path.parent.mkdir()
    path.write_bytes(VALID)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_reads_exact_path_from_immutable_resolved_baseline(tmp_path: Path) -> None:
    repo, commit = _repository(tmp_path)
    resolved = resolve_baseline_ref(repo, "HEAD")

    assert resolved.reference is not None
    assert resolved.reference.resolved_commit == commit
    read = read_baseline(repo, resolved.reference, DECLARATION)

    assert read.input is not None
    assert read.input.path == DECLARATION.path
    assert read.input.raw_bytes == VALID
    assert read.diagnostics == ()

    (repo / DECLARATION.path).write_bytes(b"changed")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "candidate")
    reread = read_baseline(repo, resolved.reference, DECLARATION)
    assert reread.input is not None
    assert reread.input.raw_bytes == VALID


def test_reports_unavailable_refs_and_invalid_baseline_entries(tmp_path: Path) -> None:
    repo, _ = _repository(tmp_path)
    unavailable = resolve_baseline_ref(repo, "not-a-ref")
    assert unavailable.reference is None
    assert unavailable.diagnostics[0].id == "openapi-baseline-ref-unavailable"

    resolved = resolve_baseline_ref(repo, "HEAD")
    assert resolved.reference is not None
    missing = read_baseline(
        repo, resolved.reference, OpenApiContractDecl("missing", "api/missing.yaml")
    )
    assert missing.input is None
    assert missing.diagnostics[0].id == "openapi-baseline-invalid"


def test_rejects_symlink_baseline_entry_without_checkout(tmp_path: Path) -> None:
    repo, _ = _repository(tmp_path)
    path = repo / DECLARATION.path
    path.unlink()
    path.symlink_to("other.yaml")
    _git(repo, "add", "api/openapi.yaml")
    _git(repo, "commit", "-m", "symlink")
    resolved = resolve_baseline_ref(repo, "HEAD")
    assert resolved.reference is not None

    read = read_baseline(repo, resolved.reference, DECLARATION)

    assert read.input is None
    assert read.diagnostics[0].id == "openapi-baseline-invalid"


def test_reports_repository_and_object_faults(tmp_path: Path) -> None:
    absent = resolve_baseline_ref(tmp_path, "HEAD")
    assert absent.reference is None
    assert absent.diagnostics[0].id == "openapi-git-failed"

    second = tmp_path / "second"
    second.mkdir()
    repo, _ = _repository(second)
    invalid = read_baseline(repo, BaselineReference("HEAD", "0" * 40), DECLARATION)
    assert invalid.input is None
    assert invalid.diagnostics[0].id == "openapi-git-failed"


def test_reads_literal_path_with_git_pathspec_characters(tmp_path: Path) -> None:
    repo, _ = _repository(tmp_path)
    declaration = OpenApiContractDecl("literal", "api/openapi*.yaml")
    (repo / declaration.path).write_bytes(VALID)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "literal path")
    resolved = resolve_baseline_ref(repo, "HEAD")
    assert resolved.reference is not None

    read = read_baseline(repo, resolved.reference, declaration)

    assert read.input is not None
    assert read.input.raw_bytes == VALID


def test_baseline_enforces_its_own_raw_size_limit(tmp_path: Path) -> None:
    repo, _ = _repository(tmp_path)
    (repo / DECLARATION.path).write_bytes(b" " * (MAX_RAW_BYTES + 1))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "oversized contract")
    resolved = resolve_baseline_ref(repo, "HEAD")
    assert resolved.reference is not None

    read = read_baseline(repo, resolved.reference, DECLARATION)

    assert read.input is None
    assert read.diagnostics[0].id == "openapi-input-invalid"


def test_baseline_ignores_inherited_git_repository_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, commit = _repository(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing-repository"))

    resolved = resolve_baseline_ref(repo, "HEAD")

    assert resolved.reference is not None
    assert resolved.reference.resolved_commit == commit
