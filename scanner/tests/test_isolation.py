import ast
import sys
import tomllib
from pathlib import Path

SCANNER = Path(__file__).resolve().parents[1]


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def test_src_imports_only_stdlib_or_dogwatch() -> None:
    sources = sorted((SCANNER / "src").rglob("*.py"))
    assert sources

    offending = [
        f"{path.relative_to(SCANNER)}: {name}"
        for path in sources
        for name in _imported_modules(path)
        if name.partition(".")[0] not in sys.stdlib_module_names
        and name.partition(".")[0] != "dogwatch"
    ]

    assert offending == []


def test_no_runtime_dependencies() -> None:
    pyproject = tomllib.loads((SCANNER / "pyproject.toml").read_text("utf-8"))

    assert pyproject["project"]["dependencies"] == []
