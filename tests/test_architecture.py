"""Architecture rules asserted in the test suite.

``lint-imports`` is the primary gate for the module-boundary and layering rules. These tests add
the checks a dependency analyser cannot express -- source-level and route-level properties -- so
a regression fails the suite as well as the linter.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.shared.errors import AppError

MODULES = ("activities", "programmes", "staff", "alerts", "reports")
APP_ROOT = Path(__file__).resolve().parent.parent / "app"


def _imported_modules(source_path: Path) -> set[str]:
    """Every module named by an ``import`` or ``from ... import`` in a file."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("module", MODULES)
def test_routes_never_import_a_repository(module: str) -> None:
    """HG-5 / Failure Mode 1. Business logic in a route is untestable below HTTP and cannot be
    reused by an event handler."""
    imports = _imported_modules(APP_ROOT / module / "routes.py")

    offending = {name for name in imports if name.endswith(".repository")}
    assert offending == set(), f"app/{module}/routes.py imports {sorted(offending)}"


@pytest.mark.parametrize("module", MODULES)
def test_no_module_imports_a_sibling_repository(module: str) -> None:
    """HG-1 / Failure Mode 1. Cross-module reads go through the sibling's service layer."""
    siblings = [other for other in MODULES if other != module]
    forbidden = {f"app.{other}.repository" for other in siblings}

    for source_path in (APP_ROOT / module).glob("*.py"):
        offending = _imported_modules(source_path) & forbidden
        assert offending == set(), f"{source_path.name} in {module} imports {sorted(offending)}"


@pytest.mark.parametrize("module", MODULES)
def test_repositories_do_not_import_services(module: str) -> None:
    """PDF section 3.5: repositories must not call external services."""
    imports = _imported_modules(APP_ROOT / module / "repository.py")

    offending = {name for name in imports if name.endswith(".service")}
    assert offending == set(), f"app/{module}/repository.py imports {sorted(offending)}"


def test_shared_does_not_import_any_business_module() -> None:
    """``app.shared`` is infrastructure. If it depended on a domain, the event bus would know
    about the modules it exists to decouple."""
    forbidden = {f"app.{module}" for module in MODULES}

    for source_path in (APP_ROOT / "shared").glob("*.py"):
        imports = _imported_modules(source_path)
        offending = {
            name
            for name in imports
            if name in forbidden or any(name.startswith(f"{item}.") for item in forbidden)
        }
        assert offending == set(), f"app/shared/{source_path.name} imports {sorted(offending)}"


def test_shared_owns_no_router() -> None:
    """Infrastructure must not acquire an HTTP surface, which is what would turn it into a
    sixth business module."""
    for source_path in (APP_ROOT / "shared").glob("*.py"):
        assert "APIRouter" not in source_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("module", MODULES)
def test_every_module_has_all_three_layers(module: str) -> None:
    for layer in ("routes.py", "service.py", "repository.py", "models.py"):
        assert (APP_ROOT / module / layer).is_file(), f"app/{module}/{layer} is missing"


@pytest.mark.parametrize("module", MODULES)
def test_services_raise_no_bare_exceptions(module: str) -> None:
    """HG-2 / Failure Mode 2, at source level: every raise in a service must name an AppError
    subclass, not a builtin."""
    banned = {"Exception", "ValueError", "RuntimeError", "KeyError", "TypeError", "HTTPException"}
    tree = ast.parse((APP_ROOT / module / "service.py").read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        call = node.exc
        raised = call.func if isinstance(call, ast.Call) else call
        name = raised.id if isinstance(raised, ast.Name) else getattr(raised, "attr", "")
        assert name not in banned, f"app/{module}/service.py raises {name}"


def test_every_app_error_subclass_declares_a_distinct_code() -> None:
    """Duplicate codes would make a client's error handling ambiguous."""

    def descendants(cls: type[AppError]) -> list[type[AppError]]:
        found: list[type[AppError]] = []
        for sub in cls.__subclasses__():
            found.append(sub)
            found.extend(descendants(sub))
        return found

    subclasses = descendants(AppError)
    codes = [sub.code for sub in subclasses]

    assert len(codes) == len(set(codes)), f"duplicate AppError codes: {sorted(codes)}"
    for sub in subclasses:
        assert 400 <= sub.status_code <= 599, f"{sub.__name__} has status {sub.status_code}"
