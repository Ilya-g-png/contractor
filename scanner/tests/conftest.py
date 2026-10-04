from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import pytest


class MakeConfig(Protocol):
    def __call__(self, toml_text: str, dirs: Iterable[str] = ()) -> Path: ...


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def make_config(tmp_path: Path) -> MakeConfig:
    def _make(toml_text: str, dirs: Iterable[str] = ()) -> Path:
        for d in dirs:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        config = tmp_path / "dogwatch.toml"
        config.write_bytes(toml_text.encode("utf-8"))
        return config

    return _make
