from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dogwatch._validate import (
    config_invalid,
    is_kebab_id,
    key_path,
    require_str,
    table_array,
)

_CONTRACTS = "openapi.contracts"
_EXTENSIONS = (".yaml", ".yml", ".json")


@dataclass(frozen=True)
class OpenApiContractDecl:
    id: str
    path: str


def parse_contracts(value: object) -> tuple[OpenApiContractDecl, ...]:
    if value is None:
        return ()
    contracts: list[OpenApiContractDecl] = []
    for index, entry in enumerate(table_array(value, _CONTRACTS)):
        contracts.append(_contract(key_path(_CONTRACTS, index), entry, contracts))
    return tuple(contracts)


def _contract(
    path: str, entry: Mapping[str, object], earlier: Sequence[OpenApiContractDecl]
) -> OpenApiContractDecl:
    contract_id = require_str(entry, path, "id")
    if not is_kebab_id(contract_id):
        raise config_invalid(
            f"{key_path(path, 'id')} '{contract_id}' must be kebab-case "
            "([a-z][a-z0-9]*(-[a-z0-9]+)*) and at most 64 characters"
        )
    for index, other in enumerate(earlier):
        if other.id == contract_id:
            raise config_invalid(
                f"{key_path(path, 'id')} '{contract_id}' duplicates "
                f"{key_path(_CONTRACTS, index, 'id')}"
            )

    contract_path = require_str(entry, path, "path")
    constraint = _syntax_violation(contract_path)
    if constraint is not None:
        raise config_invalid(f"{key_path(path, 'path')} '{contract_path}' {constraint}")
    for index, other in enumerate(earlier):
        if other.path == contract_path:
            raise config_invalid(
                f"{key_path(path, 'path')} '{contract_path}' duplicates "
                f"{key_path(_CONTRACTS, index, 'path')}"
            )
    return OpenApiContractDecl(id=contract_id, path=contract_path)


def _syntax_violation(path: str) -> str | None:
    if path.startswith("/"):
        return "must be relative"
    if any(segment in ("", ".", "..") for segment in path.split("/")):
        return "must not contain '.', '..' or empty segments"
    if "\\" in path:
        return "must use '/' separators"
    if not path.endswith(_EXTENSIONS):
        return "must end in .yaml, .yml or .json"
    return None
