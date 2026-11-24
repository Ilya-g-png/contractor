import hashlib
import io
import os
import platform
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dogwatch.diagnostics import Diagnostic
from dogwatch.openapi.runner import collect_process

OASDIFF_VERSION = "1.39.0"
ARCHIVES = {
    ("Darwin", "arm64"): (
        "oasdiff_1.39.0_darwin_all.tar.gz",
        "fe88d9950324d3b0ebeaf8e0d3a210b64cb099a0f55fce5ee5a22b276df0eac4",
    ),
    ("Darwin", "x86_64"): (
        "oasdiff_1.39.0_darwin_all.tar.gz",
        "fe88d9950324d3b0ebeaf8e0d3a210b64cb099a0f55fce5ee5a22b276df0eac4",
    ),
    ("Linux", "x86_64"): (
        "oasdiff_1.39.0_linux_amd64.tar.gz",
        "71a85930728f367a2086077b7ae1411319421549d18473a3e8258b6451520433",
    ),
    ("Linux", "aarch64"): (
        "oasdiff_1.39.0_linux_arm64.tar.gz",
        "481db7d891d916f13df277b2ef8bbb95477702827710e49fe22cef69c359c780",
    ),
}
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ToolResult:
    executable: Path | None
    diagnostics: tuple[Diagnostic, ...]


def resolve_verified_oasdiff(
    cache_dir: Path, *, system: str | None = None, machine: str | None = None
) -> ToolResult:
    selected = ARCHIVES.get(
        (system or platform.system(), machine or platform.machine())
    )
    if selected is None:
        return _unavailable("oasdiff v1.39.0 is unavailable on this platform")
    archive_name, checksum = selected
    archive_path = cache_dir / archive_name
    executable = cache_dir / "oasdiff"
    try:
        archive_bytes = _read_regular(archive_path, MAX_ARCHIVE_BYTES)
        if hashlib.sha256(archive_bytes).hexdigest() != checksum:
            return _unavailable("oasdiff archive checksum is invalid")
        expected_executable = _archive_executable(archive_bytes)
        installed_executable = _read_regular(executable, MAX_EXECUTABLE_BYTES)
        if installed_executable != expected_executable:
            return _unavailable(
                "oasdiff executable does not match the verified archive"
            )
        if not os.access(executable, os.X_OK):
            return _unavailable("oasdiff executable is not executable")
        stdout, _, status, failure = collect_process(
            [str(executable.resolve()), "--version"],
            cache_dir,
            {"HOME": str(cache_dir), "PATH": os.defpath},
            5,
            4096,
            4096,
        )
    except (OSError, ValueError, tarfile.TarError):
        return _unavailable("verified oasdiff v1.39.0 is unavailable")
    if (
        failure is not None
        or status != 0
        or stdout.strip() != b"oasdiff version 1.39.0"
    ):
        return _unavailable("oasdiff executable has the wrong version")
    return ToolResult(executable.resolve(), ())


def _read_regular(path: Path, limit: int) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("not a regular file")
    with path.open("rb") as file:
        content = file.read(limit + 1)
    if len(content) > limit:
        raise ValueError("file exceeds limit")
    return content


def _archive_executable(content: bytes) -> bytes:
    executable: bytes | None = None
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe archive entry")
            if member.isdir():
                continue
            if not member.isfile() or member.size > MAX_EXECUTABLE_BYTES:
                raise ValueError("unsafe archive entry")
            if path.name == "oasdiff":
                if executable is not None:
                    raise ValueError("duplicate executable")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("missing executable data")
                executable = stream.read(MAX_EXECUTABLE_BYTES + 1)
                if len(executable) != member.size:
                    raise ValueError("invalid executable size")
    if executable is None:
        raise ValueError("archive lacks executable")
    return executable


def _unavailable(message: str) -> ToolResult:
    return ToolResult(
        None,
        (Diagnostic("openapi", "openapi-tool-unavailable", "error", message),),
    )
