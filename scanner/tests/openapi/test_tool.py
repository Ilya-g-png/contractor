import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from dogwatch.openapi import tool


def _cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: bytes) -> Path:
    archive_name = "oasdiff_1.39.0_linux_amd64.tar.gz"
    archive = tmp_path / archive_name
    with tarfile.open(archive, "w:gz") as output:
        info = tarfile.TarInfo("oasdiff")
        info.size = len(body)
        info.mode = 0o755
        output.addfile(info, io.BytesIO(body))
    executable = tmp_path / "oasdiff"
    executable.write_bytes(body)
    executable.chmod(0o700)
    monkeypatch.setitem(
        tool.ARCHIVES,
        ("Linux", "x86_64"),
        (archive_name, hashlib.sha256(archive.read_bytes()).hexdigest()),
    )
    return archive


def _resolve(tmp_path: Path) -> tool.ToolResult:
    return tool.resolve_verified_oasdiff(tmp_path, system="Linux", machine="x86_64")


def test_manifest_contains_only_pinned_archives() -> None:
    assert set(tool.ARCHIVES.values()) == {
        (
            "oasdiff_1.39.0_darwin_all.tar.gz",
            "fe88d9950324d3b0ebeaf8e0d3a210b64cb099a0f55fce5ee5a22b276df0eac4",
        ),
        (
            "oasdiff_1.39.0_linux_amd64.tar.gz",
            "71a85930728f367a2086077b7ae1411319421549d18473a3e8258b6451520433",
        ),
        (
            "oasdiff_1.39.0_linux_arm64.tar.gz",
            "481db7d891d916f13df277b2ef8bbb95477702827710e49fe22cef69c359c780",
        ),
    }


def test_provider_accepts_matching_archive_binary_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cache(tmp_path, monkeypatch, b"#!/bin/sh\necho 'oasdiff version 1.39.0'\n")
    result = _resolve(tmp_path)
    assert result.executable == (tmp_path / "oasdiff").resolve()
    assert result.diagnostics == ()


def test_provider_rejects_unsupported_and_missing(tmp_path: Path) -> None:
    for result in (
        tool.resolve_verified_oasdiff(tmp_path, system="Windows", machine="AMD64"),
        _resolve(tmp_path),
    ):
        assert result.executable is None
        assert result.diagnostics[0].id == "openapi-tool-unavailable"


@pytest.mark.parametrize("condition", ["checksum", "binary", "version", "unsafe"])
def test_provider_rejects_invalid_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, condition: str
) -> None:
    archive = _cache(
        tmp_path,
        monkeypatch,
        b"#!/bin/sh\necho 'oasdiff version 1.38.0'\n"
        if condition == "version"
        else b"#!/bin/sh\necho 'oasdiff version 1.39.0'\n",
    )
    if condition == "checksum":
        archive.write_bytes(b"bad archive")
    elif condition == "binary":
        (tmp_path / "oasdiff").write_bytes(b"bad binary")
    elif condition == "unsafe":
        with tarfile.open(archive, "w:gz") as output:
            info = tarfile.TarInfo("../oasdiff")
            info.size = 1
            output.addfile(info, io.BytesIO(b"x"))
        monkeypatch.setitem(
            tool.ARCHIVES,
            ("Linux", "x86_64"),
            (archive.name, hashlib.sha256(archive.read_bytes()).hexdigest()),
        )
    result = _resolve(tmp_path)
    assert result.executable is None
    assert result.diagnostics[0].id == "openapi-tool-unavailable"
