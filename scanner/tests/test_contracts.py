import ast
import builtins
import dataclasses
import io
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dogwatch.contracts import OpenApiContractDecl, parse_contracts
from dogwatch.diagnostics import Diagnostic, DogwatchError

CONTRACTS_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "dogwatch" / "contracts.py"
)
PUBLIC: dict[str, object] = {"id": "public-api", "path": "specs/openapi.yaml"}
KEBAB = "must be kebab-case ([a-z][a-z0-9]*(-[a-z0-9]+)*) and at most 64 characters"
SEGMENTS = "must not contain '.', '..' or empty segments"


def _second(**changes: object) -> dict[str, object]:
    return {"id": "internal-api", "path": "specs/internal.json", **changes}


def _without(entry: dict[str, object], key: str) -> dict[str, object]:
    return {k: v for k, v in entry.items() if k != key}


def _message(value: object) -> str:
    with pytest.raises(DogwatchError) as excinfo:
        parse_contracts(value)
    (diagnostic,) = excinfo.value.diagnostics
    assert diagnostic == Diagnostic(
        source="dogwatch",
        id="config-invalid",
        severity="error",
        message=diagnostic.message,
    )
    return diagnostic.message


def test_contract_decl_fields_are_unchanged() -> None:
    assert [
        (f.name, f.type, f.default) for f in dataclasses.fields(OpenApiContractDecl)
    ] == [("id", str, dataclasses.MISSING), ("path", str, dataclasses.MISSING)]


@pytest.mark.parametrize("value", [None, []])
def test_absent_or_empty_contracts_load_as_empty(value: object) -> None:
    assert parse_contracts(value) == ()


def test_contracts_load_in_config_order() -> None:
    contracts = parse_contracts(
        [PUBLIC, _second(), {"id": "admin", "path": "admin.yml"}]
    )

    assert contracts == (
        OpenApiContractDecl(id="public-api", path="specs/openapi.yaml"),
        OpenApiContractDecl(id="internal-api", path="specs/internal.json"),
        OpenApiContractDecl(id="admin", path="admin.yml"),
    )


def test_unknown_keys_inside_a_contract_entry_are_not_checked_here() -> None:
    assert parse_contracts([{**PUBLIC, "severity": "high"}]) == (
        OpenApiContractDecl(id="public-api", path="specs/openapi.yaml"),
    )


def test_missing_id_is_rejected() -> None:
    message = _message([PUBLIC, _without(_second(), "id")])

    assert message == "openapi.contracts[1].id is required"


def test_missing_path_is_rejected() -> None:
    message = _message([_without(PUBLIC, "path")])

    assert message == "openapi.contracts[0].path is required"


def test_duplicate_id_is_rejected() -> None:
    message = _message([PUBLIC, _second(), _second(id="public-api")])

    assert message == (
        "openapi.contracts[2].id 'public-api' duplicates openapi.contracts[0].id"
    )


def test_duplicate_path_is_rejected() -> None:
    message = _message(
        [PUBLIC, _second(), _second(id="copy", path="specs/openapi.yaml")]
    )

    assert message == (
        "openapi.contracts[2].path 'specs/openapi.yaml' duplicates "
        "openapi.contracts[0].path"
    )


def test_bad_extension_is_rejected() -> None:
    message = _message([PUBLIC, _second(path="specs/internal.txt")])

    assert message == (
        "openapi.contracts[1].path 'specs/internal.txt' "
        "must end in .yaml, .yml or .json"
    )


def test_absolute_path_is_rejected() -> None:
    message = _message([_second(path="/etc/openapi.yaml")])

    assert message == "openapi.contracts[0].path '/etc/openapi.yaml' must be relative"


def test_dotdot_segment_is_rejected() -> None:
    message = _message([PUBLIC, _second(path="../shared/openapi.yaml")])

    assert message == (f"openapi.contracts[1].path '../shared/openapi.yaml' {SEGMENTS}")


def test_backslashes_are_rejected() -> None:
    message = _message([_second(path="specs\\openapi.yaml")])

    assert message == (
        "openapi.contracts[0].path 'specs\\openapi.yaml' must use '/' separators"
    )


def test_dot_segment_is_rejected() -> None:
    message = _message([PUBLIC, _second(path="./specs/internal.json")])

    assert message == f"openapi.contracts[1].path './specs/internal.json' {SEGMENTS}"


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (_second(id=7), "openapi.contracts[0].id must be a string"),
        (_second(path=["a.yaml"]), "openapi.contracts[0].path must be a string"),
        (_second(id="Internal_API"), f"openapi.contracts[0].id 'Internal_API' {KEBAB}"),
        (_second(id="a" * 65), f"openapi.contracts[0].id '{'a' * 65}' {KEBAB}"),
        (_second(path=""), f"openapi.contracts[0].path '' {SEGMENTS}"),
        (
            _second(path="specs//a.yaml"),
            f"openapi.contracts[0].path 'specs//a.yaml' {SEGMENTS}",
        ),
        (
            _second(path="specs/openapi.YAML"),
            "openapi.contracts[0].path 'specs/openapi.YAML' "
            "must end in .yaml, .yml or .json",
        ),
    ],
)
def test_contract_field_rejected(entry: dict[str, object], message: str) -> None:
    assert _message([entry]) == message


@pytest.mark.parametrize(
    "value", [{"id": "x"}, "specs/openapi.yaml", [PUBLIC, "specs/openapi.yaml"]]
)
def test_contracts_not_an_array_of_tables_rejected(value: object) -> None:
    assert _message(value) == "openapi.contracts must be an array of tables"


def test_id_is_checked_before_path() -> None:
    message = _message([PUBLIC, {"id": "public-api", "path": "/abs.txt"}])

    assert message == (
        "openapi.contracts[1].id 'public-api' duplicates openapi.contracts[0].id"
    )


def test_path_uniqueness_is_textual() -> None:
    contracts = parse_contracts([PUBLIC, _second(path="Specs/openapi.yaml")])

    assert [c.path for c in contracts] == ["specs/openapi.yaml", "Specs/openapi.yaml"]


def test_missing_contract_file_loads_without_filesystem_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def recording(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            return fn(*args, **kwargs)

        return wrapper

    for module, attr in [
        (builtins, "open"),
        (io, "open"),
        (os, "open"),
        (os, "scandir"),
        (os, "stat"),
        (os, "lstat"),
    ]:
        monkeypatch.setattr(module, attr, recording(attr, getattr(module, attr)))

    contracts = parse_contracts([{"id": "ghost", "path": "nowhere/missing.json"}])

    assert calls == []
    assert contracts == (OpenApiContractDecl(id="ghost", path="nowhere/missing.json"),)


def test_contracts_imports_only_stdlib_validate_and_diagnostics() -> None:
    tree = ast.parse(CONTRACTS_SOURCE.read_bytes())
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
    assert "dogwatch.rules" not in imported
    assert {m for m in imported if m.partition(".")[0] == "dogwatch"} <= {
        "dogwatch._validate",
        "dogwatch.diagnostics",
    }
    assert all(
        m.partition(".")[0] in sys.stdlib_module_names
        for m in imported
        if m.partition(".")[0] != "dogwatch"
    )
