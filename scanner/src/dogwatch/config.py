import os
import re
import tomllib
from dataclasses import dataclass
from typing import Any, NamedTuple

from dogwatch._validate import config_invalid, is_identifier, key_path, require_str
from dogwatch.contracts import OpenApiContractDecl, parse_contracts
from dogwatch.diagnostics import (
    CONFIG_INVALID,
    CONFIG_NOT_FOUND,
    Diagnostic,
    DogwatchError,
)
from dogwatch.exclude import ExclusionDecl, check_matches, parse_exclusions
from dogwatch.rules import RuleDecl, parse_rules

_PACKAGES = "python.packages"
_TOP_LEVEL_KEYS = frozenset({"python", "openapi"})
_PYTHON_KEYS = frozenset({"packages", "exclude", "rules"})
_OPENAPI_KEYS = frozenset({"contracts"})
_PACKAGE_KEYS = frozenset({"name", "root"})
_CONTRACT_KEYS = frozenset({"id", "path"})
_TOML_LINE = re.compile(r"at line (\d+)")
_TOML_POSITION = re.compile(r" \((?:at line \d+, column \d+|at end of document)\)$")


@dataclass(frozen=True)
class PackageDecl:
    name: str
    root: str


@dataclass(frozen=True)
class DogwatchConfig:
    path_arg: str
    raw: bytes
    packages: tuple[PackageDecl, ...]
    exclusions: tuple[ExclusionDecl, ...]
    rules: tuple[RuleDecl, ...]
    contracts: tuple[OpenApiContractDecl, ...]


class _Located(NamedTuple):
    position: int
    decl: PackageDecl
    root_real: str
    package_real: str


def load_policy(config_arg: str) -> DogwatchConfig:
    if not os.path.lexists(config_arg):
        raise DogwatchError(
            (
                Diagnostic(
                    source="dogwatch",
                    id=CONFIG_NOT_FOUND,
                    severity="error",
                    message=f"{config_arg} does not exist",
                ),
            )
        )
    raw = _read(config_arg)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise config_invalid(f"{config_arg} is not valid UTF-8") from None
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise config_invalid(
            f"{config_arg}:{_error_line(exc)}: invalid TOML: {_error_msg(exc)}"
        ) from None

    unknown = sorted(_unknown_keys(document))
    if unknown:
        raise config_invalid(f"{unknown[0]} is not supported in this version")
    python = _python_table(config_arg, document)
    packages = _packages(config_arg, python)
    exclusions = parse_exclusions(python["exclude"]) if "exclude" in python else ()
    rules = parse_rules(python.get("rules"))
    contracts = parse_contracts(_openapi_table(document).get("contracts"))

    config_dir = os.path.dirname(config_arg)
    _validate_structure(config_dir, packages)
    if exclusions:
        check_matches(config_dir, packages, exclusions)
    return DogwatchConfig(config_arg, raw, packages, exclusions, rules, contracts)


def _config_invalid(message: str) -> Diagnostic:
    return Diagnostic(
        source="dogwatch", id=CONFIG_INVALID, severity="error", message=message
    )


def _read(config_arg: str) -> bytes:
    not_readable = f"{config_arg} is not a readable file"
    if not os.path.isfile(config_arg):
        raise config_invalid(not_readable)
    try:
        with open(config_arg, "rb") as f:
            return f.read()
    except OSError:
        raise config_invalid(not_readable) from None


def _error_line(exc: tomllib.TOMLDecodeError) -> str:
    lineno = getattr(exc, "lineno", None)
    if isinstance(lineno, int):
        return str(lineno)
    match = _TOML_LINE.search(str(exc))
    return match.group(1) if match else "?"


def _error_msg(exc: tomllib.TOMLDecodeError) -> str:
    msg = getattr(exc, "msg", None)
    if isinstance(msg, str):
        return msg
    return _TOML_POSITION.sub("", str(exc))


def _unknown_keys(document: dict[str, Any]) -> list[str]:
    unknown = _unknown(document, _TOP_LEVEL_KEYS)
    python = document.get("python")
    if isinstance(python, dict):
        unknown += _unknown(python, _PYTHON_KEYS, "python")
        unknown += _unknown_in_entries(python.get("packages"), _PACKAGE_KEYS, _PACKAGES)
    openapi = document.get("openapi")
    if isinstance(openapi, dict):
        unknown += _unknown(openapi, _OPENAPI_KEYS, "openapi")
        unknown += _unknown_in_entries(
            openapi.get("contracts"), _CONTRACT_KEYS, "openapi.contracts"
        )
    return unknown


def _unknown(
    table: dict[str, Any], accepted: frozenset[str], *path: str | int
) -> list[str]:
    return [key_path(*path, key) for key in table if key not in accepted]


def _unknown_in_entries(
    entries: object, accepted: frozenset[str], path: str
) -> list[str]:
    if not isinstance(entries, list):
        return []
    return [
        key
        for index, entry in enumerate(entries)
        if isinstance(entry, dict)
        for key in _unknown(entry, accepted, path, index)
    ]


def _python_table(config_arg: str, document: dict[str, Any]) -> dict[str, Any]:
    if "python" not in document:
        raise config_invalid(_requires_entry(config_arg))
    python = document["python"]
    if not isinstance(python, dict):
        raise config_invalid("python must be a table")
    return python


def _openapi_table(document: dict[str, Any]) -> dict[str, Any]:
    openapi = document.get("openapi", {})
    if not isinstance(openapi, dict):
        raise config_invalid("openapi must be a table")
    return openapi


def _requires_entry(config_arg: str) -> str:
    return f"{config_arg} requires at least one [[python.packages]] entry"


def _packages(config_arg: str, python: dict[str, Any]) -> tuple[PackageDecl, ...]:
    if "packages" not in python:
        raise config_invalid(_requires_entry(config_arg))
    entries = python["packages"]
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise config_invalid(f"{_PACKAGES} must be a array of tables")
    if not entries:
        raise config_invalid(_requires_entry(config_arg))
    return tuple(_package(index, entry) for index, entry in enumerate(entries))


def _package(index: int, entry: dict[str, Any]) -> PackageDecl:
    path = key_path(_PACKAGES, index)
    name = require_str(entry, path, "name")
    if not is_identifier(name):
        raise config_invalid(
            f"{key_path(path, 'name')} '{name}' must be a single top-level identifier"
        )
    return PackageDecl(name, require_str(entry, path, "root"))


def _validate_structure(config_dir: str, packages: tuple[PackageDecl, ...]) -> None:
    failures: list[Diagnostic] = []
    located: list[_Located] = []
    for index, decl in enumerate(packages):
        root_dir = os.path.join(config_dir, decl.root)
        package_dir = os.path.join(root_dir, decl.name)
        shown = f"'{decl.root}/{decl.name}'"
        if not os.path.lexists(package_dir):
            failures.append(
                _package_invalid(
                    index, f"package '{decl.name}': directory {shown} does not exist"
                )
            )
        elif not os.path.isdir(package_dir):
            failures.append(
                _package_invalid(
                    index, f"package '{decl.name}': {shown} is not a directory"
                )
            )
        else:
            located.append(
                _Located(
                    index,
                    decl,
                    os.path.realpath(root_dir),
                    os.path.realpath(package_dir),
                )
            )
    for i, first in enumerate(located):
        for second in located[i + 1 :]:
            conflict = _conflict(first, second)
            if conflict is not None:
                failures.append(_package_invalid(second.position, conflict))
    if failures:
        raise DogwatchError(tuple(failures))


def _package_invalid(index: int, message: str) -> Diagnostic:
    return _config_invalid(f"{key_path(_PACKAGES, index)}: {message}")


def _conflict(first: _Located, second: _Located) -> str | None:
    a, b = first.decl, second.decl
    if a.name == b.name:
        if first.root_real == second.root_real:
            return f"package '{b.name}' is declared more than once (root '{b.root}')"
        return f"package '{a.name}' split across roots '{a.root}', '{b.root}'"
    if _within(first.package_real, second.package_real) or _within(
        second.package_real, first.package_real
    ):
        return (
            f"packages '{a.name}' ('{a.root}/{a.name}') "
            f"and '{b.name}' ('{b.root}/{b.name}') are nested"
        )
    return None


def _within(inner: str, outer: str) -> bool:
    return inner == outer or inner.startswith(os.path.join(outer, ""))
