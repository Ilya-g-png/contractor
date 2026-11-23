from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

Severity = Literal["error", "warning", "info"]

CONFIG_NOT_FOUND: Final[str] = "config-not-found"
CONFIG_INVALID: Final[str] = "config-invalid"
EXCLUDE_UNMATCHED: Final[str] = "exclude-unmatched"
SOURCE_SYNTAX_INVALID: Final[str] = "source-syntax-invalid"

EXIT_OK: Final = 0
EXIT_GATE_FAILED: Final = 1  # emitted when the report status is "fail"
EXIT_ERROR: Final = 2


@dataclass(frozen=True)
class Diagnostic:
    source: str
    id: str
    severity: Severity
    message: str


class DogwatchError(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("DogwatchError requires at least one diagnostic")
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


def render_diagnostics(diagnostics: Sequence[Diagnostic]) -> str:
    return "".join(f"dogwatch:{d.id}: {d.message}\n" for d in diagnostics)


def render(err: DogwatchError) -> str:
    return render_diagnostics(err.diagnostics)
