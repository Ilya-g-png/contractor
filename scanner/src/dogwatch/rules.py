from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

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

RuleKind = Literal["forbid", "layers"]

_RULES = "python.rules"
_COMMON_KEYS = frozenset({"id", "kind", "reason"})
_KEYS = {
    "forbid": _COMMON_KEYS | {"targets", "sources", "except_sources", "except_targets"},
    "layers": _COMMON_KEYS | {"layers", "container", "exhaustive"},
}


@dataclass(frozen=True)
class RuleDecl:
    id: str
    kind: RuleKind
    reason: str
    targets: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    except_sources: tuple[str, ...] = ()
    except_targets: tuple[str, ...] = ()
    layers: tuple[str, ...] = ()
    container: str | None = None
    exhaustive: bool = False


def parse_rules(value: object) -> tuple[RuleDecl, ...]:
    if value is None:
        return ()
    rules: list[RuleDecl] = []
    for index, entry in enumerate(table_array(value, _RULES)):
        rules.append(_rule(key_path(_RULES, index), entry, rules))
    return tuple(rules)


def _rule(
    path: str, entry: Mapping[str, object], earlier: Sequence[RuleDecl]
) -> RuleDecl:
    kind = require_str(entry, path, "kind")
    if kind not in _KEYS:
        raise config_invalid(
            f"{key_path(path, 'kind')} '{kind}' must be one of: forbid, layers"
        )
    unknown = sorted(entry.keys() - _KEYS[kind])
    if unknown:
        raise config_invalid(
            f"{key_path(path, unknown[0])} is not supported in this version"
        )

    rule = _forbid(path, entry) if kind == "forbid" else _layers(path, entry)

    if not is_kebab_id(rule.id):
        raise config_invalid(
            f"{key_path(path, 'id')} '{rule.id}' must be kebab-case "
            "([a-z][a-z0-9]*(-[a-z0-9]+)*) and at most 64 characters"
        )
    for index, other in enumerate(earlier):
        if other.id == rule.id:
            raise config_invalid(
                f"{key_path(path, 'id')} '{rule.id}' duplicates "
                f"{key_path(_RULES, index, 'id')}"
            )
    if not rule.reason:
        raise config_invalid(f"{key_path(path, 'reason')} must not be empty")

    _check_selectors(path, rule)
    _check_descendants(
        path, "except_sources", rule.except_sources, "sources", rule.sources
    )
    _check_descendants(
        path, "except_targets", rule.except_targets, "targets", rule.targets
    )
    _check_layers(path, rule)
    return rule


def _forbid(path: str, entry: Mapping[str, object]) -> RuleDecl:
    return RuleDecl(
        id=require_str(entry, path, "id"),
        kind="forbid",
        reason=require_str(entry, path, "reason"),
        targets=_non_empty(entry, path, "targets", required=True),
        sources=_non_empty(entry, path, "sources"),
        except_sources=_non_empty(entry, path, "except_sources"),
        except_targets=_non_empty(entry, path, "except_targets"),
    )


def _layers(path: str, entry: Mapping[str, object]) -> RuleDecl:
    return RuleDecl(
        id=require_str(entry, path, "id"),
        kind="layers",
        reason=require_str(entry, path, "reason"),
        layers=_non_empty(entry, path, "layers", required=True),
        container=optional_str(entry, path, "container"),
        exhaustive=optional_bool(entry, path, "exhaustive") or False,
    )


def _non_empty(
    entry: Mapping[str, object], path: str, key: str, *, required: bool = False
) -> tuple[str, ...]:
    value = (
        require_str_list(entry, path, key)
        if required
        else optional_str_list(entry, path, key)
    )
    if value is None:
        return ()
    if not value:
        raise config_invalid(f"{key_path(path, key)} must not be empty")
    return value


def _is_selector(value: str) -> bool:
    return all(is_identifier(segment) for segment in value.split("."))


def _is_descendant(selector: str, ancestor: str) -> bool:
    return selector.startswith(ancestor + ".")


def _check_selectors(path: str, rule: RuleDecl) -> None:
    for key, selectors in (
        ("targets", rule.targets),
        ("sources", rule.sources),
        ("except_sources", rule.except_sources),
        ("except_targets", rule.except_targets),
        ("layers", rule.layers),
    ):
        for index, selector in enumerate(selectors):
            if not _is_selector(selector):
                raise config_invalid(
                    f"{key_path(path, key, index)} '{selector}' is not a valid selector"
                )
    if rule.container is not None and not _is_selector(rule.container):
        raise config_invalid(
            f"{key_path(path, 'container')} '{rule.container}' is not a valid selector"
        )


def _check_descendants(
    path: str,
    key: str,
    selectors: tuple[str, ...],
    scope_key: str,
    scope: tuple[str, ...],
) -> None:
    for index, selector in enumerate(selectors):
        if not any(_is_descendant(selector, ancestor) for ancestor in scope):
            raise config_invalid(
                f"{key_path(path, key, index)} '{selector}' "
                f"must be a strict descendant of a {scope_key} entry"
            )


def _check_layers(path: str, rule: RuleDecl) -> None:
    layers = rule.layers
    for later, layer in enumerate(layers):
        for index, other in enumerate(layers[:later]):
            if _is_descendant(layer, other) or _is_descendant(other, layer):
                raise config_invalid(
                    f"{key_path(path, 'layers', later)} '{layer}' overlaps "
                    f"{key_path(path, 'layers', index)} '{other}'"
                )
    for later, layer in enumerate(layers):
        if layer in layers[:later]:
            raise config_invalid(
                f"{key_path(path, 'layers', later)} '{layer}' "
                "is declared more than once"
            )
    if not rule.exhaustive:
        return
    if rule.container is None:
        raise config_invalid(
            f"{key_path(path, 'container')} is required when exhaustive = true"
        )
    for index, layer in enumerate(layers):
        if not _is_descendant(layer, rule.container):
            raise config_invalid(
                f"{key_path(path, 'layers', index)} '{layer}' "
                f"must be a strict descendant of container '{rule.container}'"
            )
