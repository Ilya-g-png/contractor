# Controlled stand-in for oasdiff, launched by the fixture-matrix harness.
# argv: STATE_DIR followed by the exact argv the runner passed to "oasdiff".
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any


def main() -> int:
    state = Path(sys.argv[1])
    behavior: dict[str, Any] = json.loads((state / "behavior.json").read_bytes())
    inputs: dict[str, dict[str, object]] = {}
    for side, value in zip(("base", "candidate"), sys.argv[-2:], strict=True):
        path = Path(value)
        content = path.read_bytes()
        inputs[side] = {
            "mode": stat.S_IMODE(path.stat().st_mode),
            "sha256": hashlib.sha256(content).hexdigest(),
            "content": content.decode("utf-8"),
        }
    observation = {
        "cwd": os.getcwd(),
        "directory_mode": stat.S_IMODE(os.stat(".").st_mode),
        "stdin_bytes": len(os.read(0, 1)),
        "inputs": inputs,
    }
    (state / "observation.json").write_text(json.dumps(observation), "utf-8")

    time.sleep(behavior.get("sleep_seconds", 0))
    stderr = behavior.get("stderr", "") + "x" * behavior.get("stderr_bytes", 0)
    sys.stderr.buffer.write(stderr.encode("utf-8"))
    sys.stderr.flush()
    stdout = (
        json.dumps(behavior["records"])
        if "records" in behavior
        else behavior.get("stdout", "")
    ) + "x" * behavior.get("stdout_bytes", 0)
    sys.stdout.buffer.write(stdout.encode("utf-8"))
    sys.stdout.flush()
    return int(behavior.get("exit_status", 0))


if __name__ == "__main__":
    sys.exit(main())
