import ast
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dogwatch_api import problems
from dogwatch_api.app import create_app

EXCEPTION_MESSAGE = "secret exception message"
ECHOED_INPUT = "leaked-input-value"


def _app_with_test_routes() -> FastAPI:
    app = create_app()

    @app.get("/test-only/validate")
    async def validate(n: int) -> dict[str, int]:
        return {"n": n}

    @app.get("/test-only/raise")
    async def raise_error() -> None:
        raise RuntimeError(EXCEPTION_MESSAGE)

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app_with_test_routes())


def _assert_problem(response: httpx.Response, code: str, status: int) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == {"type", "title", "status", "detail", "code"}
    assert body["status"] == response.status_code
    assert body["code"] == code
    assert body["type"] == "urn:dogwatch:problem:" + body["code"]


def test_unknown_path_is_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/nope?token=secret")

    _assert_problem(response, "not-found", 404)
    assert response.json()["title"] == "Not Found"
    assert response.json()["detail"] == "No route matches /api/v1/nope"
    assert "secret" not in response.text


def test_any_method_on_unknown_path_is_not_found(client: TestClient) -> None:
    _assert_problem(client.delete("/nope"), "not-found", 404)


def test_wrong_method_on_health_is_method_not_allowed(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    _assert_problem(response, "method-not-allowed", 405)
    assert response.headers["allow"] == "GET"
    assert response.json()["title"] == "Method Not Allowed"
    assert response.json()["detail"] == "Method POST is not allowed; allowed: GET"


def test_wrong_method_on_openapi_is_method_not_allowed(client: TestClient) -> None:
    response = client.put("/api/v1/openapi.json")

    _assert_problem(response, "method-not-allowed", 405)
    assert "GET" in response.headers["allow"].split(", ")


def test_validation_error_does_not_echo_input(client: TestClient) -> None:
    response = client.get("/test-only/validate", params={"n": ECHOED_INPUT})

    _assert_problem(response, "validation-failed", 422)
    assert response.json()["title"] == "Validation Failed"
    assert response.json()["detail"] == "Request validation failed (1 errors)"
    assert ECHOED_INPUT not in response.text


def test_unhandled_exception_is_internal_error(client: TestClient) -> None:
    response = client.get("/test-only/raise")

    _assert_problem(response, "internal-error", 500)
    assert response.json()["title"] == "Internal Server Error"
    assert response.json()["detail"] == "Internal server error."
    assert EXCEPTION_MESSAGE not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    ("constant", "code", "status"),
    [
        (problems.SCHEMA_INVALID, "schema-invalid", 400),
        (problems.IN_FLIGHT, "in-flight", 409),
        (problems.PAYLOAD_TOO_LARGE, "payload-too-large", 413),
        (problems.IDEMPOTENCY_CONFLICT, "idempotency-conflict", 422),
        (problems.RATE_LIMITED, "rate-limited", 429),
    ],
)
def test_reserved_codes_exist(
    constant: problems.ProblemCode, code: str, status: int
) -> None:
    assert constant == problems.ProblemCode(code, status)


def test_reserved_codes_are_not_used_outside_problems() -> None:
    reserved = {
        "SCHEMA_INVALID",
        "IN_FLIGHT",
        "PAYLOAD_TOO_LARGE",
        "IDEMPOTENCY_CONFLICT",
        "RATE_LIMITED",
    }
    package = Path(problems.__file__).parent
    used: set[str] = set()
    for path in package.glob("*.py"):
        if path.name == "problems.py":
            continue
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.alias):
                used.add(node.name)

    assert used & reserved == set()
