from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

HOST_VAR: Final = "DOGWATCH_API_HOST"
PORT_VAR: Final = "DOGWATCH_API_PORT"

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8000


@dataclass(frozen=True)
class Settings:
    host: str
    port: int


class SettingsError(Exception):
    pass


def load_settings(environ: Mapping[str, str]) -> Settings:
    return Settings(host=_host(environ), port=_port(environ))


def _host(environ: Mapping[str, str]) -> str:
    host = environ.get(HOST_VAR, DEFAULT_HOST)
    if not host:
        raise SettingsError(f"dogwatch-api: error: cannot bind {HOST_VAR}={host}")
    return host


def _port(environ: Mapping[str, str]) -> int:
    raw = environ.get(PORT_VAR)
    if raw is None:
        return DEFAULT_PORT
    if raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 65535:
        return int(raw)
    raise SettingsError(
        f"dogwatch-api: error: {PORT_VAR} must be an integer between 1 and 65535"
    )
