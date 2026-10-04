import os
import re
import tomllib
from dataclasses import dataclass
from typing import Any, NamedTuple

from dogwatch.diagnostics import Diagnostic, DogwatchError

_ENTRY_KEYS = ("name", "root")
_TOML_LINE = re.compile(r"at line (\d+)")
_TOML_POSITION = re.compile(r" \((?:at line \d+, column \d+|at end of document)\)$")


@dataclass(frozen=True)
class PackageDecl:
    name: str
    root: str


@dataclass(frozen=True)
class PolicyConfig:
    path_arg: str
    raw: bytes
    packages: tuple[PackageDecl, ...]


class _Located(NamedTuple):
    decl: PackageDecl
    root_real: str
    package_real: str


def load_policy(config_arg: str) -> PolicyConfig:
    if not os.path.lexists(config_arg):
        raise DogwatchError(
            (Diagnostic("config-not-found", f"{config_arg} does not exist"),)
        )
    raw = _read(config_arg)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _invalid(f"{config_arg} is not valid UTF-8") from None
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise _invalid(
            f"{config_arg}:{_error_line(exc)}: invalid TOML: {_error_msg(exc)}"
        ) from None
    packages = _validate_shape(config_arg, document)
    _validate_structure(os.path.dirname(config_arg), packages)
    return PolicyConfig(config_arg, raw, packages)


def _invalid(message: str) -> DogwatchError:
    return DogwatchError((Diagnostic("config-invalid", message),))


def _read(config_arg: str) -> bytes:
    not_readable = f"{config_arg} is not a readable file"
    if not os.path.isfile(config_arg):
        raise _invalid(not_readable)
    try:
        with open(config_arg, "rb") as f:
            return f.read()
    except OSError:
        raise _invalid(not_readable) from None


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
    unknown = [key for key in document if key != "python"]
    python = document.get("python")
    if isinstance(python, dict):
        unknown += [f"python.{key}" for key in python if key != "packages"]
        entries = python.get("packages")
        if isinstance(entries, list):
            for i, entry in enumerate(entries):
                if isinstance(entry, dict):
                    unknown += [
                        f"python.packages[{i}].{key}"
                        for key in entry
                        if key not in _ENTRY_KEYS
                    ]
    return unknown


def _validate_shape(
    config_arg: str, document: dict[str, Any]
) -> tuple[PackageDecl, ...]:
    unknown = sorted(_unknown_keys(document))
    if unknown:
        raise _invalid(f"{unknown[0]} is not supported in this version")
    requires_entry = f"{config_arg} requires at least one [[python.packages]] entry"
    if "python" not in document:
        raise _invalid(requires_entry)
    python = document["python"]
    if not isinstance(python, dict):
        raise _invalid("python must be a table")
    if "packages" not in python:
        raise _invalid(requires_entry)
    entries = python["packages"]
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise _invalid("python.packages must be a array of tables")
    if not entries:
        raise _invalid(requires_entry)
    return tuple(_package(i, entry) for i, entry in enumerate(entries))


def _package(index: int, entry: dict[str, Any]) -> PackageDecl:
    name = _string_field(index, entry, "name")
    if not name.isidentifier():
        raise _invalid(
            f"python.packages[{index}].name '{name}' "
            "must be a single top-level identifier"
        )
    return PackageDecl(name, _string_field(index, entry, "root"))


def _string_field(index: int, entry: dict[str, Any], key: str) -> str:
    dotted = f"python.packages[{index}].{key}"
    if key not in entry:
        raise _invalid(f"{dotted} is required")
    value = entry[key]
    if not isinstance(value, str):
        raise _invalid(f"{dotted} must be a string")
    return value


def _validate_structure(config_dir: str, packages: tuple[PackageDecl, ...]) -> None:
    failures: list[Diagnostic] = []
    located: list[_Located] = []
    for decl in packages:
        root_dir = os.path.join(config_dir, decl.root)
        package_dir = os.path.join(root_dir, decl.name)
        shown = f"'{decl.root}/{decl.name}'"
        if not os.path.lexists(package_dir):
            failures.append(
                Diagnostic(
                    "config-invalid",
                    f"package '{decl.name}': directory {shown} does not exist",
                )
            )
        elif not os.path.isdir(package_dir):
            failures.append(
                Diagnostic(
                    "config-invalid",
                    f"package '{decl.name}': {shown} is not a directory",
                )
            )
        else:
            located.append(
                _Located(
                    decl, os.path.realpath(root_dir), os.path.realpath(package_dir)
                )
            )
    for i, first in enumerate(located):
        for second in located[i + 1 :]:
            conflict = _conflict(first, second)
            if conflict is not None:
                failures.append(Diagnostic("config-invalid", conflict))
    if failures:
        raise DogwatchError(tuple(failures))


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
