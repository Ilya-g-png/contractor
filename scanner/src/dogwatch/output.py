import contextlib
import os
import sys
import tempfile

STDOUT = "-"


def write_report(data: bytes, output_arg: str) -> None:
    if output_arg == STDOUT:
        _write_stdout(data)
    else:
        _write_atomic(data, output_arg)


def _write_stdout(data: bytes) -> None:
    stream = sys.stdout.buffer
    try:
        stream.write(data)
        stream.flush()
    except BrokenPipeError:
        # Keep the interpreter's exit-time flush from reporting the same error.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, stream.fileno())
        os.close(devnull)
        raise


def _write_atomic(data: bytes, target: str) -> None:
    directory = os.path.dirname(target) or os.curdir
    fd, temp = tempfile.mkstemp(
        prefix=f".{os.path.basename(target)}.", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o666 & ~_umask())
        os.replace(temp, target)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask
