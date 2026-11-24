from dataclasses import dataclass
from typing import Literal

from dogwatch.diagnostics import Diagnostic

ContractSide = Literal["base", "candidate"]


@dataclass(frozen=True)
class BaselineReference:
    supplied_ref: str
    resolved_commit: str


@dataclass(frozen=True)
class ValidatedContractInput:
    side: ContractSide
    path: str
    raw_bytes: bytes
    raw_sha256: str
    canonical_json: bytes
    openapi_version: str


@dataclass(frozen=True)
class PreflightResult:
    input: ValidatedContractInput | None
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class ValidatedInputsResult:
    inputs: tuple[ValidatedContractInput, ValidatedContractInput] | None
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class BaselineResolution:
    reference: BaselineReference | None
    diagnostics: tuple[Diagnostic, ...]
