import os
import subprocess
from pathlib import Path

from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Diagnostic
from dogwatch.openapi.model import (
    BaselineReference,
    BaselineResolution,
    PreflightResult,
)
from dogwatch.openapi.preflight import (
    MAX_RAW_BYTES,
    input_diagnostic,
    preflight_bytes,
    valid_contract_path,
)


def resolve_baseline_ref(
    repository_root: Path, supplied_ref: str
) -> BaselineResolution:
    repository = _git(repository_root, "rev-parse", "--is-inside-work-tree")
    if repository is None or repository.returncode != 0:
        return _git_failure("could not inspect local Git repository")
    completed = _git(
        repository_root,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{supplied_ref}^{{commit}}",
    )
    if completed is None:
        return _git_failure("could not start local Git while resolving baseline ref")
    if completed.returncode != 0:
        return BaselineResolution(
            None,
            (
                Diagnostic(
                    "openapi",
                    "openapi-baseline-ref-unavailable",
                    "error",
                    f"baseline ref {supplied_ref!r} is unavailable locally",
                ),
            ),
        )
    try:
        commit = completed.stdout.decode("ascii", "strict").strip()
    except UnicodeDecodeError:
        return _git_failure("Git returned an invalid baseline commit")
    if not _is_object_id(commit):
        return _git_failure("Git returned an invalid baseline commit")
    return BaselineResolution(BaselineReference(supplied_ref, commit), ())


def read_baseline(
    repository_root: Path, baseline: BaselineReference, declaration: OpenApiContractDecl
) -> PreflightResult:
    if not valid_contract_path(declaration.path):
        return _baseline_invalid(declaration.path, "invalid relative contract path")
    entry = _git(
        repository_root,
        "ls-tree",
        "-z",
        baseline.resolved_commit,
        "--",
        f":(literal){declaration.path}",
    )
    if entry is None or entry.returncode != 0:
        return _preflight_git_failure(
            declaration.path, "could not inspect baseline tree"
        )
    try:
        parsed = _tree_entry(entry.stdout, declaration.path)
    except ValueError:
        return _preflight_git_failure(
            declaration.path, "Git returned an invalid tree entry"
        )
    if parsed is None:
        return _baseline_invalid(declaration.path, "baseline contract path is missing")
    mode, object_type, object_id = parsed
    if (
        mode not in {"100644", "100755"}
        or object_type != "blob"
        or not _is_object_id(object_id)
    ):
        return _baseline_invalid(
            declaration.path, "baseline contract path is not a regular file"
        )

    size_result = _git(repository_root, "cat-file", "-s", object_id)
    if size_result is None or size_result.returncode != 0:
        return _preflight_git_failure(
            declaration.path, "could not inspect baseline blob"
        )
    try:
        size = int(size_result.stdout.decode("ascii", "strict").strip())
    except (UnicodeDecodeError, ValueError):
        return _preflight_git_failure(
            declaration.path, "Git returned an invalid baseline blob size"
        )
    if size < 0:
        return _preflight_git_failure(
            declaration.path, "Git returned an invalid baseline blob size"
        )
    if size > MAX_RAW_BYTES:
        return input_diagnostic(
            "base", declaration.path, "contract exceeds the 5 MiB raw-byte limit"
        )

    blob = _git(repository_root, "cat-file", "blob", object_id)
    if blob is None or blob.returncode != 0 or len(blob.stdout) != size:
        return _preflight_git_failure(declaration.path, "could not read baseline blob")
    return preflight_bytes("base", declaration, blob.stdout)


def _git(
    repository_root: Path, *arguments: str
) -> subprocess.CompletedProcess[bytes] | None:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        return subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "--no-replace-objects",
                *arguments,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=environment,
        )
    except OSError:
        return None


def _tree_entry(output: bytes, path: str) -> tuple[str, str, str] | None:
    records = [record for record in output.split(b"\0") if record]
    if not records:
        return None
    if len(records) != 1:
        raise ValueError("multiple tree entries")
    try:
        metadata, entry_path = records[0].split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii", "strict").split(" ")
        if entry_path.decode("utf-8", "strict") != path:
            raise ValueError("unexpected tree path")
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("malformed tree entry") from error
    return mode, object_type, object_id


def _is_object_id(value: str) -> bool:
    return len(value) in {40, 64} and all(char in "0123456789abcdef" for char in value)


def _baseline_invalid(path: str, message: str) -> PreflightResult:
    return PreflightResult(
        None,
        (
            Diagnostic(
                "openapi",
                "openapi-baseline-invalid",
                "error",
                f"base {path}: {message}",
            ),
        ),
    )


def _preflight_git_failure(path: str, message: str) -> PreflightResult:
    return PreflightResult(
        None,
        (
            Diagnostic(
                "openapi", "openapi-git-failed", "error", f"base {path}: {message}"
            ),
        ),
    )


def _git_failure(message: str) -> BaselineResolution:
    return BaselineResolution(
        None,
        (Diagnostic("openapi", "openapi-git-failed", "error", message),),
    )
