import hashlib
import json
import os
from typing import Any

from dogwatch.config import PolicyConfig

SCHEMA_VERSION = "0.1"
SCANNER_NAME = "dogwatch"


def build_report(cfg: PolicyConfig, version: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "scanner": {"name": SCANNER_NAME, "version": version},
        "policy": {
            "path": os.path.basename(cfg.path_arg),
            "digest": {"sha256": hashlib.sha256(cfg.raw).hexdigest()},
        },
        "findings": [],
    }


def serialize_canonical(obj: Any) -> bytes:
    return (
        json.dumps(
            obj, sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": ")
        )
        + "\n"
    ).encode("utf-8")
