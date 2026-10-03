from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_api_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOGWATCH_API_HOST", raising=False)
    monkeypatch.delenv("DOGWATCH_API_PORT", raising=False)


@pytest.fixture
def api_root() -> Path:
    return Path(__file__).resolve().parents[1]
