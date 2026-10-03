import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from dogwatch_api.app import create_app


@pytest.fixture
def openapi() -> dict[str, Any]:
    response = TestClient(create_app()).get("/api/v1/openapi.json")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    document: dict[str, Any] = response.json()
    return document


def test_openapi_version_is_3_1(openapi: dict[str, Any]) -> None:
    assert openapi["openapi"].startswith("3.1")
    assert re.fullmatch(r"3\.1\.\d+", openapi["openapi"])


def test_openapi_info(openapi: dict[str, Any]) -> None:
    assert openapi["info"]["title"] == "dogwatch-api"
    assert openapi["info"]["version"] == "0.1.0"


def test_openapi_paths_are_health_only(openapi: dict[str, Any]) -> None:
    assert set(openapi["paths"]) == {"/api/v1/health"}
    assert set(openapi["paths"]["/api/v1/health"]) == {"get"}


def test_openapi_health_status_component(openapi: dict[str, Any]) -> None:
    schema = openapi["components"]["schemas"]["HealthStatus"]

    assert set(schema["properties"]) == {"status", "service", "version"}
    assert schema["properties"]["status"]["const"] == "ok"
    assert sorted(schema["required"]) == ["service", "status", "version"]


def test_openapi_is_deterministic() -> None:
    first = TestClient(create_app()).get("/api/v1/openapi.json").content
    second = TestClient(create_app()).get("/api/v1/openapi.json").content

    assert first == second


def test_product_app_exposes_only_health_and_openapi() -> None:
    routes = create_app().routes

    assert all(isinstance(route, Route) for route in routes)
    assert {route.path for route in routes if isinstance(route, Route)} == {
        "/api/v1/health",
        "/api/v1/openapi.json",
    }
