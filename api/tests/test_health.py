import importlib.metadata

import pytest
from fastapi.testclient import TestClient

from dogwatch_api.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_health_status(client: TestClient) -> None:
    version = importlib.metadata.version("dogwatch-api")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.content == (
        b'{"status":"ok","service":"dogwatch-api","version":"%s"}' % version.encode()
    )
    assert version == "0.1.0"


def test_health_ignores_query_parameters(client: TestClient) -> None:
    response = client.get("/api/v1/health", params={"verbose": "1"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "dogwatch-api",
        "version": "0.1.0",
    }


def test_health_sets_no_cookie(client: TestClient) -> None:
    assert "set-cookie" not in client.get("/api/v1/health").headers


@pytest.mark.parametrize(
    "path", ["/api/v1/health/", "/api/v1/openapi.json/", "/docs", "/redoc"]
)
def test_unlisted_paths_are_not_found_without_redirect(
    client: TestClient, path: str
) -> None:
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers
    assert response.json()["code"] == "not-found"
