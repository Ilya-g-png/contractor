import json
import logging
import sys
from datetime import UTC, datetime
from typing import Final

REQUEST_LOGGER: Final = "dogwatch_api.request"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": _timestamp(record.created),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        return json.dumps(line, separators=(",", ":"))


class StdoutHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def request_logger() -> logging.Logger:
    logger = logging.getLogger(REQUEST_LOGGER)
    if not logger.handlers:
        handler = StdoutHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def _timestamp(created: float) -> str:
    moment = datetime.fromtimestamp(created, UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
