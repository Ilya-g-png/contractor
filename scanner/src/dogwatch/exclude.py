import os
import posixpath
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from dogwatch._validate import config_invalid, key_path
from dogwatch.diagnostics import EXCLUDE_UNMATCHED, Diagnostic, DogwatchError

_EXCLUDE = "python.exclude"
_FORBIDDEN_CHARACTERS = ("?", "[", "\\")


@dataclass(frozen=True)
class ExclusionDecl:
    pattern: str


class PackageLike(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def root(self) -> str: ...


def parse_exclusions(value: object) -> tuple[ExclusionDecl, ...]:
    if not isinstance(value, list):
        raise config_invalid(f"{_EXCLUDE} must be an array of strings")
    return tuple(_exclusion(index, entry) for index, entry in enumerate(value))


def _exclusion(index: int, entry: object) -> ExclusionDecl:
    path = key_path(_EXCLUDE, index)
    if not isinstance(entry, str):
        raise config_invalid(f"{path} must be a string")
    constraint = _syntax_violation(entry)
    if constraint is not None:
        raise config_invalid(f"{path} '{entry}' {constraint}")
    return ExclusionDecl(entry)


def _syntax_violation(pattern: str) -> str | None:
    if not pattern:
        return "must not be empty"
    if pattern.startswith("/"):
        return "must be relative"
    if any(segment in ("", ".", "..") for segment in pattern.split("/")):
        return "must not contain '.', '..' or empty segments"
    if any(character in pattern for character in _FORBIDDEN_CHARACTERS):
        return "may use only '*' as a wildcard ('?', '[' and '\\' are not allowed)"
    return None


def _compile(pattern: str) -> re.Pattern[str]:
    parts = (
        "(?:[^/]+/)*"
        if segment == "**"
        else "[^/]*".join(map(re.escape, segment.split("*"))) + "/"
        for segment in pattern.split("/")
    )
    return re.compile("".join(parts))


def matches(pattern: str, path: str) -> bool:
    return _compile(pattern).fullmatch(path + "/") is not None


def check_matches(
    config_dir: str,
    packages: tuple[PackageLike, ...],
    exclusions: tuple[ExclusionDecl, ...],
) -> None:
    if not exclusions:
        return
    candidates = [
        candidate + "/"
        for package in packages
        for candidate in _walk(
            os.path.join(config_dir, package.root, package.name),
            f"{package.root}/{package.name}",
        )
    ]
    unmatched = tuple(
        Diagnostic(
            source="dogwatch",
            id=EXCLUDE_UNMATCHED,
            severity="error",
            message=f"{key_path(_EXCLUDE, index)} '{exclusion.pattern}' "
            "matches no file under a declared package directory",
        )
        for index, exclusion in enumerate(exclusions)
        if not any(map(_compile(exclusion.pattern).fullmatch, candidates))
    )
    if unmatched:
        raise DogwatchError(unmatched)


def _walk(directory: str, relative: str) -> Iterator[str]:
    with os.scandir(directory) as entries:
        for entry in entries:
            child = f"{relative}/{entry.name}"
            if entry.is_file(follow_symlinks=False):
                yield posixpath.normpath(child)
            elif entry.is_dir(follow_symlinks=False):
                yield from _walk(entry.path, child)
