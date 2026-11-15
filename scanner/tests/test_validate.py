import ast
import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dogwatch._validate import (
    config_invalid,
    is_identifier,
    is_kebab_id,
    key_path,
    optional_bool,
    optional_str,
    optional_str_list,
    require_str,
    require_str_list,
    table_array,
)
from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Diagnostic, DogwatchError
from dogwatch.exclude import ExclusionDecl
from dogwatch.rules import RuleDecl

SRC = Path(__file__).resolve().parents[1] / "src" / "dogwatch"


def _message(call: Callable[[], object]) -> str:
    with pytest.raises(DogwatchError) as excinfo:
        call()
    (diagnostic,) = excinfo.value.diagnostics
    assert diagnostic.id == "config-invalid"
    return diagnostic.message


def _imports(module: str) -> set[str]:
    tree = ast.parse((SRC / f"{module}.py").read_bytes())
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }


@pytest.mark.parametrize("value", ["a", "no-db-in-domain", "a1-b2", "a" * 64])
def test_is_kebab_id_accepts(value: str) -> None:
    assert is_kebab_id(value)


@pytest.mark.parametrize(
    "value", ["a" * 65, "A", "a_b", "a:b", "-a", "a--b", "a-", "1a", ""]
)
def test_is_kebab_id_rejects(value: str) -> None:
    assert not is_kebab_id(value)


@pytest.mark.parametrize("value", ["acme", "_private", "Shop2"])
def test_is_identifier_accepts(value: str) -> None:
    assert is_identifier(value)


@pytest.mark.parametrize("value", ["class", "foo-bar", "", "a.b", "1abc"])
def test_is_identifier_rejects(value: str) -> None:
    assert not is_identifier(value)


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (("python", "rules", 1, "targets", 0), "python.rules[1].targets[0]"),
        (("python.rules", 1, "targets", 0), "python.rules[1].targets[0]"),
        (("python", "packages", 0, "name"), "python.packages[0].name"),
        (("python", "exclude", 2), "python.exclude[2]"),
        (("openapi", "contracts", 0, "path"), "openapi.contracts[0].path"),
        (("python",), "python"),
    ],
)
def test_key_path_rendering(parts: tuple[str | int, ...], expected: str) -> None:
    assert key_path(*parts) == expected


def test_config_invalid_carries_one_config_invalid_diagnostic() -> None:
    err = config_invalid("python must be a table")

    assert isinstance(err, DogwatchError)
    assert err.diagnostics == (
        Diagnostic(
            source="dogwatch",
            id="config-invalid",
            severity="error",
            message="python must be a table",
        ),
    )


def test_require_str_returns_value() -> None:
    assert require_str({"id": "x"}, "python.rules[0]", "id") == "x"


@pytest.mark.parametrize(
    ("accessor", "expected"),
    [
        (require_str, "python.packages[1].root is required"),
        (require_str_list, "python.packages[1].root is required"),
    ],
)
def test_required_accessor_wording(
    accessor: Callable[[dict[str, Any], str, str], object], expected: str
) -> None:
    assert _message(lambda: accessor({}, "python.packages[1]", "root")) == expected


@pytest.mark.parametrize(
    ("accessor", "value", "expected"),
    [
        (require_str, 1, "python.packages[0].name must be a string"),
        (optional_str, ["src"], "python.packages[0].name must be a string"),
        (
            require_str_list,
            "acme",
            "python.packages[0].name must be an array of strings",
        ),
        (
            optional_str_list,
            ["acme", 1],
            "python.packages[0].name must be an array of strings",
        ),
        (optional_bool, "true", "python.packages[0].name must be a boolean"),
    ],
)
def test_accessor_type_wording(
    accessor: Callable[[dict[str, Any], str, str], object], value: Any, expected: str
) -> None:
    table = {"name": value}

    assert _message(lambda: accessor(table, "python.packages[0]", "name")) == expected


def test_optional_accessors_return_none_when_absent() -> None:
    assert optional_str({}, "t", "k") is None
    assert optional_str_list({}, "t", "k") is None
    assert optional_bool({}, "t", "k") is None


def test_list_and_bool_accessors_return_values() -> None:
    table: dict[str, Any] = {"targets": ["a", "b.c"], "exhaustive": False}

    assert require_str_list(table, "python.rules[0]", "targets") == ("a", "b.c")
    assert optional_str_list({"sources": []}, "t", "sources") == ()
    assert optional_bool(table, "python.rules[0]", "exhaustive") is False


@pytest.mark.parametrize("value", [1, {"id": "x"}, [1], [{"id": "x"}, "y"]])
def test_table_array_rejects(value: object) -> None:
    assert _message(lambda: table_array(value, "python.rules")) == (
        "python.rules must be an array of tables"
    )


def test_table_array_returns_entries() -> None:
    assert table_array([{"id": "x"}], "openapi.contracts") == ({"id": "x"},)
    assert table_array([], "openapi.contracts") == ()


def test_rule_decl_defaults_follow_dc_c4() -> None:
    forbid = RuleDecl(id="no-db", kind="forbid", reason="r", targets=("db",))
    layers = RuleDecl(id="layering", kind="layers", reason="r", layers=("a", "b"))

    assert (forbid.sources, forbid.except_sources, forbid.except_targets) == (
        (),
        (),
        (),
    )
    assert (forbid.layers, forbid.container, forbid.exhaustive) == ((), None, False)
    assert (layers.targets, layers.container, layers.exhaustive) == ((), None, False)


@pytest.mark.parametrize(
    ("entity", "field"),
    [
        (ExclusionDecl("src/acme/**"), "pattern"),
        (RuleDecl(id="r", kind="forbid", reason="x", targets=("db",)), "id"),
        (OpenApiContractDecl("public-api", "openapi.yaml"), "path"),
    ],
)
def test_entities_are_frozen(entity: object, field: str) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(entity, field, "other")


def test_validate_imports_only_diagnostics_from_dogwatch() -> None:
    assert {m for m in _imports("_validate") if m.startswith("dogwatch")} == {
        "dogwatch.diagnostics"
    }
