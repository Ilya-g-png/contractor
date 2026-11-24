import hashlib
from pathlib import Path

import pytest

from dogwatch.contracts import OpenApiContractDecl
from dogwatch.openapi.preflight import (
    MAX_RAW_BYTES,
    preflight_bytes,
    preflight_candidate,
    preflight_pair,
)

DECLARATION = OpenApiContractDecl("public-api", "api/openapi.yaml")
VALID = b"openapi: 3.1.0\ninfo: {title: Example, version: 1}\npaths: {}\n"


def _candidate(tmp_path: Path, content: bytes = VALID) -> Path:
    path = tmp_path / DECLARATION.path
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    return path


def test_preflight_canonicalizes_valid_yaml_and_retains_raw_hash(
    tmp_path: Path,
) -> None:
    _candidate(tmp_path)

    result = preflight_candidate(tmp_path, DECLARATION)

    assert result.input is not None
    assert result.diagnostics == ()
    assert result.input.raw_sha256 == hashlib.sha256(VALID).hexdigest()
    assert result.input.canonical_json == (
        b'{"info":{"title":"Example","version":1},"openapi":"3.1.0","paths":{}}'
    )


@pytest.mark.parametrize(
    "content",
    [
        b"openapi: 3.1.0\npaths: {}\npaths: {}\n",
        b"openapi: 3.1.0\npaths: &paths {}\ncopy: *paths\n",
        b"openapi: 3.1.0\nitem: !!python/object/apply:os.system ['false']\n",
        b"openapi: 3.1.0\npaths:\n  $ref: https://example.test/openapi.yaml\n",
        b"openapi: 3.1.0\npaths:\n  $ref: '#/components/missing'\n",
        b"openapi: 2.0\npaths: {}\n",
    ],
)
def test_preflight_rejects_unsafe_or_invalid_documents(
    tmp_path: Path, content: bytes
) -> None:
    _candidate(tmp_path, content)

    result = preflight_candidate(tmp_path, DECLARATION)

    assert result.input is None
    assert result.diagnostics[0].source == "openapi"
    assert result.diagnostics[0].id == "openapi-input-invalid"
    assert result.diagnostics[0].severity == "error"


def test_unsafe_yaml_constructor_is_never_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def record_system(command: str) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr("os.system", record_system)
    _candidate(
        tmp_path,
        b"openapi: 3.1.0\nitem: !!python/object/apply:os.system ['echo unsafe']\n",
    )

    result = preflight_candidate(tmp_path, DECLARATION)

    assert result.input is None
    assert calls == []


@pytest.mark.parametrize(
    "path", ["api/contract.txt", "../api/openapi.yaml", "/api/openapi.yaml"]
)
def test_preflight_rejects_invalid_declaration_paths(path: str) -> None:
    result = preflight_bytes(
        "candidate", OpenApiContractDecl("public-api", path), VALID
    )

    assert result.input is None
    assert result.diagnostics[0].id == "openapi-input-invalid"


@pytest.mark.parametrize("version", ["3.0.4", "3.1.1", "3.2.0"])
def test_preflight_accepts_supported_numeric_patch_versions(version: str) -> None:
    content = f'{{"openapi":"{version}","paths":{{}}}}'.encode()

    result = preflight_bytes(
        "candidate", OpenApiContractDecl("public-api", "api/openapi.json"), content
    )

    assert result.input is not None
    assert result.input.openapi_version == version


def test_preflight_rejects_malformed_patch_version() -> None:
    result = preflight_bytes(
        "candidate", DECLARATION, b"openapi: 3.1.invalid\npaths: {}\n"
    )

    assert result.input is None


def test_preflight_resolves_percent_encoded_internal_pointer() -> None:
    content = (
        b"openapi: 3.1.0\ncomponents:\n  schemas:\n    a/b: {}\n"
        b"paths:\n  /x:\n    $ref: '#/components/schemas/a%7E1b'\n"
    )

    result = preflight_bytes("candidate", DECLARATION, content)

    assert result.input is not None


def test_preflight_rejects_excessive_yaml_nesting() -> None:
    content = b"openapi: 3.1.0\nvalue: " + b"[" * 101 + b"0" + b"]" * 101

    result = preflight_bytes("candidate", DECLARATION, content)

    assert result.input is None
    assert result.diagnostics[0].id == "openapi-input-invalid"


def test_preflight_rejects_missing_non_regular_and_oversized_inputs(
    tmp_path: Path,
) -> None:
    missing = preflight_candidate(tmp_path, DECLARATION)
    assert missing.input is None

    path = _candidate(tmp_path)
    path.unlink()
    path.mkdir()
    non_regular = preflight_candidate(tmp_path, DECLARATION)
    assert non_regular.input is None

    path.rmdir()
    path.write_bytes(b" " * (MAX_RAW_BYTES + 1))
    oversized = preflight_candidate(tmp_path, DECLARATION)
    assert oversized.input is None
    assert all(
        result.diagnostics[0].id == "openapi-input-invalid"
        for result in (missing, non_regular, oversized)
    )


def test_preflight_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "openapi.yaml").write_bytes(VALID)
    (tmp_path / "api").symlink_to(outside, target_is_directory=True)

    result = preflight_candidate(tmp_path, DECLARATION)

    assert result.input is None
    assert result.diagnostics[0].id == "openapi-input-invalid"


def test_pair_is_ready_only_after_both_inputs_validate(tmp_path: Path) -> None:
    _candidate(tmp_path)
    candidate = preflight_candidate(tmp_path, DECLARATION)

    missing_baseline = preflight_candidate(tmp_path / "base", DECLARATION, side="base")
    failed_pair = preflight_pair(candidate, missing_baseline)
    assert failed_pair.inputs is None

    baseline_root = tmp_path / "base"
    _candidate(baseline_root)
    baseline = preflight_candidate(baseline_root, DECLARATION, side="base")
    valid_pair = preflight_pair(candidate, baseline)
    assert valid_pair.inputs == (candidate.input, baseline.input)
