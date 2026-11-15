from dataclasses import dataclass


@dataclass(frozen=True)
class OpenApiContractDecl:
    id: str
    path: str
