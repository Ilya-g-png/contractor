from fastapi import FastAPI

from dogwatch_api import __version__, health
from dogwatch_api.middleware import RequestContext
from dogwatch_api.problems import register_problem_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="dogwatch-api",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        redirect_slashes=False,
    )
    app.add_api_route("/api/v1/health", health.health, methods=["GET"])
    register_problem_handlers(app)
    app.add_middleware(RequestContext)
    return app
