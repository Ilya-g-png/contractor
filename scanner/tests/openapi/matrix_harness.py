import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

from dogwatch.cli import main
from dogwatch.openapi import coordinator, runner
from dogwatch.openapi.tool import ToolResult
from dogwatch.report import serialize_canonical

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SUBSTITUTE = Path(__file__).resolve().with_name("oasdiff_substitute.py")
CASE_NAME = "case.json"
POLICY_NAME = "dogwatch.toml"
REPORT_NAME = "expected-report.json"
INVOCATION_NAME = "expected-invocation.json"
PACKAGE_INIT = Path("src", "fixture_api", "__init__.py")
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Dogwatch Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@dogwatch.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_NAME": "Dogwatch Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@dogwatch.invalid",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


@dataclass(frozen=True)
class FixtureCase:
    name: str
    directory: Path
    category: str
    baseline_ref: str
    tool: dict[str, Any] | None
    exit_code: int
    check_ids: tuple[str, ...]
    diagnostic_ids: tuple[str, ...]

    @property
    def report_path(self) -> Path:
        return self.directory / REPORT_NAME

    @property
    def invocation_path(self) -> Path:
        return self.directory / INVOCATION_NAME


@dataclass(frozen=True)
class MatrixRun:
    exit_code: int
    report: bytes
    stderr: str
    baseline_commit: str
    invocations: tuple[bytes, ...]
    tool_inputs: dict[str, str] | None


@dataclass(frozen=True)
class _Call:
    argv: list[str]
    cwd: Path
    environment: dict[str, str]
    timeout_seconds: float
    stdout_limit: int
    stderr_limit: int


def discover_cases() -> list[FixtureCase]:
    return [load_case(path.parent) for path in sorted(FIXTURES.glob(f"*/{CASE_NAME}"))]


def load_case(directory: Path) -> FixtureCase:
    data: dict[str, Any] = json.loads((directory / CASE_NAME).read_bytes())
    expected: dict[str, Any] = data["expected"]
    return FixtureCase(
        name=directory.name,
        directory=directory,
        category=data["category"],
        baseline_ref=data.get("baseline_ref", "baseline"),
        tool=data["tool"],
        exit_code=expected["exit_code"],
        check_ids=tuple(expected["check_ids"]),
        diagnostic_ids=tuple(expected["diagnostic_ids"]),
    )


def materialize(case: FixtureCase, repository: Path) -> str:
    repository.mkdir()
    _git(repository, "init", "-q", "--object-format=sha1")
    base_files = _copy_tree(case.directory / "base", repository)
    _git(repository, "add", "-A")
    _git(repository, "commit", "-q", "-m", "baseline")
    _git(repository, "tag", "baseline")
    commit = _git(repository, "rev-parse", "baseline^{commit}")
    for relative in base_files:
        (repository / relative).unlink()
    _copy_tree(case.directory / "candidate", repository)
    shutil.copyfile(case.directory / POLICY_NAME, repository / POLICY_NAME)
    (repository / PACKAGE_INIT).parent.mkdir(parents=True)
    (repository / PACKAGE_INIT).write_bytes(b"")
    return commit


def run_case(case: FixtureCase) -> MatrixRun:
    with tempfile.TemporaryDirectory(prefix="dogwatch-openapi-matrix-") as tmp:
        work = Path(tmp)
        repository = work / "repo"
        commit = materialize(case, repository)
        state = work / "substitute"
        state.mkdir()
        launcher = state / "oasdiff"
        calls: list[_Call] = []
        stderr = io.StringIO()
        output = work / "report.json"
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    coordinator,
                    "resolve_verified_oasdiff",
                    _substitute_provider(case, state, launcher),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    runner, "collect_process", _recording_collector(case, calls)
                )
            )
            stack.enter_context(contextlib.redirect_stderr(stderr))
            code = main(
                [
                    "check",
                    "--config",
                    str(repository / POLICY_NAME),
                    "--baseline-ref",
                    case.baseline_ref,
                    "--output",
                    str(output),
                ]
            )
        observation_path = state / "observation.json"
        observation: dict[str, Any] | None = (
            json.loads(observation_path.read_bytes())
            if observation_path.exists()
            else None
        )
        invocations = tuple(
            serialize_canonical(_invocation_record(call, observation, launcher))
            for call in calls
        )
        return MatrixRun(
            exit_code=code,
            report=output.read_bytes(),
            stderr=stderr.getvalue(),
            baseline_commit=commit,
            invocations=invocations,
            tool_inputs=(
                None
                if observation is None
                else {
                    side: item["content"]
                    for side, item in observation["inputs"].items()
                }
            ),
        )


def _substitute_provider(
    case: FixtureCase, state: Path, launcher: Path
) -> Callable[[Path], ToolResult]:
    def provide(cache_dir: Path) -> ToolResult:
        if case.tool is None:
            raise AssertionError(f"{case.name}: oasdiff must not be resolved")
        (state / "behavior.json").write_text(json.dumps(case.tool), "utf-8")
        launcher.write_text(
            "#!/bin/sh\nexec "
            + " ".join(shlex.quote(part) for part in (sys.executable, str(SUBSTITUTE)))
            + f' {shlex.quote(str(state))} "$@"\n',
            "utf-8",
        )
        launcher.chmod(0o500)
        return ToolResult(launcher, ())

    return provide


_Collector = Callable[
    [list[str], Path, dict[str, str], float, int, int],
    tuple[bytes, bytes, int | None, str | None],
]


def _recording_collector(case: FixtureCase, calls: list[_Call]) -> _Collector:
    collect = runner.collect_process

    def record(
        argv: list[str],
        cwd: Path,
        environment: dict[str, str],
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
    ) -> tuple[bytes, bytes, int | None, str | None]:
        calls.append(
            _Call(
                list(argv),
                cwd,
                dict(environment),
                timeout_seconds,
                stdout_limit,
                stderr_limit,
            )
        )
        # The timeout fixture shortens only the wall-clock wait; the record
        # keeps the deadline the runner actually requested.
        deadline = (case.tool or {}).get("deadline_seconds", timeout_seconds)
        return collect(argv, cwd, environment, deadline, stdout_limit, stderr_limit)

    return record


def _invocation_record(
    call: _Call, observation: dict[str, Any] | None, launcher: Path
) -> dict[str, Any]:
    if observation is None:
        raise AssertionError("the substitute did not record its invocation")
    private = {str(call.cwd), os.path.realpath(call.cwd)}

    def placeholder(value: str) -> str:
        if value == str(launcher):
            return "{substitute}"
        for prefix in private:
            if value == prefix:
                return "{private}"
            if value.startswith(prefix + "/"):
                return "{private}" + value[len(prefix) :]
        return value

    return {
        "argv": [placeholder(argument) for argument in call.argv],
        "cwd": placeholder(str(call.cwd)),
        "environment": {
            name: placeholder(value) for name, value in call.environment.items()
        },
        "limits": {
            "timeout_seconds": call.timeout_seconds,
            "stdout_bytes": call.stdout_limit,
            "stderr_bytes": call.stderr_limit,
        },
        "observed": {
            "cwd": placeholder(observation["cwd"]),
            "private_directory_mode": f"{observation['directory_mode']:04o}",
            "stdin_bytes": observation["stdin_bytes"],
            "inputs": {
                side: {"mode": f"{item['mode']:04o}", "sha256": item["sha256"]}
                for side, item in observation["inputs"].items()
            },
        },
    }


def _copy_tree(source: Path, destination: Path) -> list[Path]:
    copied: list[Path] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        (destination / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination / relative)
        copied.append(relative)
    return copied


def _git(repository: Path, *arguments: str) -> str:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    environment.update(
        GIT_IDENTITY, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull
    )
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        env=environment,
        stdin=subprocess.DEVNULL,
        text=True,
    ).stdout.strip()
