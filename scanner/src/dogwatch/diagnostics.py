from dataclasses import dataclass
from typing import Final, Literal

DiagnosticId = Literal["config-invalid", "config-not-found"]

EXIT_OK: Final = 0
EXIT_GATE_FAILED: Final = 1  # reserved, never emitted in CD-5
EXIT_ERROR: Final = 2


@dataclass(frozen=True)
class Diagnostic:
    id: DiagnosticId
    message: str


class DogwatchError(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("DogwatchError requires at least one diagnostic")
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


def render(err: DogwatchError) -> str:
    return "\n".join(f"dogwatch:{d.id}: {d.message}" for d in err.diagnostics) + "\n"
