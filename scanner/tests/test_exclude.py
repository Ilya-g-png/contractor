import ast
import builtins
import dataclasses
import io
import os
import sys
import typing
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pytest

from dogwatch.config import PackageDecl
from dogwatch.diagnostics import Diagnostic, DogwatchError
from dogwatch.exclude import (
    ExclusionDecl,
    PackageLike,
    check_matches,
    matches,
    parse_exclusions,
)

EXCLUDE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "dogwatch" / "exclude.py"
SHOP = (PackageDecl("shop", "src"),)
SEGMENTS = "must not contain '.', '..' or empty segments"
WILDCARD = "may use only '*' as a wildcard ('?', '[' and '\\' are not allowed)"


def _tree(root: Path, files: Iterable[str]) -> None:
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")


def _exclusions(*patterns: str) -> tuple[ExclusionDecl, ...]:
    return tuple(ExclusionDecl(p) for p in patterns)


def _unmatched(
    config_dir: Path,
    packages: tuple[PackageLike, ...],
    *patterns: str,
) -> tuple[Diagnostic, ...]:
    with pytest.raises(DogwatchError) as excinfo:
        check_matches(str(config_dir), packages, _exclusions(*patterns))
    diagnostics = excinfo.value.diagnostics
    assert all(
        d.source == "dogwatch" and d.severity == "error" and d.id == "exclude-unmatched"
        for d in diagnostics
    )
    return diagnostics


def _diagnostic(index: int, pattern: str) -> Diagnostic:
    return Diagnostic(
        source="dogwatch",
        id="exclude-unmatched",
        severity="error",
        message=f"python.exclude[{index}] '{pattern}' "
        "matches no file under a declared package directory",
    )


def test_exclusion_decl_fields_are_frozen_to_pattern() -> None:
    assert [f.name for f in dataclasses.fields(ExclusionDecl)] == ["pattern"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ExclusionDecl("a").pattern = "b"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([], ()),
        (["src/shop/**", "src/shop/*.py"], _exclusions("src/shop/**", "src/shop/*.py")),
        (["src/shop/legacy/x.py"], _exclusions("src/shop/legacy/x.py")),
        (["src/shop/a**b.py"], _exclusions("src/shop/a**b.py")),
    ],
)
def test_parse_exclusions_accepts_valid_patterns_in_config_order(
    value: object, expected: tuple[ExclusionDecl, ...]
) -> None:
    assert parse_exclusions(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("src/shop/**", "python.exclude must be an array of strings"),
        ({"a": "b"}, "python.exclude must be an array of strings"),
        (["src/a.py", 3], "python.exclude[1] must be a string"),
        ([None], "python.exclude[0] must be a string"),
        ([""], "python.exclude[0] '' must not be empty"),
        (["/src/a.py"], "python.exclude[0] '/src/a.py' must be relative"),
        (["src/a.py", "/"], "python.exclude[1] '/' must be relative"),
        (["."], f"python.exclude[0] '.' {SEGMENTS}"),
        (["src/./a.py"], f"python.exclude[0] 'src/./a.py' {SEGMENTS}"),
        ([".."], f"python.exclude[0] '..' {SEGMENTS}"),
        (["src/../a.py"], f"python.exclude[0] 'src/../a.py' {SEGMENTS}"),
        (["src//a.py"], f"python.exclude[0] 'src//a.py' {SEGMENTS}"),
        (["src/"], f"python.exclude[0] 'src/' {SEGMENTS}"),
        (["src/?.py"], f"python.exclude[0] 'src/?.py' {WILDCARD}"),
        (["src/[ab].py"], f"python.exclude[0] 'src/[ab].py' {WILDCARD}"),
        (["src\\a.py"], f"python.exclude[0] 'src\\a.py' {WILDCARD}"),
        (["ok/*.py", "", "/a"], "python.exclude[1] '' must not be empty"),
    ],
)
def test_parse_exclusions_rejects_with_one_ic_err_4_diagnostic(
    value: object, message: str
) -> None:
    with pytest.raises(DogwatchError) as excinfo:
        parse_exclusions(value)

    assert excinfo.value.diagnostics == (
        Diagnostic(
            source="dogwatch", id="config-invalid", severity="error", message=message
        ),
    )


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("src/shop/**/*.py", "src/shop/a.py", True),
        ("src/shop/**/*.py", "src/shop/x/y/b.py", True),
        ("src/shop/**/*.py", "src/shop/x/y/b.pyc", False),
        ("src/shop/*.py", "src/shop/a.py", True),
        ("src/shop/*.py", "src/shop/x/b.py", False),
        ("src/shop/**", "src/shop/x/y/b.py", True),
        ("**/b.py", "src/shop/x/y/b.py", True),
        ("src/shop", "src/shop/a.py", False),
        ("src/shop/a.py", "src/shop/a.py", True),
        ("src/shop/a.py", "src/shop/a.pyx", False),
        ("src/shop/a.py", "x/src/shop/a.py", False),
        ("src/shop/a**b", "src/shop/ab", True),
        ("src/shop/a**b", "src/shop/axyb", True),
        ("src/shop/a**b", "src/shop/a/b", False),
        ("src/shop/a*b", "src/shop/a/b", False),
        ("src/shop/A.py", "src/shop/a.py", False),
        ("src/shop/a.py", "src/shop/A.py", False),
        ("src/shop/*.PY", "src/shop/a.py", False),
        ("src/shop/a+b(1).py", "src/shop/a+b(1).py", True),
        ("src/shop/a.py", "src/shop/aXpy", False),
    ],
)
def test_matcher_follows_glob_contract(pattern: str, path: str, expected: bool) -> None:
    assert matches(pattern, path) is expected


@pytest.mark.parametrize("path", ["src/shop/ab", "src/shop/axyb", "src/shop/a/b"])
def test_double_star_inside_segment_behaves_like_single_star(path: str) -> None:
    assert matches("src/shop/a**b", path) is matches("src/shop/a*b", path)


def test_check_matches_accepts_overlapping_patterns_on_same_file(
    tmp_path: Path,
) -> None:
    _tree(tmp_path, ["src/shop/legacy/x.py"])

    check_matches(
        str(tmp_path),
        SHOP,
        _exclusions("src/shop/**", "src/shop/legacy/*.py", "src/shop/legacy/x.py"),
    )


def test_check_matches_normalizes_root_in_candidates(tmp_path: Path) -> None:
    _tree(tmp_path, ["src/shop/legacy/x.py", "lib/core/y.py"])

    check_matches(
        str(tmp_path),
        (PackageDecl("shop", "./src"), PackageDecl("core", "lib/../lib")),
        _exclusions("src/shop/legacy/x.py", "lib/core/y.py"),
    )


def test_check_matches_reports_pattern_matching_only_a_directory(
    tmp_path: Path,
) -> None:
    _tree(tmp_path, ["src/shop/legacy/x.py"])

    assert _unmatched(tmp_path, SHOP, "src/shop/legacy") == (
        _diagnostic(0, "src/shop/legacy"),
    )


@pytest.mark.parametrize("pattern", ["src/*.py", "setup.py", "src/other/**"])
def test_check_matches_reports_pattern_matching_only_files_outside_package(
    tmp_path: Path, pattern: str
) -> None:
    _tree(tmp_path, ["src/shop/a.py", "src/top.py", "setup.py", "src/other/b.py"])

    assert _unmatched(tmp_path, SHOP, pattern) == (_diagnostic(0, pattern),)


def test_check_matches_ignores_symlink_to_file(tmp_path: Path) -> None:
    _tree(tmp_path, ["src/shop/a.py", "outside.py"])
    (tmp_path / "src" / "shop" / "link.py").symlink_to(tmp_path / "outside.py")

    assert _unmatched(tmp_path, SHOP, "src/shop/link.py") == (
        _diagnostic(0, "src/shop/link.py"),
    )


@pytest.mark.parametrize("pattern", ["src/shop/linked/m.py", "src/shop/linked/**"])
def test_check_matches_never_descends_symlink_to_directory(
    tmp_path: Path, pattern: str
) -> None:
    _tree(tmp_path, ["src/shop/a.py", "external/m.py"])
    (tmp_path / "src" / "shop" / "linked").symlink_to(tmp_path / "external")

    assert _unmatched(tmp_path, SHOP, pattern) == (_diagnostic(0, pattern),)


def test_check_matches_reports_each_unmatched_pattern_in_config_order(
    tmp_path: Path,
) -> None:
    _tree(tmp_path, ["src/shop/a.py"])

    assert _unmatched(
        tmp_path, SHOP, "src/shop/z.py", "src/shop/a.py", "src/shop/b/**", "x.py"
    ) == (
        _diagnostic(0, "src/shop/z.py"),
        _diagnostic(2, "src/shop/b/**"),
        _diagnostic(3, "x.py"),
    )


def test_check_matches_searches_every_declared_package(tmp_path: Path) -> None:
    _tree(tmp_path, ["src/shop/a.py", "lib/core/b.py"])
    packages = (PackageDecl("shop", "src"), PackageDecl("core", "lib"))

    check_matches(str(tmp_path), packages, _exclusions("lib/core/b.py"))


def test_check_matches_accepts_any_object_with_name_and_root(tmp_path: Path) -> None:
    @dataclasses.dataclass(frozen=True)
    class Package:
        name: str
        root: str

    _tree(tmp_path, ["src/shop/a.py"])

    check_matches(str(tmp_path), (Package("shop", "src"),), _exclusions("**/a.py"))


def _record(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], list[str]]:
    opened: list[str] = []
    scanned: list[str] = []

    def recording(fn: Callable[..., Any], calls: list[str]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            calls.append(os.path.realpath(os.fsdecode(args[0] if args else ".")))
            return fn(*args, **kwargs)

        return wrapper

    for module, attr in [(builtins, "open"), (io, "open"), (os, "open")]:
        monkeypatch.setattr(module, attr, recording(getattr(module, attr), opened))
    monkeypatch.setattr(os, "scandir", recording(os.scandir, scanned))
    return opened, scanned


def test_check_matches_never_opens_and_lists_only_under_package_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(
        tmp_path,
        [
            "src/shop/a.py",
            "src/shop/x/y/b.py",
            "src/sibling/c.py",
            "lib/core/d.py",
            "external/e.py",
        ],
    )
    (tmp_path / "src" / "shop" / "linked").symlink_to(tmp_path / "external")
    (tmp_path / "lib" / "core" / "up").symlink_to(tmp_path / "src")
    packages = (PackageDecl("shop", "src"), PackageDecl("core", "lib"))
    package_dirs = [os.path.realpath(tmp_path / p.root / p.name) for p in packages]
    opened, scanned = _record(monkeypatch)

    with pytest.raises(DogwatchError):
        check_matches(
            str(tmp_path), packages, _exclusions("src/shop/**/b.py", "nothing.py")
        )

    assert opened == []
    shop, core = package_dirs
    assert sorted(scanned) == sorted(
        [shop, os.path.join(shop, "x"), os.path.join(shop, "x", "y"), core]
    )
    assert all(
        any(s == d or s.startswith(d + os.sep) for d in package_dirs) for s in scanned
    )


def test_check_matches_skips_walk_without_exclusions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path, ["src/shop/a.py"])
    opened, scanned = _record(monkeypatch)

    check_matches(str(tmp_path), SHOP, ())

    assert opened == []
    assert scanned == []


def test_packages_are_typed_against_module_local_read_only_protocol() -> None:
    hints = typing.get_type_hints(check_matches)

    assert hints["packages"] == tuple[PackageLike, ...]
    assert PackageLike.__module__ == "dogwatch.exclude"
    assert typing.Protocol in PackageLike.__mro__
    assert isinstance(PackageLike.__dict__["name"], property)
    assert isinstance(PackageLike.__dict__["root"], property)
    assert PackageLike.__dict__["name"].fset is None
    assert PackageLike.__dict__["root"].fset is None


def test_exclude_imports_only_stdlib_validate_and_diagnostics() -> None:
    tree = ast.parse(EXCLUDE_SOURCE.read_bytes())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level]
    assert {m for m in imported if m.partition(".")[0] == "dogwatch"} <= {
        "dogwatch._validate",
        "dogwatch.diagnostics",
    }
    assert all(
        m.partition(".")[0] in sys.stdlib_module_names
        for m in imported
        if m.partition(".")[0] != "dogwatch"
    )
