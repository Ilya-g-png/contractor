import errno
import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from dogwatch.output import write_report

DATA = b'{\n  "findings": []\n}\n'


@pytest.fixture(autouse=True)
def _chdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def restore_umask() -> Iterator[None]:
    mask = os.umask(0o022)
    os.umask(mask)
    yield
    os.umask(mask)


def _temp_files(directory: Path) -> list[Path]:
    return sorted(directory.glob(".*.tmp"))


def _spy(
    monkeypatch: pytest.MonkeyPatch, events: list[tuple[str, Any]], name: str
) -> None:
    real: Callable[..., Any] = getattr(os, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        events.append((name, args))
        return real(*args, **kwargs)

    monkeypatch.setattr(os, name, wrapper)


def test_writes_exact_bytes_and_leaves_no_temp_file(tmp_path: Path) -> None:
    write_report(DATA, "report.json")

    assert (tmp_path / "report.json").read_bytes() == DATA
    assert _temp_files(tmp_path) == []


def test_replaces_existing_target(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "report.json").write_bytes(b"old contents that are longer\n")

    write_report(DATA, "out/report.json")

    assert (tmp_path / "out" / "report.json").read_bytes() == DATA
    assert _temp_files(tmp_path / "out") == []


def test_temp_file_is_named_after_target_in_target_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "out").mkdir()
    events: list[tuple[str, Any]] = []
    _spy(monkeypatch, events, "replace")

    write_report(DATA, "out/report.json")

    [(_, (temp, target))] = events
    assert target == "out/report.json"
    assert Path(temp).parent.resolve() == (tmp_path / "out").resolve()
    assert re.fullmatch(r"\.report\.json\.[A-Za-z0-9_]+\.tmp", os.path.basename(temp))


@pytest.mark.usefixtures("restore_umask")
def test_fsyncs_then_chmods_then_replaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.umask(0o022)
    events: list[tuple[str, Any]] = []
    for name in ("fsync", "chmod", "replace"):
        _spy(monkeypatch, events, name)

    write_report(DATA, "report.json")

    assert [name for name, _ in events] == ["fsync", "chmod", "replace"]
    temp = events[2][1][0]
    assert events[1][1] == (temp, 0o644)


@pytest.mark.usefixtures("restore_umask")
@pytest.mark.parametrize("umask", [0o022, 0o002, 0o077, 0o000])
def test_report_mode_is_0666_masked_by_umask(tmp_path: Path, umask: int) -> None:
    os.umask(umask)

    write_report(DATA, "report.json")

    assert (tmp_path / "report.json").stat().st_mode & 0o777 == 0o666 & ~umask


@pytest.mark.parametrize("failing", ["fsync", "chmod", "replace"])
@pytest.mark.parametrize("preexisting", [False, True])
def test_os_error_at_any_step_unlinks_temp_and_keeps_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str, preexisting: bool
) -> None:
    target = tmp_path / "report.json"
    if preexisting:
        target.write_bytes(b"previous\n")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(os, failing, fail)

    with pytest.raises(OSError) as excinfo:
        write_report(DATA, "report.json")

    assert excinfo.value.errno == errno.ENOSPC
    assert _temp_files(tmp_path) == []
    if preexisting:
        assert target.read_bytes() == b"previous\n"
    else:
        assert not target.exists()


def test_unlink_failure_during_cleanup_does_not_mask_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, os.strerror(errno.EIO))

    monkeypatch.setattr(os, "replace", fail)
    monkeypatch.setattr(os, "unlink", fail)

    with pytest.raises(OSError) as excinfo:
        write_report(DATA, "report.json")

    assert excinfo.value.errno == errno.EIO


def test_missing_directory_raises_and_creates_nothing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        write_report(DATA, "absent/report.json")

    assert list(tmp_path.iterdir()) == []


def test_dash_writes_to_stdout_buffer(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    write_report(DATA, "-")

    captured = capsysbinary.readouterr()
    assert captured.out == DATA
    assert captured.err == b""
    assert list(tmp_path.iterdir()) == []
