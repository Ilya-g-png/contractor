from dataclasses import dataclass
from typing import Literal

RuleKind = Literal["forbid", "layers"]


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
