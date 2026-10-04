import builtins
import io
import os
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dogwatch.cli import main
from tests.test_cli import expected_report, minimal_project


@pytest.fixture
def package_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.chdir(tmp_path)
    minimal_project(tmp_path)
    return os.path.realpath(tmp_path / "src" / "acme_shop")


def _under(path: str, directory: str) -> bool:
    return path == directory or path.startswith(directory + os.sep)


def _package_modules(directory: str) -> list[str]:
    return [
        name
        for name, module in list(sys.modules.items())
        if isinstance(getattr(module, "__file__", None), str)
        and _under(os.path.realpath(module.__file__ or ""), directory)
    ]


@pytest.mark.parametrize("output", ["-", "report.json"])
def test_run_never_opens_lists_or_imports_package_directory(
    package_dir: str,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
    output: str,
) -> None:
    calls: list[str] = []

    def recording(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            target = args[0] if args else kwargs.get("path", kwargs.get("file", "."))
            if isinstance(target, (str, bytes, os.PathLike)):
                calls.append(os.path.realpath(os.fsdecode(target)))
            return fn(*args, **kwargs)

        return wrapper

    for module, attr in [
        (builtins, "open"),
        (io, "open"),
        (io, "open_code"),
        (os, "open"),
        (os, "scandir"),
        (os, "listdir"),
    ]:
        monkeypatch.setattr(module, attr, recording(getattr(module, attr)))

    code = main(["check", "--output", output])

    assert code == 0
    assert capsysbinary.readouterr().err == b""
    assert os.path.realpath("dogwatch.toml") in calls
    assert [call for call in calls if _under(call, package_dir)] == []
    assert "acme_shop" not in sys.modules
    assert _package_modules(package_dir) == []


def test_run_succeeds_with_network_disabled(
    package_dir: str,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    attempts: list[object] = []

    def refuse(self: socket.socket, address: object) -> None:
        attempts.append(address)
        raise OSError("network access is disabled in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)

    code = main(["check", "--output", "-"])

    captured = capsysbinary.readouterr()
    assert code == 0
    assert captured.err == b""
    assert captured.out == expected_report(Path("dogwatch.toml").read_bytes())
    assert attempts == []
    assert "acme_shop" not in sys.modules
    assert _package_modules(package_dir) == []
