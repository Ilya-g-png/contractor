import difflib
import getpass
import hashlib
import json
import os
import shutil
import socket
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from dogwatch import __version__
from tests.golden.harness import (
    GOLDEN_NAME,
    REPO_ROOT,
    VARIANTS,
    discover_configs,
    golden_path,
    run_scanner,
)

SCHEMA_PATH = REPO_ROOT / "scanner" / "schemas" / "report-0.1.schema.json"
CONFIGS = discover_configs()


def _fixture_id(config: Path) -> str:
    return config.parent.name


def _unified_diff(expected: bytes, actual: bytes) -> str:
    return "".join(
        difflib.unified_diff(
            expected.decode("utf-8", "replace").splitlines(keepends=True),
            actual.decode("utf-8", "replace").splitlines(keepends=True),
            GOLDEN_NAME,
            "actual",
        )
    )


@pytest.mark.golden
def test_fixtures_are_discovered() -> None:
    assert CONFIGS, f"no fixtures/*/dogwatch.toml under {REPO_ROOT}"


@pytest.mark.golden
def test_dogwatch_entry_point_resolves_in_active_environment() -> None:
    found = shutil.which("dogwatch")

    assert found is not None
    assert Path(found).parent == Path(sys.executable).parent


@pytest.mark.golden
@pytest.mark.parametrize("k", range(len(VARIANTS)), ids=lambda k: f"variant{k}")
@pytest.mark.parametrize("config", CONFIGS, ids=_fixture_id)
def test_output_matches_golden(config: Path, k: int) -> None:
    golden = golden_path(config)
    stat_before = golden.stat()
    expected = golden.read_bytes()

    result = run_scanner(config, k)

    if result.returncode != 0:
        pytest.fail(
            f"dogwatch exited {result.returncode}; stderr:\n"
            + result.stderr.decode("utf-8", "replace"),
            pytrace=False,
        )
    assert result.stderr == b""
    if result.output != expected:
        pytest.fail(_unified_diff(expected, result.output), pytrace=False)
    for location in {result.cwd, os.path.realpath(result.cwd)}:
        assert location.encode() not in result.output
    for location in {result.home, os.path.realpath(result.home)}:
        assert location.encode() not in result.output
    stat_after = golden.stat()
    assert golden.read_bytes() == expected
    assert stat_after.st_mtime_ns == stat_before.st_mtime_ns


@pytest.mark.golden
@pytest.mark.parametrize("config", CONFIGS, ids=_fixture_id)
def test_repeated_runs_are_identical(config: Path) -> None:
    first = run_scanner(config, 0)
    second = run_scanner(config, 0)

    assert first.returncode == second.returncode == 0
    assert first.output == second.output


@pytest.mark.golden
@pytest.mark.parametrize("config", CONFIGS, ids=_fixture_id)
def test_golden_satisfies_report_contract(config: Path) -> None:
    golden_bytes = golden_path(config).read_bytes()
    report: dict[str, Any] = json.loads(golden_bytes)
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_bytes())

    Draft202012Validator(schema).validate(report)
    assert report["findings"] == []
    assert report["scanner"]["version"] == __version__
    assert report["policy"]["path"] == "dogwatch.toml"
    assert (
        report["policy"]["digest"]["sha256"]
        == hashlib.sha256(config.read_bytes()).hexdigest()
    )
    for leak in (
        os.getcwd(),
        os.path.expanduser("~"),
        socket.gethostname(),
        getpass.getuser(),
    ):
        assert leak.encode() not in golden_bytes
