import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from urllib.parse import unquote_to_bytes

import yaml
from yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent

from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Diagnostic
from dogwatch.openapi.model import (
    ContractSide,
    PreflightResult,
    ValidatedContractInput,
    ValidatedInputsResult,
)

MAX_RAW_BYTES = 5 * 1024 * 1024
MAX_YAML_NESTING = 100
_OPENAPI_VERSION = re.compile(r"3\.(?:0|1|2)\.[0-9]+\Z")


class _SafeContractLoader(yaml.SafeLoader):
    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[object, object]:
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as error:
                raise yaml.constructor.ConstructorError(
                    None, None, "unhashable mapping key", key_node.start_mark
                ) from error
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate mapping key {key!r}", key_node.start_mark
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def preflight_candidate(
    candidate_root: Path,
    declaration: OpenApiContractDecl,
    *,
    side: ContractSide = "candidate",
) -> PreflightResult:
    if not valid_contract_path(declaration.path):
        return _invalid(side, declaration.path, "invalid relative contract path")
    try:
        raw_bytes = _read_regular_file(candidate_root, declaration.path)
    except OSError as error:
        return _invalid(
            side,
            declaration.path,
            f"cannot read regular contract file: {error.strerror}",
        )
    return preflight_bytes(side, declaration, raw_bytes)


def preflight_bytes(
    side: ContractSide, declaration: OpenApiContractDecl, raw_bytes: bytes
) -> PreflightResult:
    if not valid_contract_path(declaration.path):
        return _invalid(side, declaration.path, "invalid relative contract path")
    if len(raw_bytes) > MAX_RAW_BYTES:
        return _invalid(
            side, declaration.path, "contract exceeds the 5 MiB raw-byte limit"
        )
    try:
        document = _load_document(declaration.path, raw_bytes)
        version = _validate_document(document)
        _validate_references(document, document)
        canonical_json = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
        UnicodeDecodeError,
        RecursionError,
    ) as error:
        return _invalid(side, declaration.path, str(error))

    return PreflightResult(
        ValidatedContractInput(
            side=side,
            path=declaration.path,
            raw_bytes=raw_bytes,
            raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            canonical_json=canonical_json,
            openapi_version=version,
        ),
        (),
    )


def preflight_pair(
    candidate: PreflightResult, baseline: PreflightResult
) -> ValidatedInputsResult:
    diagnostics = candidate.diagnostics + baseline.diagnostics
    if candidate.input is None or baseline.input is None:
        return ValidatedInputsResult(None, diagnostics)
    return ValidatedInputsResult((candidate.input, baseline.input), diagnostics)


def input_diagnostic(side: ContractSide, path: str, message: str) -> PreflightResult:
    return _invalid(side, path, message)


def valid_contract_path(path: str) -> bool:
    return (
        not path.startswith("/")
        and "\\" not in path
        and "\x00" not in path
        and all(segment not in {"", ".", ".."} for segment in path.split("/"))
        and path.endswith((".yaml", ".yml", ".json"))
    )


def _read_regular_file(root: Path, relative_path: str) -> bytes:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(root, directory_flags)
    try:
        segments = relative_path.split("/")
        for segment in segments[:-1]:
            next_directory = os.open(segment, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        descriptor = os.open(
            segments[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("contract path is not a regular file")
            chunks: list[bytes] = []
            remaining = MAX_RAW_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)


def _load_document(path: str, raw_bytes: bytes) -> object:
    if path.endswith(".json"):
        return json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_json_object)
    _validate_yaml_events(raw_bytes)
    return yaml.load(raw_bytes, Loader=_SafeContractLoader)


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _validate_yaml_events(raw_bytes: bytes) -> None:
    depth = 0
    for event in yaml.parse(raw_bytes, Loader=yaml.SafeLoader):
        if isinstance(event, AliasEvent):
            raise ValueError("YAML aliases are not supported")
        if isinstance(event, CollectionStartEvent):
            depth += 1
            if depth > MAX_YAML_NESTING:
                raise ValueError(f"YAML nesting exceeds {MAX_YAML_NESTING} levels")
        elif isinstance(event, CollectionEndEvent):
            depth -= 1


def _validate_document(document: object) -> str:
    _validate_json_values(document)
    if not isinstance(document, dict):
        raise ValueError("OpenAPI document must be an object")
    version = document.get("openapi")
    if not isinstance(version, str) or _OPENAPI_VERSION.fullmatch(version) is None:
        raise ValueError("OpenAPI version must be 3.0.x, 3.1.x, or 3.2.x")
    return version


def _validate_json_values(value: object, depth: int = 0) -> None:
    if depth > MAX_YAML_NESTING:
        raise ValueError(f"document nesting exceeds {MAX_YAML_NESTING} levels")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("document contains a non-finite number")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("document object keys must be strings")
        for item in value.values():
            _validate_json_values(item, depth + 1)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_values(item, depth + 1)
        return
    raise ValueError("document contains a value that cannot be represented as JSON")


def _validate_references(value: object, document: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref":
                if not isinstance(item, str) or not item.startswith("#"):
                    raise ValueError(
                        "OpenAPI $ref values must be internal JSON pointers"
                    )
                _resolve_json_pointer(document, item)
            _validate_references(item, document)
    elif isinstance(value, list):
        for item in value:
            _validate_references(item, document)


def _resolve_json_pointer(document: object, reference: str) -> None:
    if reference == "#":
        return
    try:
        pointer = unquote_to_bytes(reference[1:]).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid internal OpenAPI $ref {reference!r}") from error
    if not pointer.startswith("/"):
        raise ValueError(f"invalid internal OpenAPI $ref {reference!r}")
    target = document
    for raw_segment in pointer[1:].split("/"):
        segment = _unescape_pointer_segment(raw_segment)
        if isinstance(target, dict):
            if segment not in target:
                raise ValueError(f"unresolved internal OpenAPI $ref {reference!r}")
            target = target[segment]
        elif isinstance(target, list):
            if not segment.isdecimal() or (
                len(segment) > 1 and segment.startswith("0")
            ):
                raise ValueError(f"unresolved internal OpenAPI $ref {reference!r}")
            index = int(segment)
            if index >= len(target):
                raise ValueError(f"unresolved internal OpenAPI $ref {reference!r}")
            target = target[index]
        else:
            raise ValueError(f"unresolved internal OpenAPI $ref {reference!r}")


def _unescape_pointer_segment(segment: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        if char != "~":
            result.append(char)
            index += 1
            continue
        if index + 1 == len(segment) or segment[index + 1] not in "01":
            raise ValueError("invalid JSON pointer escape")
        result.append("~" if segment[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def _invalid(side: ContractSide, path: str, message: str) -> PreflightResult:
    return PreflightResult(
        None,
        (
            Diagnostic(
                "openapi", "openapi-input-invalid", "error", f"{side} {path}: {message}"
            ),
        ),
    )
