import keyword
import re
from collections.abc import Mapping

from dogwatch.diagnostics import CONFIG_INVALID, Diagnostic, DogwatchError

KEBAB_ID_MAX_LENGTH = 64
_KEBAB_ID = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")


def key_path(*parts: str | int) -> str:
    rendered = ""
    for part in parts:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}" if rendered else part
    return rendered


def config_invalid(message: str) -> DogwatchError:
    return DogwatchError(
        (
            Diagnostic(
                source="dogwatch", id=CONFIG_INVALID, severity="error", message=message
            ),
        )
    )


def is_identifier(value: str) -> bool:
    return value.isidentifier() and not keyword.iskeyword(value)


def is_kebab_id(value: str) -> bool:
    return len(value) <= KEBAB_ID_MAX_LENGTH and _KEBAB_ID.fullmatch(value) is not None


def table_array(value: object, path: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
        raise config_invalid(f"{path} must be an array of tables")
    return tuple(value)


def require_str(table: Mapping[str, object], table_path: str, key: str) -> str:
    value = optional_str(table, table_path, key)
    if value is None:
        raise config_invalid(f"{key_path(table_path, key)} is required")
    return value


def optional_str(table: Mapping[str, object], table_path: str, key: str) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise config_invalid(f"{key_path(table_path, key)} must be a string")
    return value


def require_str_list(
    table: Mapping[str, object], table_path: str, key: str
) -> tuple[str, ...]:
    value = optional_str_list(table, table_path, key)
    if value is None:
        raise config_invalid(f"{key_path(table_path, key)} is required")
    return value


def optional_str_list(
    table: Mapping[str, object], table_path: str, key: str
) -> tuple[str, ...] | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(e, str) for e in value):
        raise config_invalid(f"{key_path(table_path, key)} must be an array of strings")
    return tuple(value)


def optional_bool(
    table: Mapping[str, object], table_path: str, key: str
) -> bool | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, bool):
        raise config_invalid(f"{key_path(table_path, key)} must be a boolean")
    return value
