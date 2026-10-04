import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from dogwatch_api.app import create_app
from dogwatch_api.middleware import RequestContext

UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
BASE_FIELDS = {
    "ts",
    "level",
    "event",
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
}
ERROR_FIELDS = {"error_type", "error_traceback"}


def _app_with_test_routes() -> FastAPI:
    app = create_app()

    @app.get("/test-only/validate")
    async def validate(n: int) -> dict[str, int]:
        return {"n": n}

    @app.get("/test-only/raise")
    async def raise_error() -> None:
        raise RuntimeError("boom")

    @app.get("/test-only/raise-after-start")
    async def raise_after_start() -> StreamingResponse:
        def chunks() -> Iterator[bytes]:
            yield b"partial"
            raise RuntimeError("late boom")

        return StreamingResponse(chunks())

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app_with_test_routes())


def _log_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().out.splitlines()


def _single_log(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    lines = _log_lines(capsys)
    assert len(lines) == 1, lines
    record: dict[str, Any] = json.loads(lines[0])
    assert lines[0] == json.dumps(record, separators=(",", ":"))
    return record


@pytest.mark.parametrize(
    ("method", "path", "status", "route"),
    [
        ("GET", "/api/v1/health", 200, "/api/v1/health"),
        ("GET", "/api/v1/openapi.json", 200, "/api/v1/openapi.json"),
        ("GET", "/api/v1/nope", 404, None),
        ("GET", "/api/v1/health/", 404, None),
        ("POST", "/api/v1/health", 405, "/api/v1/health"),
        ("GET", "/test-only/validate?n=x", 422, "/test-only/validate"),
        ("GET", "/test-only/raise", 500, "/test-only/raise"),
    ],
)
def test_one_log_line_per_request(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
    method: str,
    path: str,
    status: int,
    route: str | None,
) -> None:
    capsys.readouterr()

    response = client.request(method, path)
    record = _single_log(capsys)

    assert response.status_code == status
    assert record["request_id"] == response.headers["x-request-id"]
    assert UUID4.fullmatch(record["request_id"])
    assert record["event"] == "request"
    assert record["method"] == method
    assert record["route"] == route
    assert record["status"] == status
    assert TIMESTAMP.fullmatch(record["ts"])
    assert isinstance(record["duration_ms"], float | int)
    assert record["duration_ms"] >= 0
    if status >= 500:
        assert record["level"] == "error"
        assert set(record) == BASE_FIELDS | ERROR_FIELDS
    else:
        assert record["level"] == "info"
        assert set(record) == BASE_FIELDS


def test_internal_error_log_line_carries_traceback(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    client.get("/test-only/raise")
    record = _single_log(capsys)

    assert record["level"] == "error"
    assert record["error_type"] == "builtins.RuntimeError"
    assert record["error_traceback"]
    assert "Traceback" in record["error_traceback"]
    assert "RuntimeError: boom" in record["error_traceback"]


def test_exception_after_response_start_is_logged_with_sent_status(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    with pytest.raises(RuntimeError, match="late boom"):
        client.get("/test-only/raise-after-start")
    record = _single_log(capsys)

    assert record["level"] == "error"
    assert record["status"] == 200
    assert record["route"] == "/test-only/raise-after-start"
    assert "late boom" in record["error_traceback"]


def test_valid_request_id_is_echoed(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    request_id = "a" * 128

    response = client.get("/api/v1/health", headers={"X-Request-ID": request_id})

    assert response.headers["x-request-id"] == request_id
    assert _single_log(capsys)["request_id"] == request_id


@pytest.mark.parametrize("path", ["/api/v1/nope", "/test-only/raise"])
def test_request_id_is_echoed_on_errors(client: TestClient, path: str) -> None:
    response = client.get(path, headers={"X-Request-ID": "req-1"})

    assert response.headers["x-request-id"] == "req-1"


@pytest.mark.parametrize(
    "raw",
    ["a" * 129, "x\ny", "é", ""],
    ids=["too-long", "newline", "non-ascii", "empty"],
)
def test_invalid_request_id_is_replaced(
    client: TestClient, capsys: pytest.CaptureFixture[str], raw: str
) -> None:
    capsys.readouterr()

    response = client.get(
        "/api/v1/health", headers={"X-Request-ID": raw.encode("utf-8")}
    )
    lines = _log_lines(capsys)
    record = json.loads(lines[0])

    assert UUID4.fullmatch(response.headers["x-request-id"])
    assert record["request_id"] == response.headers["x-request-id"]
    if raw:
        rendered = json.dumps(raw)[1:-1]
        assert not any(raw in line or rendered in line for line in lines)


def test_missing_request_id_is_generated(client: TestClient) -> None:
    first = client.get("/api/v1/health").headers["x-request-id"]
    second = client.get("/api/v1/health").headers["x-request-id"]

    assert UUID4.fullmatch(first)
    assert UUID4.fullmatch(second)
    assert first != second


def test_query_string_and_headers_are_not_logged(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    client.get("/api/v1/health?token=secret", headers={"Authorization": "Bearer x"})
    client.get("/api/v1/nope?token=secret", headers={"Authorization": "Bearer x"})
    out = capsys.readouterr().out

    assert len(out.splitlines()) == 2
    assert "secret" not in out
    assert "Bearer" not in out
    assert "/api/v1/nope" not in out


def test_request_context_is_pure_asgi_outermost_middleware() -> None:
    app = create_app()

    classes: list[object] = [m.cls for m in app.user_middleware]

    assert classes == [RequestContext]
    assert not issubclass(RequestContext, BaseHTTPMiddleware)
