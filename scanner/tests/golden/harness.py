import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_NAME = "expected-report.json"
STRIPPED_VARS = ("TZ", "LANG", "PYTHONHASHSEED", "HOME")

# IC-7 variant table: (TZ, LC_ALL = LANG). An unavailable locale falls back
# silently at the libc level, which is fine because output must not depend on it.
VARIANTS = (
    ("UTC", "C"),
    ("America/Los_Angeles", "C.UTF-8"),
    ("Asia/Kolkata", "en_US.UTF-8"),
    ("Pacific/Chatham", "tr_TR.UTF-8"),
    ("Etc/GMT+12", "POSIX"),
)


class ScanResult(NamedTuple):
    returncode: int
    stderr: bytes
    output: bytes
    cwd: str
    home: str


def discover_configs() -> list[Path]:
    return sorted(REPO_ROOT.glob("fixtures/*/dogwatch.toml"))


def golden_path(config: Path) -> Path:
    return config.with_name(GOLDEN_NAME)


def variant_env(k: int, home: str) -> dict[str, str]:
    tz, locale = VARIANTS[k]
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in STRIPPED_VARS and not name.startswith("LC_")
    }
    env.update(
        TZ=tz,
        LC_ALL=locale,
        LANG=locale,
        HOME=home,
        PYTHONHASHSEED=str(random.SystemRandom().randint(1, 4294967295)),
    )
    return env


def run_scanner(config: Path, k: int) -> ScanResult:
    with tempfile.TemporaryDirectory(prefix="dogwatch-golden-") as tmp:
        cwd = os.path.join(tmp, "cwd")
        home = os.path.join(tmp, "home")
        os.mkdir(cwd)
        os.mkdir(home)
        out = os.path.join(tmp, "out.json")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "dogwatch",
                "check",
                "--config",
                str(config.resolve()),
                "--output",
                out,
            ],
            cwd=cwd,
            env=variant_env(k, home),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        output = Path(out).read_bytes() if os.path.exists(out) else b""
        return ScanResult(proc.returncode, proc.stderr, output, cwd, home)
