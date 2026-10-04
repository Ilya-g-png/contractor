import resource
import subprocess
import sys
from pathlib import Path

from tests.test_cli import minimal_project

PEAK_RSS_LIMIT_BYTES = 200 * 10**6


def _peak_children_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def test_check_peak_rss_within_budget(tmp_path: Path) -> None:
    config = minimal_project(tmp_path)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "dogwatch",
            "check",
            "--config",
            str(config),
            "--output",
            str(tmp_path / "report.json"),
        ],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    assert (proc.returncode, proc.stderr) == (0, b"")
    peak = _peak_children_rss_bytes()
    assert 0 < peak <= PEAK_RSS_LIMIT_BYTES
