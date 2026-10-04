from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

MEDIA_TYPE: Final = "application/problem+json"


@dataclass(frozen=True)
class ProblemCode:
    code: str
    status: int


NOT_FOUND: Final = ProblemCode("not-found", 404)
METHOD_NOT_ALLOWED: Final = ProblemCode("method-not-allowed", 405)
VALIDATION_FAILED: Final = ProblemCode("validation-failed", 422)
INTERNAL_ERROR: Final = ProblemCode("internal-error", 500)

SCHEMA_INVALID: Final = ProblemCode("schema-invalid", 400)
IN_FLIGHT: Final = ProblemCode("in-flight", 409)
PAYLOAD_TOO_LARGE: Final = ProblemCode("payload-too-large", 413)
IDEMPOTENCY_CONFLICT: Final = ProblemCode("idempotency-conflict", 422)
RATE_LIMITED: Final = ProblemCode("rate-limited", 429)

_TITLES: Final[Mapping[ProblemCode, str]] = {
    NOT_FOUND: "Not Found",
    METHOD_NOT_ALLOWED: "Method Not Allowed",
    VALIDATION_FAILED: "Validation Failed",
    INTERNAL_ERROR: "Internal Server Error",
}

INTERNAL_ERROR_DETAIL: Final = "Internal server error."


def problem_response(
    problem: ProblemCode, detail: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body = {
        "type": f"urn:dogwatch:problem:{problem.code}",
        "title": _TITLES[problem],
        "status": problem.status,
        "detail": detail,
        "code": problem.code,
    }
    return JSONResponse(
        body, status_code=problem.status, headers=headers, media_type=MEDIA_TYPE
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == NOT_FOUND.status:
        return problem_response(NOT_FOUND, f"No route matches {request.scope['path']}")
    if exc.status_code == METHOD_NOT_ALLOWED.status:
        allowed = ", ".join(sorted((exc.headers or {})["Allow"].split(", ")))
        return problem_response(
            METHOD_NOT_ALLOWED,
            f"Method {request.method} is not allowed; allowed: {allowed}",
            headers={"Allow": allowed},
        )
    raise exc


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return problem_response(
        VALIDATION_FAILED, f"Request validation failed ({len(exc.errors())} errors)"
    )


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
