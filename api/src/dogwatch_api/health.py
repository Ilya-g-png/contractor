from typing import Literal

from pydantic import BaseModel

from dogwatch_api import __version__


class HealthStatus(BaseModel):
    status: Literal["ok"]
    service: Literal["dogwatch-api"]
    version: str


async def health() -> HealthStatus:
    return HealthStatus(status="ok", service="dogwatch-api", version=__version__)
