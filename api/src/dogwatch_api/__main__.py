import errno
import os
import signal
import socket
import sys
from types import FrameType

import uvicorn

from dogwatch_api.app import create_app
from dogwatch_api.settings import (
    HOST_VAR,
    PORT_VAR,
    Settings,
    SettingsError,
    load_settings,
)


def main() -> int:
    try:
        settings = load_settings(os.environ)
        sock = _bind(settings)
    except SettingsError as exc:
        print(exc, file=sys.stderr)
        return 1
    # uvicorn re-raises the shutdown signal after a graceful exit; IC-4 wants 0.
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _exit_cleanly)
    config = uvicorn.Config(create_app(), access_log=False, workers=1)
    uvicorn.Server(config).run(sockets=[sock])
    return 0


def _bind(settings: Settings) -> socket.socket:
    host_error = f"dogwatch-api: error: cannot bind {HOST_VAR}={settings.host}"
    try:
        family, kind, proto, _, address = socket.getaddrinfo(
            settings.host, settings.port, type=socket.SOCK_STREAM
        )[0]
    except socket.gaierror:
        raise SettingsError(host_error) from None
    sock = socket.socket(family, kind, proto)
    try:
        if os.name == "posix":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
    except OSError as exc:
        sock.close()
        if exc.errno == errno.EADDRINUSE:
            raise SettingsError(
                f"dogwatch-api: error: {settings.host}:{settings.port} is already "
                f"in use; set {PORT_VAR} to choose another port"
            ) from None
        if exc.errno == errno.EADDRNOTAVAIL:
            raise SettingsError(host_error) from None
        raise
    return sock


def _exit_cleanly(signum: int, frame: FrameType | None) -> None:
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())
