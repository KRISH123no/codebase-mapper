"""Reading a Python project into modules and the edges between them.

`ast` only. It ships with Python, it cannot execute the code it reads, and it
is exact about what the file literally imports — which matters, because the
alternative is importing the project to inspect it, and importing a stranger's
project runs their code.

What it cannot see: imports built from strings, plugin registries, dependency
injection, anything resolved at runtime. That is a real limit and the README
says so rather than pretending the graph is complete.
"""

from __future__ import annotations

import ast
import os
import warnings
from dataclasses import dataclass
from pathlib import Path

from .model import Module

SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "env", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "build", "dist", "node_modules", "site-packages",
})

#: Names that mark a class as something to implement against rather than edit.
ABSTRACT_BASES = frozenset({"ABC", "ABCMeta", "Protocol", "Generic"})
ABSTRACT_DECORATORS = frozenset({"abstractmethod", "abstractproperty"})


@dataclass(slots=True)
class Project:
    root: str
    modules: dict[str, Module]
    #: Files that failed to parse — a syntax error, or Python too new.
    unreadable: list[str]

    @property
    def source(self) -> dict[str, Module]:
        """Everything that is not a test. Tests depend on the code; counting
        them inflates fan-in and makes the most-tested module look central."""
        return {n: m for n, m in self.modules.items() if not m.is_test}


def module_name(path: Path, root: Path) -> tuple[str, bool]:
    """`src/pkg/thing.py` under `src` -> `("pkg.thing", False)`.

    The flag says whether this file *is* a package rather than living in one,
    which decides what a relative import means: inside `pkg/__init__.py`,
    `from . import x` means `pkg.x`, but inside `pkg/mod.py` it means the
    same thing — because the package of `pkg.mod` is `pkg`, not `pkg.mod`.
    """
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    is_package = bool(parts) and parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def looks_like_test(name: str, path: str) -> bool:
    last = name.rsplit(".", 1)[-1]
    return (
        last.startswith("test_")
        or last.endswith("_test")
        or "tests" in Path(path).parts
        or last == "conftest"
    )


def parse(root: str | Path) -> Project:
    root = Path(root).expanduser().resolve()
    modules: dict[str, Module] = {}
    unreadable: list[str] = []

    for folder, subdirs, files in os.walk(root):
        subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = Path(folder) / name
            try:
                text = path.read_text(encoding="utf-8")
                with warnings.catch_warnings():
                    # A file with a stray backslash in a docstring warns on
                    # parse. That is the project's business, not ours.
                    warnings.simplefilter("ignore")
                    tree = ast.parse(text)
            except (OSError, SyntaxError, ValueError):
                unreadable.append(str(path))
                continue

            dotted, is_package = module_name(path, root)
            if not dotted:
                continue
            # The package a relative import is counted from.
            package = dotted if is_package else dotted.rpartition(".")[0]
            module = Module(
                name=dotted,
                path=str(path),
                lines=text.count("\n") + 1,
                is_test=looks_like_test(dotted, str(path)),
            )
            _walk(tree, module, package)
            modules[dotted] = module

    _resolve(modules)
    return Project(root=str(root), modules=modules, unreadable=unreadable)


def _walk(tree: ast.Module, module: Module, package: str) -> None:
    """Descend the tree, remembering whether we are still at import time.

    `ast.walk` flattens everything, which treats

        if TYPE_CHECKING:
            from .app import Flask

    exactly like a module-level import. It is not one: nothing is imported at
    run time, and the author wrote it that way *because* there is a cycle.
    Counting it as a dependency turns every mature project into one enormous
    circular cluster — Flask came out as 20 of its 35 modules.
    """
    hard: list[tuple[str, tuple[str, ...]]] = []
    soft: list[tuple[str, tuple[str, ...]]] = []

    def visit(node: ast.AST, deferred: bool) -> None:
        bucket = soft if deferred else hard
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                bucket.extend((alias.name, ()) for alias in child.names)
            elif isinstance(child, ast.ImportFrom):
                bucket.append((_from_target(child, package),
                               tuple(a.name for a in child.names)))
                continue
            elif isinstance(child, ast.ClassDef):
                module.classes += 1
                if _is_abstract(child):
                    module.abstract_classes += 1
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                module.functions += 1
                visit(child, True)  # a body that runs later, if at all
                continue
            elif isinstance(child, ast.If) and _is_type_checking(child.test):
                for item in child.body:
                    visit(ast.Module(body=[item], type_ignores=[]), True)
                for item in child.orelse:
                    visit(ast.Module(body=[item], type_ignores=[]), deferred)
                continue
            visit(child, deferred)

    visit(tree, False)
    module.raw = [(base, names) for base, names in hard if base]
    module.raw_deferred = [(base, names) for base, names in soft if base]


def _from_target(node: ast.ImportFrom, package: str) -> str:
    """Turn `from . import x` and `from ..a import b` into an absolute name.

    One dot means the module's own package, two means its parent, and so on —
    so the dots are counted off the *package*, never off the module. Counting
    them off the module turns `from .volume import run` inside `pkg.memory`
    into `pkg.memory.volume`, which does not exist, and every edge disappears.
    """
    if not node.level:
        return node.module or ""
    parts = package.split(".") if package else []
    drop = node.level - 1
    base = parts[: len(parts) - drop] if drop <= len(parts) else []
    if node.module:
        base = [*base, *node.module.split(".")]
    return ".".join(base)


def _is_type_checking(test: ast.expr) -> bool:
    """`if TYPE_CHECKING:` in any of the spellings people use."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _is_abstract(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        if name in ABSTRACT_BASES:
            return True
    for item in node.body:
        if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in item.decorator_list:
            label = (
                decorator.id if isinstance(decorator, ast.Name)
                else getattr(decorator, "attr", "")
            )
            if label in ABSTRACT_DECORATORS:
                return True
    return False


def _resolve(modules: dict[str, Module]) -> None:
    """Turn each import statement into the most specific module it reaches.

    `from . import sessions` names the package, and `sessions` is a name taken
    out of it — but if `pkg.sessions` is itself a module then *that* is what
    the file depends on, not the package. Recording the package instead gives
    every submodule an edge back to `__init__`, and a package that re-exports
    its contents then appears to be one enormous dependency cycle. On requests
    that invented an eleven-module cycle out of nothing.

    So the specific name wins when it is a module, and the base is the
    fallback for `from .compat import urlparse`, where the name is a function.
    """
    known = set(modules)
    for module in modules.values():
        module.imports = _edges(module.raw, known, module.name)
        module.deferred = _edges(module.raw_deferred, known, module.name) - module.imports


def _edges(raw: list[tuple[str, tuple[str, ...]]], known: set[str], self_name: str) -> set[str]:
    edges: set[str] = set()
    for base, names in raw:
        specific = {f"{base}.{name}" for name in names} & known
        if specific:
            edges |= specific
            continue
        if base in known:
            edges.add(base)
            continue
        # `a.b.c` may be an attribute of module `a.b`.
        parent = base.rsplit(".", 1)[0]
        if parent in known:
            edges.add(parent)
    edges.discard(self_name)
    return edges
