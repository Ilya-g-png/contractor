import sys
from pathlib import Path

import pytest

from dogwatch.openapi import runner


def _executable(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "fake-oasdiff"
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o700)
    return path


def test_runner_uses_fixed_argv_and_private_read_only_inputs(tmp_path: Path) -> None:
    executable = _executable(
        tmp_path,
        """
import json, os, pathlib, sys
args = sys.argv[1:]
base, candidate = [pathlib.Path(value) for value in args[-2:]]
assert args[:-2] == [
    'changelog', '--format=json', '--level=INFO',
    '--allow-external-refs=false', '--',
]
assert base.parent.resolve() == candidate.parent.resolve()
assert base.parent.resolve() == pathlib.Path.cwd().resolve()
assert base.parent.stat().st_mode & 0o077 == 0
assert base.stat().st_mode & 0o222 == 0
assert candidate.stat().st_mode & 0o222 == 0
assert base.read_bytes() == b'{"base":true}'
assert candidate.read_bytes() == b'{"candidate":true}'
assert os.read(0, 1) == b''
print(json.dumps([{'id':'api-path-removed','text':'removed','level':3,'fingerprint':'abcdef123456'}]))
""",
    )

    result = runner.run_oasdiff(executable, b'{"base":true}', b'{"candidate":true}')

    assert result.diagnostics == ()
    assert result.records == (
        {
            "id": "api-path-removed",
            "text": "removed",
            "level": 3,
            "fingerprint": "abcdef123456",
        },
    )


def test_runner_accepts_empty_success(tmp_path: Path) -> None:
    executable = _executable(tmp_path, "print('[]')\n")
    result = runner.run_oasdiff(executable, b"{}", b"{}")
    assert result.records == ()
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("body", "diagnostic_id"),
    [
        ("import time; time.sleep(10)\n", "openapi-tool-timeout"),
        ("print('x' * 200)\n", "openapi-tool-stdout-limit-exceeded"),
        (
            "import sys; sys.stderr.write('x' * 200)\n",
            "openapi-tool-stderr-limit-exceeded",
        ),
        ("raise SystemExit(3)\n", "openapi-tool-failed"),
        ("print('{bad')\n", "openapi-tool-failed"),
        ('print(\'[{}, {"id": "valid"}]\')\n', "openapi-tool-failed"),
    ],
)
def test_runner_failures_never_return_partial_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    diagnostic_id: str,
) -> None:
    monkeypatch.setattr(
        runner,
        "TIMEOUT_SECONDS",
        0.25 if diagnostic_id == "openapi-tool-timeout" else 2,
    )
    monkeypatch.setattr(runner, "STDOUT_LIMIT", 100)
    monkeypatch.setattr(runner, "STDERR_LIMIT", 100)
    result = runner.run_oasdiff(_executable(tmp_path, body), b"{}", b"{}")
    assert result.records is None
    assert result.diagnostics[0].id == diagnostic_id
    assert result.diagnostics[0].severity == "error"


def test_runner_startup_failure_is_diagnostic(tmp_path: Path) -> None:
    result = runner.run_oasdiff(tmp_path / "missing", b"{}", b"{}")
    assert result.records is None
    assert result.diagnostics[0].id == "openapi-tool-failed"


def test_runner_collects_both_streams_concurrently(tmp_path: Path) -> None:
    executable = _executable(
        tmp_path,
        "import sys\nsys.stderr.write('e' * 65536)\nprint('[]')\n",
    )
    result = runner.run_oasdiff(executable, b"{}", b"{}")
    assert result.records == ()
    assert result.diagnostics == ()


def test_runner_does_not_use_shell(tmp_path: Path) -> None:
    executable = _executable(tmp_path, "print('[]')\n")
    renamed = tmp_path / "fake; touch injected"
    executable.rename(renamed)
    result = runner.run_oasdiff(renamed, b"{}", b"{}")
    assert result.records == ()
    assert not (tmp_path / "injected").exists()
