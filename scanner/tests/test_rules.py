import ast
import builtins
import dataclasses
import io
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import pytest

from dogwatch.diagnostics import Diagnostic, DogwatchError
from dogwatch.rules import RuleDecl, parse_rules

RULES_SOURCE = Path(__file__).resolve().parents[1] / "src" / "dogwatch" / "rules.py"
FORBID: dict[str, object] = {
    "id": "no-db",
    "kind": "forbid",
    "reason": "domain stays pure",
    "targets": ["shop.db"],
}
LAYERS: dict[str, object] = {
    "id": "layering",
    "kind": "layers",
    "reason": "one-way deps",
    "layers": ["shop.api", "shop.domain"],
}
KEBAB = "must be kebab-case ([a-z][a-z0-9]*(-[a-z0-9]+)*) and at most 64 characters"
NOT_SUPPORTED = "is not supported in this version"


def _forbid(**changes: object) -> dict[str, object]:
    return {**FORBID, "id": "second", **changes}


def _layers(**changes: object) -> dict[str, object]:
    return {**LAYERS, "id": "second", **changes}


def _without(entry: dict[str, object], key: str) -> dict[str, object]:
    return {k: v for k, v in entry.items() if k != key}


def _message(value: object) -> str:
    with pytest.raises(DogwatchError) as excinfo:
        parse_rules(value)
    (diagnostic,) = excinfo.value.diagnostics
    assert diagnostic == Diagnostic(
        source="dogwatch",
        id="config-invalid",
        severity="error",
        message=diagnostic.message,
    )
    return diagnostic.message


def test_rule_decl_fields_are_unchanged() -> None:
    assert [(f.name, f.type, f.default) for f in dataclasses.fields(RuleDecl)] == [
        ("id", str, dataclasses.MISSING),
        ("kind", Literal["forbid", "layers"], dataclasses.MISSING),
        ("reason", str, dataclasses.MISSING),
        ("targets", tuple[str, ...], ()),
        ("sources", tuple[str, ...], ()),
        ("except_sources", tuple[str, ...], ()),
        ("except_targets", tuple[str, ...], ()),
        ("layers", tuple[str, ...], ()),
        ("container", str | None, None),
        ("exhaustive", bool, False),
    ]


@pytest.mark.parametrize("value", [None, []])
def test_absent_or_empty_rules_load_as_empty(value: object) -> None:
    assert parse_rules(value) == ()


def test_forbid_with_all_optional_keys_loads() -> None:
    rule = {
        **FORBID,
        "targets": ["shop.db", "sqlalchemy"],
        "sources": ["shop.domain"],
        "except_sources": ["shop.domain.adapters"],
        "except_targets": ["shop.db.types"],
    }

    assert parse_rules([rule]) == (
        RuleDecl(
            id="no-db",
            kind="forbid",
            reason="domain stays pure",
            targets=("shop.db", "sqlalchemy"),
            sources=("shop.domain",),
            except_sources=("shop.domain.adapters",),
            except_targets=("shop.db.types",),
        ),
    )


def test_forbid_with_only_targets_defaults_sources_and_layers_fields() -> None:
    (rule,) = parse_rules([FORBID])

    assert rule.targets == ("shop.db",)
    assert (rule.sources, rule.except_sources, rule.except_targets) == ((), (), ())
    assert (rule.layers, rule.container, rule.exhaustive) == ((), None, False)


def test_exhaustive_layers_with_container_loads() -> None:
    rule = {**LAYERS, "container": "shop", "exhaustive": True}

    assert parse_rules([rule]) == (
        RuleDecl(
            id="layering",
            kind="layers",
            reason="one-way deps",
            layers=("shop.api", "shop.domain"),
            container="shop",
            exhaustive=True,
        ),
    )


def test_layers_without_container_defaults_and_keeps_forbid_fields_empty() -> None:
    (rule,) = parse_rules([LAYERS])

    assert rule.layers == ("shop.api", "shop.domain")
    assert (rule.container, rule.exhaustive) == (None, False)
    assert (rule.targets, rule.sources, rule.except_sources, rule.except_targets) == (
        (),
        (),
        (),
        (),
    )


def test_rules_keep_config_order() -> None:
    rules = parse_rules([LAYERS, FORBID, _forbid(id="third", kind="forbid")])

    assert [r.id for r in rules] == ["layering", "no-db", "third"]


def test_non_exhaustive_container_and_space_reason_are_accepted() -> None:
    (rule,) = parse_rules([{**LAYERS, "container": "app", "reason": " "}])

    assert (rule.container, rule.exhaustive, rule.reason) == ("app", False, " ")


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        pytest.param(
            _without(_forbid(), "id"), "python.rules[1].id is required", id="no-id"
        ),
        pytest.param(
            _without(_forbid(), "kind"),
            "python.rules[1].kind is required",
            id="no-kind",
        ),
        pytest.param(
            _without(_forbid(), "reason"),
            "python.rules[1].reason is required",
            id="no-reason",
        ),
        pytest.param(
            _forbid(id="a" * 65),
            f"python.rules[1].id '{'a' * 65}' {KEBAB}",
            id="id-over-64",
        ),
        pytest.param(
            _forbid(id="No-db"), f"python.rules[1].id 'No-db' {KEBAB}", id="id-upper"
        ),
        pytest.param(
            _forbid(id="no_db"),
            f"python.rules[1].id 'no_db' {KEBAB}",
            id="id-underscore",
        ),
        pytest.param(
            _forbid(id="no:db"), f"python.rules[1].id 'no:db' {KEBAB}", id="id-colon"
        ),
        pytest.param(
            _forbid(id="no-db"),
            "python.rules[1].id 'no-db' duplicates python.rules[0].id",
            id="duplicate-id",
        ),
        pytest.param(
            _forbid(kind="allow"),
            "python.rules[1].kind 'allow' must be one of: forbid, layers",
            id="unknown-kind",
        ),
        pytest.param(
            _without(_forbid(), "targets"),
            "python.rules[1].targets is required",
            id="forbid-no-targets",
        ),
        pytest.param(
            _forbid(targets=[]),
            "python.rules[1].targets must not be empty",
            id="forbid-empty-targets",
        ),
        pytest.param(
            _forbid(targets=["shop.db", "a..b"]),
            "python.rules[1].targets[1] 'a..b' is not a valid selector",
            id="selector-empty-segment",
        ),
        pytest.param(
            _forbid(targets=["foo-bar"]),
            "python.rules[1].targets[0] 'foo-bar' is not a valid selector",
            id="selector-non-identifier",
        ),
        pytest.param(
            _forbid(sources=["shop.class"]),
            "python.rules[1].sources[0] 'shop.class' is not a valid selector",
            id="selector-keyword-segment",
        ),
        pytest.param(
            _forbid(sources=["shop.domain"], except_sources=["shop.api.x"]),
            "python.rules[1].except_sources[0] 'shop.api.x' "
            "must be a strict descendant of a sources entry",
            id="except-sources-not-descendant",
        ),
        pytest.param(
            _forbid(sources=["shop.domain"], except_sources=["shop.domain"]),
            "python.rules[1].except_sources[0] 'shop.domain' "
            "must be a strict descendant of a sources entry",
            id="except-sources-equal-to-source",
        ),
        pytest.param(
            _forbid(except_sources=["shop.domain.x"]),
            "python.rules[1].except_sources[0] 'shop.domain.x' "
            "must be a strict descendant of a sources entry",
            id="except-sources-without-sources",
        ),
        pytest.param(
            _forbid(except_targets=["shop.db.types", "shop.dbx"]),
            "python.rules[1].except_targets[1] 'shop.dbx' "
            "must be a strict descendant of a targets entry",
            id="except-targets-not-descendant",
        ),
        pytest.param(
            _forbid(sources=[]),
            "python.rules[1].sources must not be empty",
            id="empty-sources",
        ),
        pytest.param(
            _forbid(sources=["shop"], except_sources=[]),
            "python.rules[1].except_sources must not be empty",
            id="empty-except-sources",
        ),
        pytest.param(
            _forbid(except_targets=[]),
            "python.rules[1].except_targets must not be empty",
            id="empty-except-targets",
        ),
        pytest.param(
            _without(_layers(), "layers"),
            "python.rules[1].layers is required",
            id="layers-missing",
        ),
        pytest.param(
            _layers(layers=[]),
            "python.rules[1].layers must not be empty",
            id="layers-empty",
        ),
        pytest.param(
            _layers(layers=["a", "b", "a"]),
            "python.rules[1].layers[2] 'a' is declared more than once",
            id="layers-duplicate",
        ),
        pytest.param(
            _layers(layers=["a.b", "c", "a"]),
            "python.rules[1].layers[2] 'a' overlaps python.rules[1].layers[0] 'a.b'",
            id="layers-prefix",
        ),
        pytest.param(
            _layers(exhaustive=True),
            "python.rules[1].container is required when exhaustive = true",
            id="exhaustive-without-container",
        ),
        pytest.param(
            _layers(container="shop.api", exhaustive=True, layers=["shop.api.v1", "x"]),
            "python.rules[1].layers[1] 'x' "
            "must be a strict descendant of container 'shop.api'",
            id="layer-outside-container",
        ),
        pytest.param(
            _layers(container="shop", exhaustive=True, layers=["shop"]),
            "python.rules[1].layers[0] 'shop' "
            "must be a strict descendant of container 'shop'",
            id="layer-is-container",
        ),
        pytest.param(
            _forbid(severity="error"),
            f"python.rules[1].severity {NOT_SUPPORTED}",
            id="unknown-key",
        ),
        pytest.param(
            _forbid(zeta=1, exhaustive=False, container="shop"),
            f"python.rules[1].container {NOT_SUPPORTED}",
            id="forbid-rejects-layers-keys",
        ),
        pytest.param(
            _forbid(layers=["shop.api"]),
            f"python.rules[1].layers {NOT_SUPPORTED}",
            id="forbid-rejects-layers",
        ),
        pytest.param(
            _layers(targets=["shop.db"], sources=["shop"]),
            f"python.rules[1].sources {NOT_SUPPORTED}",
            id="layers-rejects-forbid-keys",
        ),
        pytest.param(
            _layers(except_targets=["shop.db.x"]),
            f"python.rules[1].except_targets {NOT_SUPPORTED}",
            id="layers-rejects-except-targets",
        ),
    ],
)
def test_rule_edge_case_rejected(entry: dict[str, object], message: str) -> None:
    assert _message([FORBID, entry]) == message


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (FORBID, "python.rules must be an array of tables"),
        ([FORBID, "x"], "python.rules must be an array of tables"),
        ([_forbid(kind=1)], "python.rules[0].kind must be a string"),
        ([_forbid(id=1)], "python.rules[0].id must be a string"),
        ([_forbid(reason=None)], "python.rules[0].reason must be a string"),
        ([_forbid(reason="")], "python.rules[0].reason must not be empty"),
        (
            [_forbid(targets="shop.db")],
            "python.rules[0].targets must be an array of strings",
        ),
        (
            [_forbid(sources=["a", 1])],
            "python.rules[0].sources must be an array of strings",
        ),
        (
            [_layers(layers=[["a"]])],
            "python.rules[0].layers must be an array of strings",
        ),
        ([_layers(container=["a"])], "python.rules[0].container must be a string"),
        ([_layers(exhaustive="true")], "python.rules[0].exhaustive must be a boolean"),
        (
            [_layers(container="a-b")],
            "python.rules[0].container 'a-b' is not a valid selector",
        ),
        (
            [_layers(layers=["a", ""])],
            "python.rules[0].layers[1] '' is not a valid selector",
        ),
    ],
)
def test_rule_shape_and_type_rejected(value: object, message: str) -> None:
    assert _message(value) == message


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        pytest.param(
            {"kind": "allow", "zeta": 1},
            "python.rules[1].kind 'allow' must be one of: forbid, layers",
            id="kind-before-unknown-keys",
        ),
        pytest.param(
            {"kind": "forbid", "zeta": 1, "beta": 2},
            f"python.rules[1].beta {NOT_SUPPORTED}",
            id="unknown-keys-before-required-sorted",
        ),
        pytest.param(
            {"kind": "forbid", "id": "BAD", "reason": "r"},
            "python.rules[1].targets is required",
            id="required-before-id-grammar",
        ),
        pytest.param(
            _forbid(id="BAD", targets=1),
            "python.rules[1].targets must be an array of strings",
            id="types-before-id-grammar",
        ),
        pytest.param(
            _forbid(id="NO-DB", reason=""),
            f"python.rules[1].id 'NO-DB' {KEBAB}",
            id="id-grammar-before-reason",
        ),
        pytest.param(
            _forbid(id="no-db", reason="", targets=["a-b"]),
            "python.rules[1].id 'no-db' duplicates python.rules[0].id",
            id="uniqueness-before-reason",
        ),
        pytest.param(
            _forbid(reason="", targets=["a-b"]),
            "python.rules[1].reason must not be empty",
            id="reason-before-selectors",
        ),
        pytest.param(
            _forbid(except_targets=["shop.x"], sources=["a..b"]),
            "python.rules[1].sources[0] 'a..b' is not a valid selector",
            id="selectors-before-structure",
        ),
        pytest.param(
            _layers(layers=["a", "a.b", "a"], container="1x", exhaustive=True),
            "python.rules[1].container '1x' is not a valid selector",
            id="container-syntax-before-structure",
        ),
        pytest.param(
            _layers(layers=["a", "a", "a.b"]),
            "python.rules[1].layers[2] 'a.b' overlaps python.rules[1].layers[0] 'a'",
            id="prefix-before-duplicate",
        ),
        pytest.param(
            _layers(layers=["a", "a"], exhaustive=True),
            "python.rules[1].layers[1] 'a' is declared more than once",
            id="duplicate-before-container",
        ),
    ],
)
def test_rule_checks_run_in_contract_order(
    entry: dict[str, object], message: str
) -> None:
    assert _message([FORBID, entry]) == message


def test_first_failing_entry_is_reported_alone() -> None:
    message = _message([FORBID, _forbid(targets=[]), _without(_forbid(), "kind")])

    assert message == "python.rules[1].targets must not be empty"


def test_selectors_naming_no_module_load_without_filesystem_access(
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

    rules = parse_rules(
        [
            {
                **FORBID,
                "targets": ["nowhere.missing"],
                "sources": ["ghost"],
                "except_sources": ["ghost.inner"],
            },
            {**LAYERS, "layers": ["void.a", "void.b"], "container": "void"},
        ]
    )

    assert calls == []
    assert [r.id for r in rules] == ["no-db", "layering"]


def test_rules_imports_only_stdlib_validate_and_diagnostics() -> None:
    tree = ast.parse(RULES_SOURCE.read_bytes())
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
