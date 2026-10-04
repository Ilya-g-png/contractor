import ast
import re
import tomllib
from pathlib import Path
from typing import Any

SCANNER_PACKAGE = "dogwatch"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def _pyproject(api_root: Path) -> dict[str, Any]:
    return tomllib.loads((api_root / "pyproject.toml").read_text("utf-8"))


def _requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9._-]+", requirement)
    assert match is not None, requirement
    return match.group(0).lower()


def test_src_does_not_import_scanner(api_root: Path) -> None:
    sources = sorted((api_root / "src").rglob("*.py"))
    assert sources

    offending = [
        f"{path.relative_to(api_root)}: {name}"
        for path in sources
        for name in _imported_modules(path)
        if name.partition(".")[0] == SCANNER_PACKAGE
    ]

    assert offending == []


def test_runtime_dependencies_are_exactly_fastapi_and_uvicorn(api_root: Path) -> None:
    dependencies: list[str] = _pyproject(api_root)["project"]["dependencies"]

    assert sorted(_requirement_name(d) for d in dependencies) == ["fastapi", "uvicorn"]
    assert not any("[" in d for d in dependencies)


def test_no_dependency_on_scanner(api_root: Path) -> None:
    pyproject = _pyproject(api_root)
    groups: dict[str, list[str]] = pyproject["dependency-groups"]
    requirements = [*pyproject["project"]["dependencies"]]
    for group in groups.values():
        requirements.extend(group)

    assert SCANNER_PACKAGE not in {_requirement_name(r) for r in requirements}
    assert "sources" not in pyproject.get("tool", {}).get("uv", {})
