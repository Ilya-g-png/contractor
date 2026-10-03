import logging
import re
import time
import traceback
import uuid
from typing import Any, Final

from starlette.routing import Match, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dogwatch_api.log import request_logger
from dogwatch_api.problems import (
    INTERNAL_ERROR,
    INTERNAL_ERROR_DETAIL,
    problem_response,
)

REQUEST_ID_HEADER: Final = b"x-request-id"
_VALID_REQUEST_ID: Final = re.compile(rb"[\x20-\x7E]{1,128}")


class RequestContext:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = request_logger()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_id = _request_id(scope)
        route = _route_template(scope)
        status: int | None = None
        error: Exception | None = None

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (REQUEST_ID_HEADER, request_id.encode("ascii")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            error = exc
            if status is not None:
                raise
            response = problem_response(INTERNAL_ERROR, INTERNAL_ERROR_DETAIL)
            await response(scope, receive, send_with_request_id)
        finally:
            fields: dict[str, Any] = {
                "request_id": request_id,
                "method": scope["method"],
                "route": route,
                "status": status if status is not None else INTERNAL_ERROR.status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            if error is not None:
                fields["error_type"] = _qualified_name(type(error))
                fields["error_traceback"] = "".join(traceback.format_exception(error))
            failed = error is not None or fields["status"] >= 500
            self.logger.log(
                logging.ERROR if failed else logging.INFO,
                "request",
                extra={"fields": fields},
            )


def _request_id(scope: Scope) -> str:
    for name, value in scope["headers"]:
        if name.lower() == REQUEST_ID_HEADER:
            if _VALID_REQUEST_ID.fullmatch(value):
                return str(value.decode("ascii"))
            break
    return str(uuid.uuid4())


def _route_template(scope: Scope) -> str | None:
    partial: str | None = None
    for route in scope["app"].router.routes:
        if not isinstance(route, Route):
            continue
        match, _ = route.matches(scope)
        if match is Match.FULL:
            return route.path
        if match is Match.PARTIAL and partial is None:
            partial = route.path
    return partial


def _qualified_name(cls: type[BaseException]) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"
