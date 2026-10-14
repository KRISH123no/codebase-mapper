"""Building small projects on disk, because parsing is the one part that
cannot be faked — and a graph built from hand-written dicts for everything
after it."""

import pytest

from codebase_mapper.model import Module


def project(root, files: dict[str, str]):
    """``project(tmp_path, {"pkg/a.py": "from .b import x"})``."""
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def mod(name, imports=(), *, classes=0, abstract=0, coverage=None, is_test=False):
    return Module(
        name=name, path=f"/repo/{name.replace('.', '/')}.py",
        imports=set(imports), classes=classes, abstract_classes=abstract,
        coverage=coverage, is_test=is_test,
    )


def graph_of(*modules):
    from codebase_mapper.graph import Graph

    return Graph({m.name: m for m in modules})


@pytest.fixture
def tiny(tmp_path):
    return project(tmp_path, {
        "pkg/__init__.py": "from .api import run\n",
        "pkg/api.py": "from . import store\nfrom .model import Thing\n",
        "pkg/store.py": "from .model import Thing\n",
        "pkg/model.py": "class Thing:\n    pass\n",
        "tests/test_api.py": "from pkg import api\n",
    })
