import errno
import hashlib
import inspect
import itertools
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dogwatch import cli
from dogwatch.cli import main
from dogwatch.config import DogwatchConfig, load_policy
from dogwatch.diagnostics import SOURCE_SYNTAX_INVALID, Diagnostic
from dogwatch.openapi.runner import RunnerResult
from dogwatch.openapi.tool import ToolResult
from dogwatch.report import Finding, Locator, derive_status

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "report-0.3.schema.json"
MINIMAL = '[python]\n\n[[python.packages]]\nname = "acme_shop"\nroot = "src"\n'
PACKAGE_MODULES = ("__init__.py", "orders.py", "payments.py")
DIAGNOSTIC_LINE = re.compile(
    rb"^dogwatch:(config-invalid|config-not-found): .+$|^dogwatch: error: .+$"
)
OLD_BYTES = b"previous report\n"
OLD_MTIME_NS = 1_000_000_000_000_000_000


class Run(NamedTuple):
    code: int
    out: bytes
    err: bytes


def minimal_project(root: Path, toml_text: str = MINIMAL) -> Path:
    package = root / "src" / "acme_shop"
    package.mkdir(parents=True)
    for module in PACKAGE_MODULES:
        (package / module).write_text("raise SystemExit('executed')\n")
    config = root / "dogwatch.toml"
    config.write_bytes(toml_text.encode("utf-8"))
    return config


def expected_report(raw: bytes) -> bytes:
    digest = hashlib.sha256(raw).hexdigest()
    return (
        "{\n"
        '  "diagnostics": [],\n'
        '  "findings": [],\n'
        '  "policy": {\n'
        '    "digest": {\n'
        f'      "sha256": "{digest}"\n'
        "    },\n"
        '    "path": "dogwatch.toml"\n'
        "  },\n"
        '  "scanner": {\n'
        '    "name": "dogwatch",\n'
        '    "version": "0.1.0"\n'
        "  },\n"
        '  "schema_version": "0.3",\n'
        '  "status": "pass"\n'
        "}\n"
    ).encode()


def assert_exit_contract(run: Run) -> None:
    assert run.code in (0, 2), run
    if run.code == 0:
        assert run.err == b""
    elif run.err.startswith(b"usage: "):
        assert_usage_error(run)
    else:
        lines = run.err.splitlines()
        assert lines
        assert all(DIAGNOSTIC_LINE.match(line) for line in lines), run.err


def assert_usage_error(run: Run) -> None:
    assert run.code == 2
    assert run.out == b""
    assert run.err.startswith(b"usage: dogwatch ")
    assert re.fullmatch(rb"dogwatch: error: .+", run.err.splitlines()[-1])


@pytest.fixture(autouse=True)
def _chdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def run(capsysbinary: pytest.CaptureFixture[bytes]) -> Callable[..., Run]:
    def _run(*argv: str) -> Run:
        try:
            code = main(list(argv))
        except SystemExit as exc:
            assert isinstance(exc.code, int)
            code = exc.code
        captured = capsysbinary.readouterr()
        return Run(code, captured.out, captured.err)

    return _run


def _entry_points() -> dict[str, list[str]]:
    return {
        "module": [sys.executable, "-m", "dogwatch"],
        "script": [os.path.join(os.path.dirname(sys.executable), "dogwatch")],
    }


def spawn(entry: str, *argv: str, cwd: Path) -> Run:
    proc = subprocess.run(
        [*_entry_points()[entry], *argv], cwd=cwd, capture_output=True, check=False
    )
    return Run(proc.returncode, proc.stdout, proc.stderr)


def _listing(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# --- IC-1 response matrix -------------------------------------------------


def test_version_prints_name_and_version(run: Callable[..., Run]) -> None:
    result = run("--version")

    assert result == Run(0, b"dogwatch 0.1.0\n", b"")


def test_valid_config_file_output(run: Callable[..., Run], tmp_path: Path) -> None:
    config = minimal_project(tmp_path)

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert result == Run(0, b"", b"")
    assert (tmp_path / "report.json").read_bytes() == expected_report(
        config.read_bytes()
    )
    assert _listing(tmp_path) == sorted(
        ["dogwatch.toml", "report.json", "src", "src/acme_shop"]
        + [f"src/acme_shop/{m}" for m in PACKAGE_MODULES]
    )


def test_openapi_declaration_requires_baseline_ref_in_report(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    minimal_project(
        tmp_path,
        MINIMAL
        + '[[openapi.contracts]]\nid = "public-api"\npath = "api/openapi.yaml"\n',
    )
    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")
    report = validate_report((tmp_path / "report.json").read_bytes())
    assert result.code == 2
    assert report["status"] == "inconclusive"
    assert report["findings"] == []
    assert report["diagnostics"][0]["source"] == "openapi"
    assert report["diagnostics"][0]["id"] == "openapi-baseline-ref-required"
    assert (
        result.err == b"dogwatch:openapi-baseline-ref-required: "
        b"OpenAPI contracts require --baseline-ref\n"
    )


def test_openapi_command_uses_resolved_baseline_for_no_change(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(
        tmp_path,
        MINIMAL
        + '[[openapi.contracts]]\nid = "public-api"\npath = "api/openapi.json"\n',
    )
    contract = tmp_path / "api" / "openapi.json"
    contract.parent.mkdir()
    contract.write_text(
        '{"openapi":"3.0.3","info":{"title":"Example","version":"1"},"paths":{}}'
    )
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "api/openapi.json"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.email=test@example.test",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )
    from dogwatch.openapi import coordinator

    monkeypatch.setattr(
        coordinator,
        "resolve_verified_oasdiff",
        lambda cache: ToolResult(tmp_path / "verified-oasdiff", ()),
    )

    def unchanged(executable: Path, base: bytes, candidate: bytes) -> RunnerResult:
        assert base == candidate
        return RunnerResult((), ())

    monkeypatch.setattr(coordinator, "run_oasdiff", unchanged)
    result = run(
        "check",
        "--config",
        "dogwatch.toml",
        "--baseline-ref",
        "HEAD",
        "--output",
        "report.json",
    )
    report = validate_report((tmp_path / "report.json").read_bytes())
    assert result == Run(0, b"", b"")
    assert report["status"] == "pass"
    assert report["findings"] == report["diagnostics"] == []


def test_valid_config_stdout_output(run: Callable[..., Run], tmp_path: Path) -> None:
    config = minimal_project(tmp_path)
    before = _listing(tmp_path)

    result = run("check", "--config", "dogwatch.toml", "--output", "-")

    assert result == Run(0, expected_report(config.read_bytes()), b"")
    assert _listing(tmp_path) == before


def test_defaults_read_dogwatch_toml_and_write_dogwatch_report_json(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    config = minimal_project(tmp_path)

    result = run("check")

    assert result == Run(0, b"", b"")
    assert (tmp_path / "dogwatch-report.json").read_bytes() == expected_report(
        config.read_bytes()
    )


def test_default_config_missing_reports_default_path(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    result = run("check")

    assert result == Run(
        2, b"", b"dogwatch:config-not-found: ./dogwatch.toml does not exist\n"
    )
    assert list(tmp_path.iterdir()) == []


def test_config_dash_is_a_file_named_dash(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    minimal_project(tmp_path)
    (tmp_path / "-").write_bytes(MINIMAL.encode())

    result = run("check", "--config", "-", "--output", "report.json")

    assert result == Run(0, b"", b"")
    report = json.loads((tmp_path / "report.json").read_bytes())
    assert report["policy"]["path"] == "-"


def test_v0_missing_config(run: Callable[..., Run], tmp_path: Path) -> None:
    result = run("check", "--config", "missing.toml", "--output", "report.json")

    assert result == Run(
        2, b"", b"dogwatch:config-not-found: missing.toml does not exist\n"
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("toml_text", "expected_err"),
    [
        (
            MINIMAL + '[openapi]\nseverity = "error"\n',
            b"dogwatch:config-invalid: openapi.severity must be an array of tables\n",
        ),
        (
            "",
            b"dogwatch:config-invalid: dogwatch.toml requires at least one "
            b"[[python.packages]] entry\n",
        ),
    ],
    ids=["v3-unknown-key", "v3-empty"],
)
def test_v3_failure_emits_one_line(
    run: Callable[..., Run], tmp_path: Path, toml_text: str, expected_err: bytes
) -> None:
    minimal_project(tmp_path, toml_text)
    before = _listing(tmp_path)

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert result == Run(2, b"", expected_err)
    assert _listing(tmp_path) == before


def test_v2_invalid_toml_emits_one_line_with_line_number(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    minimal_project(tmp_path, '[python]\n\n[[python.packages]\nname = "x"\n')
    before = _listing(tmp_path)

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert result.code == 2
    assert result.out == b""
    assert re.fullmatch(
        rb"dogwatch:config-invalid: dogwatch\.toml:3: invalid TOML: .+\n", result.err
    )
    assert _listing(tmp_path) == before


def test_v1_directory_config(run: Callable[..., Run], tmp_path: Path) -> None:
    (tmp_path / "conf").mkdir()

    result = run("check", "--config", "conf", "--output", "report.json")

    assert result == Run(
        2, b"", b"dogwatch:config-invalid: conf is not a readable file\n"
    )
    assert _listing(tmp_path) == ["conf"]


def test_v4_failures_emit_one_line_each_in_order(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    minimal_project(
        tmp_path,
        MINIMAL
        + '[[python.packages]]\nname = "ghost"\nroot = "src"\n'
        + '[[python.packages]]\nname = "acme_shop"\nroot = "lib"\n',
    )
    (tmp_path / "lib" / "acme_shop").mkdir(parents=True)
    before = _listing(tmp_path)

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert result == Run(
        2,
        b"",
        b"dogwatch:config-invalid: python.packages[1]: package 'ghost': "
        b"directory 'src/ghost' does not exist\n"
        b"dogwatch:config-invalid: python.packages[2]: package 'acme_shop' "
        b"split across roots 'src', 'lib'\n",
    )
    assert _listing(tmp_path) == before


def test_output_same_as_config(run: Callable[..., Run], tmp_path: Path) -> None:
    config = minimal_project(tmp_path)
    raw = config.read_bytes()

    result = run("check", "--config", "dogwatch.toml", "--output", "./dogwatch.toml")

    assert result == Run(
        2,
        b"",
        b"dogwatch: error: output path ./dogwatch.toml is the same file as "
        b"config dogwatch.toml\n",
    )
    assert config.read_bytes() == raw


def test_output_missing_directory(run: Callable[..., Run], tmp_path: Path) -> None:
    minimal_project(tmp_path)
    before = _listing(tmp_path)

    result = run("check", "--config", "dogwatch.toml", "--output", "nope/out.json")

    assert result == Run(
        2,
        b"",
        b"dogwatch: error: cannot write report to nope/out.json: "
        + os.strerror(errno.ENOENT).encode()
        + b"\n",
    )
    assert _listing(tmp_path) == before


@pytest.fixture
def read_only_dir(tmp_path: Path) -> Iterator[Path]:
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    directory = tmp_path / "ro"
    directory.mkdir()
    yield directory
    directory.chmod(0o755)


def test_output_permission_denied(
    run: Callable[..., Run], tmp_path: Path, read_only_dir: Path
) -> None:
    minimal_project(tmp_path)
    read_only_dir.chmod(0o555)

    result = run("check", "--config", "dogwatch.toml", "--output", "ro/out.json")

    assert result == Run(
        2,
        b"",
        b"dogwatch: error: cannot write report to ro/out.json: "
        + os.strerror(errno.EACCES).encode()
        + b"\n",
    )
    assert list(read_only_dir.iterdir()) == []


def test_output_no_space_left(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(tmp_path)
    (tmp_path / "report.json").write_bytes(OLD_BYTES)

    def no_space(fd: int) -> None:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(os, "fsync", no_space)

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert result == Run(
        2,
        b"",
        b"dogwatch: error: cannot write report to report.json: "
        + os.strerror(errno.ENOSPC).encode()
        + b"\n",
    )
    assert (tmp_path / "report.json").read_bytes() == OLD_BYTES
    assert list(tmp_path.glob(".*.tmp")) == []


def test_broken_stdout_pipe(tmp_path: Path) -> None:
    minimal_project(tmp_path)
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        proc = subprocess.run(
            [*_entry_points()["module"], "check", "--output", "-"],
            cwd=tmp_path,
            stdout=write_end,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        os.close(write_end)

    assert proc.returncode == 2
    assert proc.stderr == (
        b"dogwatch: error: cannot write report to -: "
        + os.strerror(errno.EPIPE).encode()
        + b"\n"
    )


@pytest.mark.parametrize(
    "argv",
    [(), ("check", "--bogus"), ("scan",), ("check", "--output")],
    ids=["no-subcommand", "unknown-flag", "unknown-subcommand", "missing-value"],
)
def test_usage_errors(
    run: Callable[..., Run], tmp_path: Path, argv: tuple[str, ...]
) -> None:
    minimal_project(tmp_path)
    before = _listing(tmp_path)

    result = run(*argv)

    assert_usage_error(result)
    assert _listing(tmp_path) == before


# --- Processing order -----------------------------------------------------


def test_processing_order_is_validate_check_build_write(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(tmp_path)
    calls: list[str] = []

    def record(name: str) -> None:
        real: Callable[..., Any] = getattr(cli, name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            return real(*args, **kwargs)

        monkeypatch.setattr(cli, name, wrapper)

    order = (
        "load_policy",
        "_same_file",
        "scan",
        "build_report",
        "serialize_canonical",
        "write_report",
        "render_diagnostics",
        "exit_code_for_status",
    )
    for name in order:
        record(name)

    assert run("check", "--output", "report.json").code == 0
    assert calls == list(order)


def test_config_validation_precedes_output_target_check(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    minimal_project(tmp_path, MINIMAL + '[openapi]\nseverity = "error"\n')

    result = run("check", "--config", "dogwatch.toml", "--output", "dogwatch.toml")

    assert result.err.startswith(b"dogwatch:config-invalid: ")


def test_output_target_check_precedes_write(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(tmp_path)
    writes: list[str] = []
    monkeypatch.setattr(cli, "write_report", lambda data, out: writes.append(out))

    result = run("check", "--config", "dogwatch.toml", "--output", "dogwatch.toml")

    assert result.err.startswith(b"dogwatch: error: output path ")
    assert writes == []


# --- INV-S3 / INV-S4 / INV-S5 ---------------------------------------------


def _seed(target: Path) -> None:
    target.write_bytes(OLD_BYTES)
    os.utime(target, ns=(OLD_MTIME_NS, OLD_MTIME_NS))


def _entries(*pairs: tuple[str, str]) -> str:
    return "[python]\n" + "".join(
        f'[[python.packages]]\nname = "{name}"\nroot = "{root}"\n'
        for name, root in pairs
    )


Setup = Callable[[Path], tuple[list[str], Path]]


def _config_case(toml_text: str | None, dirs: tuple[str, ...] = ()) -> Setup:
    def setup(root: Path) -> tuple[list[str], Path]:
        for d in dirs:
            (root / d).mkdir(parents=True, exist_ok=True)
        if toml_text is not None:
            (root / "dogwatch.toml").write_text(toml_text, encoding="utf-8")
        return ["--output", "report.json"], root / "report.json"

    return setup


def _missing_output_dir(root: Path) -> tuple[list[str], Path]:
    minimal_project(root)
    return ["--output", "absent/report.json"], root / "absent" / "report.json"


def _output_is_config(root: Path) -> tuple[list[str], Path]:
    minimal_project(root)
    return ["--output", "dogwatch.toml"], root / "dogwatch.toml"


def _output_symlink_to_config(root: Path) -> tuple[list[str], Path]:
    minimal_project(root)
    (root / "alias.json").symlink_to("dogwatch.toml")
    return ["--output", "alias.json"], root / "alias.json"


def _output_hardlink_to_config(root: Path) -> tuple[list[str], Path]:
    minimal_project(root)
    (root / "hard.json").hardlink_to(root / "dogwatch.toml")
    return ["--output", "hard.json"], root / "hard.json"


EXIT_2_CASES: dict[str, tuple[Setup, tuple[bool, ...]]] = {
    "sc013-missing-dir": (_config_case(_entries(("acme_shop", "src"))), (False, True)),
    "sc013-duplicate": (
        _config_case(
            _entries(("acme_shop", "src"), ("acme_shop", "src")), ("src/acme_shop",)
        ),
        (False, True),
    ),
    "sc013-nested": (
        _config_case(
            _entries(("acme_shop", "src"), ("inner", "src/acme_shop")),
            ("src/acme_shop/inner",),
        ),
        (False, True),
    ),
    "sc013-split": (
        _config_case(
            _entries(("acme_shop", "src"), ("acme_shop", "lib")),
            ("src/acme_shop", "lib/acme_shop"),
        ),
        (False, True),
    ),
    "v0": (_config_case(None), (False, True)),
    "v2": (_config_case("[python\n"), (False, True)),
    "v3": (
        _config_case(MINIMAL + "[python.rules]\n", ("src/acme_shop",)),
        (False, True),
    ),
    "missing-output-dir": (_missing_output_dir, (False,)),
    "output-is-config": (_output_is_config, (True,)),
    "output-symlink-to-config": (_output_symlink_to_config, (True,)),
    "output-hardlink-to-config": (_output_hardlink_to_config, (True,)),
}


@pytest.mark.parametrize(
    ("case", "preexisting"),
    [
        pytest.param(name, pre, id=f"{name}-{'existing' if pre else 'absent'}")
        for name, (_, variants) in EXIT_2_CASES.items()
        for pre in variants
    ],
)
def test_exit_2_leaves_target_untouched(
    run: Callable[..., Run], tmp_path: Path, case: str, preexisting: bool
) -> None:
    setup, _ = EXIT_2_CASES[case]
    argv, target = setup(tmp_path)
    if preexisting and not target.exists():
        _seed(target)
    before = (target.read_bytes(), target.stat().st_mtime_ns) if preexisting else None
    was_symlink = target.is_symlink()

    result = run("check", *argv)

    assert result.code == 2
    assert result.out == b""
    assert_exit_contract(result)
    if preexisting:
        assert (target.read_bytes(), target.stat().st_mtime_ns) == before
        assert target.is_symlink() == was_symlink
    else:
        assert not os.path.lexists(target)
    if target.parent.exists():
        assert list(target.parent.glob(".*.tmp")) == []


@pytest.mark.parametrize("preexisting", [False, True])
def test_exit_2_read_only_directory_leaves_target_untouched(
    run: Callable[..., Run], tmp_path: Path, read_only_dir: Path, preexisting: bool
) -> None:
    minimal_project(tmp_path)
    target = read_only_dir / "report.json"
    if preexisting:
        _seed(target)
    read_only_dir.chmod(0o555)

    result = run("check", "--output", "ro/report.json")

    assert result.code == 2
    assert result.out == b""
    assert_exit_contract(result)
    if preexisting:
        assert (target.read_bytes(), target.stat().st_mtime_ns) == (
            OLD_BYTES,
            OLD_MTIME_NS,
        )
    else:
        assert not target.exists()
    assert list(read_only_dir.glob(".*.tmp")) == []


def test_success_replaces_preexisting_target(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    config = minimal_project(tmp_path)
    _seed(tmp_path / "report.json")

    result = run("check", "--output", "report.json")

    assert result == Run(0, b"", b"")
    assert (tmp_path / "report.json").read_bytes() == expected_report(
        config.read_bytes()
    )
    assert list(tmp_path.glob(".*.tmp")) == []


# --- Entry points ---------------------------------------------------------


def test_console_script_is_installed_next_to_interpreter() -> None:
    assert os.access(_entry_points()["script"][0], os.X_OK)


@pytest.mark.parametrize(
    "argv",
    [
        ("--version",),
        (),
        ("check", "--output", "-"),
        ("check", "--output", "report.json"),
        ("check", "--config", "missing.toml"),
        ("check", "--output", "dogwatch.toml"),
        ("check", "--output", "absent/report.json"),
    ],
    ids=[
        "version",
        "no-subcommand",
        "stdout",
        "file",
        "v0",
        "same-file",
        "unwritable",
    ],
)
def test_module_and_console_script_behave_identically(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    results: dict[str, tuple[Run, bytes | None]] = {}
    for entry in ("module", "script"):
        cwd = tmp_path / entry
        cwd.mkdir()
        minimal_project(cwd)
        result = spawn(entry, *argv, cwd=cwd)
        report = cwd / "report.json"
        results[entry] = (result, report.read_bytes() if report.exists() else None)
        assert_exit_contract(result)

    assert results["module"] == results["script"]


def test_module_entry_point_runs_golden_harness_invocation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config = minimal_project(project)
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    out = workdir / "out.json"

    result = spawn(
        "module", "check", "--config", str(config), "--output", str(out), cwd=workdir
    )

    assert result == Run(0, b"", b"")
    assert out.read_bytes() == expected_report(config.read_bytes())


# --- Determinism (acceptance criterion 3) ---------------------------------


def test_two_stdout_runs_are_byte_identical_and_match_empty_report(
    run: Callable[..., Run], tmp_path: Path
) -> None:
    config = minimal_project(tmp_path)

    first = run("check", "--config", "dogwatch.toml", "--output", "-")
    second = run("check", "--config", "dogwatch.toml", "--output", "-")

    assert first == second == Run(0, expected_report(config.read_bytes()), b"")
    report = json.loads(first.out)
    Draft202012Validator(json.loads(SCHEMA_PATH.read_bytes())).validate(report)
    assert report["findings"] == []


def test_stdout_report_is_independent_of_cwd_and_config_spelling(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config = minimal_project(project)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    from_project = spawn("module", "check", "--output", "-", cwd=project)
    from_elsewhere = spawn(
        "module", "check", "--config", str(config), "--output", "-", cwd=elsewhere
    )
    relative = spawn(
        "module",
        "check",
        "--config",
        "../project/./dogwatch.toml",
        "--output",
        "-",
        cwd=elsewhere,
    )

    assert from_project == from_elsewhere == relative
    assert from_project.out == expected_report(config.read_bytes())
    assert str(tmp_path).encode() not in from_project.out
    assert os.getcwd().encode() not in from_project.out


# --- AC-4 modes, stderr mirror and the scan seam (IC-CLI-1) ---------------

ERROR_FINDING = Finding(
    "python",
    "no-db",
    "error",
    "acme_shop.orders imports acme_shop.payments",
    "fp-1",
    Locator("src/acme_shop/orders.py", 1, 1, "acme_shop.orders", "acme_shop.payments"),
)
SYNTAX_DIAGNOSTIC = Diagnostic(
    "dogwatch", SOURCE_SYNTAX_INVALID, "error", "src/acme_shop/orders.py:1: bad"
)
ADAPTER_DIAGNOSTIC = Diagnostic("openapi", "openapi-tool-failed", "error", "exit 3")
PRE_SCAN_IDS = {"config-not-found", "config-invalid", "exclude-unmatched"}


class Mode(NamedTuple):
    report_present: bool
    status: str | None
    exit: int
    adapter_source: bool | None


def stub_scan(
    monkeypatch: pytest.MonkeyPatch,
    findings: Sequence[Finding] = (),
    diagnostics: Sequence[Diagnostic] = (),
) -> list[DogwatchConfig]:
    calls: list[DogwatchConfig] = []

    def fake(cfg: DogwatchConfig) -> tuple[tuple[Finding, ...], tuple[Diagnostic, ...]]:
        calls.append(cfg)
        return tuple(findings), tuple(diagnostics)

    monkeypatch.setattr(cli, "scan", fake)
    return calls


def validate_report(data: bytes) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(data)
    Draft202012Validator(json.loads(SCHEMA_PATH.read_bytes())).validate(report)
    return report


def observe(result: Run, target: Path) -> Mode:
    if not target.exists():
        return Mode(False, None, result.code, None)
    report = validate_report(target.read_bytes())
    diagnostics = report["diagnostics"]
    findings = [
        Finding(
            **{k: v for k, v in f.items() if k not in ("waiver", "locator")},
            locator=Locator(**f["locator"]),
        )
        for f in report["findings"]
    ]
    assert report["status"] == derive_status(
        findings, [Diagnostic(**d) for d in diagnostics]
    )
    assert result.code == {"pass": 0, "fail": 1, "inconclusive": 2}[report["status"]]
    assert not {d["id"] for d in diagnostics} & PRE_SCAN_IDS
    assert result.err.decode().splitlines() == [
        f"dogwatch:{d['id']}: {d['message']}" for d in diagnostics
    ]
    return Mode(
        True,
        report["status"],
        result.code,
        any(d["source"] != "dogwatch" for d in diagnostics),
    )


SCAN_MODES: dict[str, tuple[tuple[Finding, ...], tuple[Diagnostic, ...], Mode]] = {
    "policy-violation": ((ERROR_FINDING,), (), Mode(True, "fail", 1, False)),
    "invalid-source-syntax": (
        (),
        (SYNTAX_DIAGNOSTIC,),
        Mode(True, "inconclusive", 2, False),
    ),
    "adapter-failure": ((), (ADAPTER_DIAGNOSTIC,), Mode(True, "inconclusive", 2, True)),
}
MALFORMED_CONFIGS = {"missing": None, "invalid-toml": "[python\n"}


def _scan_mode(
    run: Callable[..., Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    findings: Sequence[Finding],
    diagnostics: Sequence[Diagnostic],
) -> Mode:
    minimal_project(tmp_path)
    calls = stub_scan(monkeypatch, findings, diagnostics)

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert len(calls) == 1
    assert result.out == b""
    return observe(result, tmp_path / "report.json")


def _malformed_mode(
    run: Callable[..., Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    toml_text: str | None,
) -> Mode:
    if toml_text is not None:
        (tmp_path / "dogwatch.toml").write_text(toml_text, encoding="utf-8")
    calls = stub_scan(monkeypatch, (ERROR_FINDING,))

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert calls == []
    assert result.out == b""
    assert re.fullmatch(
        rb"dogwatch:(config-not-found|config-invalid): .+\n", result.err
    )
    return observe(result, tmp_path / "report.json")


@pytest.mark.parametrize("mode", SCAN_MODES)
def test_scan_mode_report_status_and_exit(
    run: Callable[..., Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    findings, diagnostics, expected = SCAN_MODES[mode]

    assert _scan_mode(run, tmp_path, monkeypatch, findings, diagnostics) == expected


@pytest.mark.parametrize("case", MALFORMED_CONFIGS)
def test_malformed_config_writes_no_report_and_never_scans(
    run: Callable[..., Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    mode = _malformed_mode(run, tmp_path, monkeypatch, MALFORMED_CONFIGS[case])

    assert mode == Mode(False, None, 2, None)


def test_four_ac4_modes_are_pairwise_distinct(
    run: Callable[..., Run],
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: dict[str, Mode] = {}
    for name, (findings, diagnostics, _) in SCAN_MODES.items():
        root = tmp_path_factory.mktemp(name)
        monkeypatch.chdir(root)
        modes[name] = _scan_mode(run, root, monkeypatch, findings, diagnostics)
    root = tmp_path_factory.mktemp("malformed")
    monkeypatch.chdir(root)
    modes["malformed-config"] = _malformed_mode(run, root, monkeypatch, None)

    assert {k: m[:3] for k, m in modes.items()} == {
        "policy-violation": (True, "fail", 1),
        "invalid-source-syntax": (True, "inconclusive", 2),
        "adapter-failure": (True, "inconclusive", 2),
        "malformed-config": (False, None, 2),
    }
    for a, b in itertools.combinations(modes.values(), 2):
        assert a != b


def test_scan_time_diagnostics_are_rendered_in_report_order(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(tmp_path)
    stub_scan(
        monkeypatch,
        diagnostics=(
            Diagnostic("openapi", "openapi-tool-timeout", "warning", "slow — 日本"),
            ADAPTER_DIAGNOSTIC,
            Diagnostic("dogwatch", SOURCE_SYNTAX_INVALID, "info", "b.py: note"),
            SYNTAX_DIAGNOSTIC,
        ),
    )

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    report = validate_report((tmp_path / "report.json").read_bytes())
    assert result.code == 2
    assert result.err.decode().splitlines() == [
        f"dogwatch:{d['id']}: {d['message']}" for d in report["diagnostics"]
    ]
    assert result.err.decode().splitlines() == [
        "dogwatch:source-syntax-invalid: b.py: note",
        "dogwatch:source-syntax-invalid: src/acme_shop/orders.py:1: bad",
        "dogwatch:openapi-tool-failed: exit 3",
        "dogwatch:openapi-tool-timeout: slow — 日本",
    ]


def test_warning_and_info_only_pass_with_mirrored_stderr(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(tmp_path)
    warning = Finding("python", "no-db", "warning", "w", "fp-1", Locator("a.py"))
    info = Diagnostic("openapi", "openapi-note", "info", "fyi")
    stub_scan(monkeypatch, (warning,), (info,))

    result = run("check", "--config", "dogwatch.toml", "--output", "-")

    report = validate_report(result.out)
    assert (report["status"], result.code) == ("pass", 0)
    assert result.err == b"dogwatch:openapi-note: fyi\n"


def test_stdout_mode_writes_report_to_stdout_and_diagnostics_to_stderr(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(tmp_path)
    stub_scan(monkeypatch, (ERROR_FINDING,), (ADAPTER_DIAGNOSTIC,))

    result = run("check", "--config", "dogwatch.toml", "--output", "-")

    assert validate_report(result.out)["status"] == "inconclusive"
    assert result.code == 2
    assert result.err == b"dogwatch:openapi-tool-failed: exit 3\n"


def test_no_scan_diagnostics_means_empty_stderr(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    minimal_project(tmp_path)
    stub_scan(monkeypatch, (ERROR_FINDING,))

    result = run("check", "--config", "dogwatch.toml", "--output", "report.json")

    assert (result.code, result.err) == (1, b"")
    assert validate_report((tmp_path / "report.json").read_bytes())["diagnostics"] == []


@pytest.mark.parametrize("failure", ["missing-dir", "no-space"])
def test_write_failure_suppresses_scan_diagnostics(
    run: Callable[..., Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    minimal_project(tmp_path)
    stub_scan(monkeypatch, (ERROR_FINDING,), (SYNTAX_DIAGNOSTIC, ADAPTER_DIAGNOSTIC))
    output = "nope/report.json" if failure == "missing-dir" else "report.json"
    if failure == "no-space":

        def no_space(fd: int) -> None:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

        monkeypatch.setattr(os, "fsync", no_space)

    result = run("check", "--config", "dogwatch.toml", "--output", output)

    lines = result.err.decode().splitlines()
    assert result.code == 2
    assert len(lines) == 1
    assert lines[-1].startswith(f"dogwatch: error: cannot write report to {output}: ")
    assert not (tmp_path / output).exists()
    assert list(tmp_path.rglob(".*.tmp")) == []


def test_same_file_guard_never_scans(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = minimal_project(tmp_path)
    raw = config.read_bytes()
    calls = stub_scan(monkeypatch, (ERROR_FINDING,))

    result = run("check", "--config", "dogwatch.toml", "--output", "dogwatch.toml")

    assert result.code == 2
    assert result.err.startswith(b"dogwatch: error: output path ")
    assert calls == []
    assert config.read_bytes() == raw


def test_scan_receives_the_validated_config(
    run: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = minimal_project(tmp_path)
    calls = stub_scan(monkeypatch)

    assert run("check", "--output", "-").code == 0
    assert calls == [load_policy("./dogwatch.toml")]
    assert calls[0].raw == config.read_bytes()


def test_scan_seam_signature_and_default_result(tmp_path: Path) -> None:
    minimal_project(tmp_path)
    cfg = load_policy("dogwatch.toml")

    assert cli.scan.__module__ == "dogwatch.cli"
    assert list(inspect.signature(cli.scan).parameters) == ["cfg"]
    assert cli.scan(cfg) == ((), ())
