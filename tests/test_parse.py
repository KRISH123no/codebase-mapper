"""Reading Python into modules and edges. The relative-import rules are the
whole difficulty."""

import pytest
from conftest import project

from codebase_mapper.parse import looks_like_test, module_name, parse


def edges(root):
    return {n: sorted(m.imports) for n, m in parse(root).source.items()}


def test_modules_are_found(tiny):
    found = parse(tiny).source
    assert set(found) == {"pkg", "pkg.api", "pkg.store", "pkg.model"}


def test_tests_are_separated_from_the_code(tiny):
    everything = parse(tiny).modules
    assert "tests.test_api" in everything
    assert "tests.test_api" not in parse(tiny).source


def test_a_sibling_import_points_at_the_sibling(tmp_path):
    """`from .b import x` inside `pkg.a` is `pkg.b`, not `pkg.a.b`."""
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from .b import x\n", "pkg/b.py": "x = 1\n"})
    assert edges(tmp_path)["pkg.a"] == ["pkg.b"]


def test_importing_a_name_out_of_the_package_points_at_the_module(tmp_path):
    """`from . import b` depends on `pkg.b`, not on `pkg`.

    Recording the package gives every submodule an edge back to __init__ and
    manufactures a cycle across the whole project.
    """
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from . import b\n", "pkg/b.py": "x = 1\n"})
    assert edges(tmp_path)["pkg.a"] == ["pkg.b"]


def test_importing_a_function_falls_back_to_its_module(tmp_path):
    project(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "from .util import helper\n",
        "pkg/util.py": "def helper(): pass\n",
    })
    assert edges(tmp_path)["pkg.a"] == ["pkg.util"]


def test_a_parent_package_import(tmp_path):
    """`from ..shared import x` inside `pkg.sub.a` is `pkg.shared`."""
    project(tmp_path, {
        "pkg/__init__.py": "", "pkg/shared.py": "x = 1\n",
        "pkg/sub/__init__.py": "", "pkg/sub/a.py": "from ..shared import x\n",
    })
    assert edges(tmp_path)["pkg.sub.a"] == ["pkg.shared"]


def test_an_absolute_internal_import_counts(tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "import pkg.b\n", "pkg/b.py": "x = 1\n"})
    assert edges(tmp_path)["pkg.a"] == ["pkg.b"]


def test_external_packages_are_not_edges(tmp_path):
    """You cannot refactor requests, so it is not part of your shape."""
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "import os\nimport requests\n"})
    assert edges(tmp_path)["pkg.a"] == []


def test_a_module_never_depends_on_itself(tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from pkg import a\n"})
    assert edges(tmp_path)["pkg.a"] == []


def test_a_file_that_will_not_parse_is_reported_not_fatal(tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/ok.py": "x = 1\n", "pkg/bad.py": "def (\n"})
    found = parse(tmp_path)
    assert "pkg.ok" in found.modules and len(found.unreadable) == 1


def test_virtualenvs_and_caches_are_skipped(tmp_path):
    project(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "x = 1\n",
        ".venv/lib/thing.py": "x = 1\n", "__pycache__/junk.py": "x = 1\n",
    })
    assert set(parse(tmp_path).source) == {"pkg", "pkg.a"}


# ------------------------------------------------------------- abstractness


def test_a_class_inheriting_abc_is_abstract(tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from abc import ABC\nclass X(ABC):\n    pass\n"})
    assert parse(tmp_path).source["pkg.a"].abstractness == 1.0


def test_a_protocol_counts_as_abstract(tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from typing import Protocol\nclass X(Protocol):\n    pass\n"})
    assert parse(tmp_path).source["pkg.a"].abstractness == 1.0


def test_an_abstractmethod_makes_the_class_abstract(tmp_path):
    project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from abc import abstractmethod\nclass X:\n    @abstractmethod\n    def f(self): ...\n",
    })
    assert parse(tmp_path).source["pkg.a"].abstractness == 1.0


def test_a_plain_class_is_concrete(tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "class X:\n    pass\n"})
    assert parse(tmp_path).source["pkg.a"].abstractness == 0.0


def test_a_module_with_no_classes_is_concrete(tmp_path):
    """A file of plain functions is something you edit, not implement against."""
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "def f(): pass\n"})
    assert parse(tmp_path).source["pkg.a"].abstractness == 0.0


# ------------------------------------------------------------------ naming


@pytest.mark.parametrize(
    "relative,expected,is_package",
    [("pkg/a.py", "pkg.a", False), ("pkg/__init__.py", "pkg", True),
     ("pkg/sub/b.py", "pkg.sub.b", False)],
)
def test_paths_become_dotted_names(tmp_path, relative, expected, is_package):
    from pathlib import Path

    assert module_name(Path(tmp_path / relative), Path(tmp_path)) == (expected, is_package)


@pytest.mark.parametrize(
    "name,path,expected",
    [("test_thing", "/r/test_thing.py", True), ("thing_test", "/r/thing_test.py", True),
     ("conftest", "/r/conftest.py", True), ("api", "/r/tests/api.py", True),
     ("api", "/r/pkg/api.py", False)],
)
def test_test_modules_are_recognised(name, path, expected):
    assert looks_like_test(name, path) is expected
