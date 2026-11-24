import json
import os
import re
import selectors
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from dogwatch.diagnostics import Diagnostic

TIMEOUT_SECONDS = 60
STDOUT_LIMIT = 16 * 1024 * 1024
STDERR_LIMIT = 1024 * 1024
_FINGERPRINT = re.compile(r"[0-9a-f]{12}\Z")


@dataclass(frozen=True)
class RunnerResult:
    records: tuple[dict[str, object], ...] | None
    diagnostics: tuple[Diagnostic, ...]


def run_oasdiff(
    executable: Path, base_json: bytes, candidate_json: bytes
) -> RunnerResult:
    try:
        with tempfile.TemporaryDirectory(prefix="dogwatch-oasdiff-") as directory:
            private_dir = Path(directory)
            base_path = private_dir / "base.json"
            candidate_path = private_dir / "candidate.json"
            for path, content in (
                (base_path, base_json),
                (candidate_path, candidate_json),
            ):
                path.write_bytes(content)
                path.chmod(0o400)
            argv = [
                str(executable),
                "changelog",
                "--format=json",
                "--level=INFO",
                "--allow-external-refs=false",
                "--",
                str(base_path),
                str(candidate_path),
            ]
            environment = {
                "HOME": directory,
                "TMPDIR": directory,
                "PATH": os.defpath,
            }
            output, stderr, returncode, failure = collect_process(
                argv,
                private_dir,
                environment,
                TIMEOUT_SECONDS,
                STDOUT_LIMIT,
                STDERR_LIMIT,
            )
    except OSError as error:
        return _failure(
            "openapi-tool-failed", f"could not prepare tool inputs: {error}"
        )

    if failure is not None:
        return _failure(failure, _failure_message(failure))
    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[:512]
        message = f"oasdiff exited with status {returncode}"
        if detail:
            message += f": {detail}"
        return _failure("openapi-tool-failed", message)
    try:
        decoded = json.loads(output) if output.strip() else []
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _failure("openapi-tool-failed", "oasdiff returned malformed JSON")
    if decoded is None:
        decoded = []
    if not isinstance(decoded, list) or not all(
        isinstance(record, dict)
        and isinstance(record.get("id"), str)
        and bool(record["id"])
        and isinstance(record.get("text"), str)
        and bool(record["text"])
        and type(record.get("level")) is int
        and record["level"] in {1, 2, 3}
        and isinstance(record.get("fingerprint"), str)
        and _FINGERPRINT.fullmatch(record["fingerprint"]) is not None
        and all(
            field not in record or isinstance(record[field], str)
            for field in ("operation", "path", "section")
        )
        for record in decoded
    ):
        return _failure(
            "openapi-tool-failed", "oasdiff returned a malformed change record"
        )
    return RunnerResult(tuple(decoded), ())


def collect_process(
    argv: list[str],
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[bytes, bytes, int | None, str | None]:
    deadline = time.monotonic() + timeout_seconds
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return b"", b"", None, "openapi-tool-failed"

    stdout = bytearray()
    stderr = bytearray()
    failure: str | None = None
    try:
        with selectors.DefaultSelector() as selector:
            assert process.stdout is not None
            assert process.stderr is not None
            selector.register(
                process.stdout, selectors.EVENT_READ, (stdout, stdout_limit)
            )
            selector.register(
                process.stderr, selectors.EVENT_READ, (stderr, stderr_limit)
            )
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failure = "openapi-tool-timeout"
                    break
                for key, _ in selector.select(remaining):
                    buffer, limit = key.data
                    chunk = os.read(key.fd, min(65536, limit - len(buffer) + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffer.extend(chunk)
                    if len(buffer) > limit:
                        failure = (
                            "openapi-tool-stdout-limit-exceeded"
                            if buffer is stdout
                            else "openapi-tool-stderr-limit-exceeded"
                        )
                        break
                if failure is not None:
                    break
        if failure is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "openapi-tool-timeout"
            else:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    failure = "openapi-tool-timeout"
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    return bytes(stdout), bytes(stderr), process.returncode, failure


def _failure_message(diagnostic_id: str) -> str:
    return {
        "openapi-tool-timeout": "oasdiff exceeded the 60-second time limit",
        "openapi-tool-stdout-limit-exceeded": (
            "oasdiff exceeded the 16 MiB stdout limit"
        ),
        "openapi-tool-stderr-limit-exceeded": "oasdiff exceeded the 1 MiB stderr limit",
        "openapi-tool-failed": "could not start oasdiff",
    }[diagnostic_id]


def _failure(diagnostic_id: str, message: str) -> RunnerResult:
    return RunnerResult(None, (Diagnostic("openapi", diagnostic_id, "error", message),))
