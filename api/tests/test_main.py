import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from dogwatch_api import __main__ as entrypoint
from dogwatch_api import __version__

PORT_MESSAGE = (
    "dogwatch-api: error: DOGWATCH_API_PORT must be an integer between 1 and 65535\n"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


def _run_module(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dogwatch_api"],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )


class _ServerRecorder:
    def __init__(self) -> None:
        self.config: uvicorn.Config | None = None
        self.sockets: list[socket.socket] = []

    def __call__(self, config: uvicorn.Config) -> _ServerRecorder:
        self.config = config
        return self

    def run(self, sockets: list[socket.socket] | None = None) -> None:
        self.sockets = sockets or []


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Iterator[_ServerRecorder]:
    handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    recorder = _ServerRecorder()
    monkeypatch.setattr(uvicorn, "Server", recorder)
    yield recorder
    for sock in recorder.sockets:
        sock.close()
    for signum, handler in handlers.items():
        signal.signal(signum, handler)


@pytest.mark.parametrize("port", ["0", "abc"])
def test_invalid_port_exits_1(
    port: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    recorder: _ServerRecorder,
) -> None:
    monkeypatch.setenv("DOGWATCH_API_PORT", port)

    assert entrypoint.main() == 1
    assert capsys.readouterr().err == PORT_MESSAGE
    assert recorder.config is None


def test_empty_host_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    recorder: _ServerRecorder,
) -> None:
    monkeypatch.setenv("DOGWATCH_API_HOST", "")

    assert entrypoint.main() == 1
    assert capsys.readouterr().err == (
        "dogwatch-api: error: cannot bind DOGWATCH_API_HOST=\n"
    )
    assert recorder.config is None


def test_unresolvable_host_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    recorder: _ServerRecorder,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise socket.gaierror(socket.EAI_NONAME, "unknown host")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    monkeypatch.setenv("DOGWATCH_API_HOST", "nowhere.invalid")

    assert entrypoint.main() == 1
    assert capsys.readouterr().err == (
        "dogwatch-api: error: cannot bind DOGWATCH_API_HOST=nowhere.invalid\n"
    )
    assert recorder.config is None


def test_runs_single_worker_server_on_its_own_socket(
    monkeypatch: pytest.MonkeyPatch, recorder: _ServerRecorder
) -> None:
    port = _free_port()
    monkeypatch.setenv("DOGWATCH_API_PORT", str(port))

    assert entrypoint.main() == 0

    assert recorder.config is not None
    assert isinstance(recorder.config.app, FastAPI)
    assert recorder.config.access_log is False
    assert recorder.config.workers == 1
    assert len(recorder.sockets) == 1
    assert recorder.sockets[0].getsockname() == ("127.0.0.1", port)


def test_port_in_use_exits_1_without_retry() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]

        result = _run_module({"DOGWATCH_API_PORT": str(port)})

    assert result.returncode == 1
    assert result.stderr == (
        f"dogwatch-api: error: 127.0.0.1:{port} is already in use; "
        "set DOGWATCH_API_PORT to choose another port\n"
    )
    assert result.stdout == ""


def test_unavailable_host_address_exits_1() -> None:
    result = _run_module(
        {"DOGWATCH_API_HOST": "192.0.2.1", "DOGWATCH_API_PORT": str(_free_port())}
    )

    assert result.returncode == 1
    assert result.stderr == (
        "dogwatch-api: error: cannot bind DOGWATCH_API_HOST=192.0.2.1\n"
    )


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_module_serves_health_and_exits_0_on_signal(signum: signal.Signals) -> None:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "dogwatch_api"],
        env={**os.environ, "DOGWATCH_API_PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        response = _wait_for_health(f"http://127.0.0.1:{port}/api/v1/health")
        process.send_signal(signum)
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "dogwatch-api",
        "version": __version__,
    }


def _wait_for_health(url: str) -> httpx.Response:
    deadline = time.monotonic() + 15
    while True:
        try:
            return httpx.get(url, timeout=1)
        except httpx.TransportError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)
