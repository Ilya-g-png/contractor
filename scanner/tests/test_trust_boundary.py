import builtins
import io
import os
import shutil
import socket
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dogwatch.cli import main
from tests.golden.harness import discover_configs, golden_path

CONFIGS = {config.parent.name: config for config in discover_configs()}
FIXTURES = ["minimal", "full-surface"]
OPENERS = [(builtins, "open"), (io, "open"), (io, "open_code"), (os, "open")]
LISTERS = [(os, "scandir"), (os, "listdir")]


def _packages(config: Path) -> dict[str, str]:
    document = tomllib.loads(config.read_text("utf-8"))
    return {
        entry["name"]: os.path.realpath(config.parent / entry["root"] / entry["name"])
        for entry in document["python"]["packages"]
    }


def _under(path: str, directory: str) -> bool:
    return path == directory or path.startswith(directory + os.sep)


def _under_any(path: str, directories: dict[str, str]) -> bool:
    return any(_under(path, directory) for directory in directories.values())


def _imported_package_modules(packages: dict[str, str]) -> list[str]:
    return sorted(
        name
        for name, module in list(sys.modules.items())
        if name.partition(".")[0] in packages
        or (
            isinstance(getattr(module, "__file__", None), str)
            and _under_any(os.path.realpath(module.__file__ or ""), packages)
        )
    )


def _record(
    monkeypatch: pytest.MonkeyPatch, targets: list[tuple[Any, str]]
) -> list[str]:
    calls: list[str] = []

    def recording(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            target = args[0] if args else kwargs.get("path", kwargs.get("file", "."))
            if isinstance(target, (str, bytes, os.PathLike)):
                calls.append(os.path.realpath(os.fsdecode(target)))
            return fn(*args, **kwargs)

        return wrapper

    for module, attr in targets:
        monkeypatch.setattr(module, attr, recording(getattr(module, attr)))
    return calls


def _check(config: Path, output: str) -> int:
    return main(["check", "--config", str(config), "--output", output])


def _report(output: str, stdout: bytes) -> bytes:
    return stdout if output == "-" else Path(output).read_bytes()


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("output", ["-", "report.json"])
def test_minimal_never_opens_lists_or_imports_package_directory(
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
    output: str,
) -> None:
    config = CONFIGS["minimal"]
    packages = _packages(config)
    calls = _record(monkeypatch, OPENERS + LISTERS)

    code = _check(config, output)

    captured = capsysbinary.readouterr()
    assert code == 0
    assert captured.err == b""
    assert _report(output, captured.out) == golden_path(config).read_bytes()
    assert os.path.realpath(config) in calls
    assert [call for call in calls if _under_any(call, packages)] == []
    assert _imported_package_modules(packages) == []


@pytest.mark.parametrize("output", ["-", "report.json"])
def test_full_surface_lists_only_package_directories_and_opens_no_file_there(
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
    output: str,
) -> None:
    config = CONFIGS["full-surface"]
    packages = _packages(config)
    opened = _record(monkeypatch, OPENERS)
    scanned = _record(monkeypatch, [(os, "scandir")])
    listed = _record(monkeypatch, [(os, "listdir")])

    code = _check(config, output)

    captured = capsysbinary.readouterr()
    assert code == 0
    assert captured.err == b""
    assert _report(output, captured.out) == golden_path(config).read_bytes()
    assert os.path.realpath(config) in opened
    assert [call for call in opened if _under_any(call, packages)] == []
    assert scanned != []
    assert [call for call in scanned if not _under_any(call, packages)] == []
    assert [call for call in listed if _under_any(call, packages)] == []
    assert _imported_package_modules(packages) == []


@pytest.mark.parametrize("fixture", FIXTURES)
def test_source_that_raises_on_import_does_not_change_outcome(
    tmp_path: Path,
    capsysbinary: pytest.CaptureFixture[bytes],
    fixture: str,
) -> None:
    copy = tmp_path / fixture
    shutil.copytree(CONFIGS[fixture].parent, copy)
    config = copy / "dogwatch.toml"
    packages = _packages(config)
    for directory in packages.values():
        Path(directory, "__init__.py").write_bytes(
            b'raise RuntimeError("fixture code must never be imported")\n'
        )

    code = _check(config, "-")

    captured = capsysbinary.readouterr()
    assert code == 0
    assert captured.err == b""
    assert captured.out == golden_path(CONFIGS[fixture]).read_bytes()
    assert _imported_package_modules(packages) == []


@pytest.mark.parametrize("fixture", FIXTURES)
def test_run_succeeds_with_network_disabled(
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
    fixture: str,
) -> None:
    config = CONFIGS[fixture]
    packages = _packages(config)
    attempts: list[object] = []

    def refuse(self: socket.socket, address: object) -> None:
        attempts.append(address)
        raise OSError("network access is disabled in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)

    code = _check(config, "-")

    captured = capsysbinary.readouterr()
    assert code == 0
    assert captured.err == b""
    assert captured.out == golden_path(config).read_bytes()
    assert attempts == []
    assert _imported_package_modules(packages) == []
