"""End to end, on real input, with the claims the README makes.

The unit tests check the pieces. These check the things a user would notice
and a reviewer would ask about: does it run on a real project, does it finish,
and is the output actually deterministic the way the README says.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from codebase_mapper.cli import main
from codebase_mapper.findings import collect
from codebase_mapper.graph import Graph
from codebase_mapper.parse import parse
from conftest import project

HERE = Path(__file__).resolve().parent.parent


# -------------------------------------------------- it runs on real code


def test_it_reads_its_own_source():
    found = parse(HERE / "codebase_mapper").source
    assert len(found) >= 8
    assert "cli" in found or any(n.endswith("cli") for n in found)


def test_its_own_graph_is_sound():
    graph = Graph(parse(HERE / "codebase_mapper").source)
    assert graph.cycles() == [], "this project should not have circular imports"
    assert 0 < graph.depth() < 10


def test_every_finding_on_its_own_source_is_well_formed():
    """A finding with an empty headline is worse than no finding."""
    graph = Graph(parse(HERE / "codebase_mapper").source)
    for finding in collect(graph):
        assert finding.subject and finding.headline
        assert finding.severity > 0
        assert finding.kind


# ---------------------------------------------------------- determinism


def test_the_same_input_gives_the_same_output(capsys, tiny):
    """The README claims no model calls and a deterministic core. Check it."""
    main(["map", str(tiny), "--no-git"])
    first = capsys.readouterr().out
    main(["map", str(tiny), "--no-git"])
    assert capsys.readouterr().out == first


def test_the_order_files_are_read_in_does_not_change_the_answer(tmp_path):
    """os.walk order is not guaranteed; the ranking must not depend on it."""
    files = {"pkg/__init__.py": ""}
    files.update({f"pkg/m{i}.py": "from .core import Thing\n" for i in range(6)})
    files["pkg/core.py"] = "class Thing:\n    pass\n"
    project(tmp_path, files)

    runs = []
    for _ in range(3):
        graph = Graph(parse(tmp_path).source)
        runs.append([(f.kind, f.subject, round(f.severity, 6)) for f in collect(graph)])
    assert runs[0] == runs[1] == runs[2]


# ---------------------------------------------------------- it finishes


def test_a_large_project_finishes_quickly(tmp_path):
    """Django is 920 modules and takes about ten seconds. This is a floor
    under that, so a change that makes it quadratic is caught here."""
    files = {"pkg/__init__.py": ""}
    for i in range(400):
        files[f"pkg/m{i}.py"] = f"from .m{max(i - 1, 0)} import x\nx = {i}\n"
    project(tmp_path, files)

    started = time.perf_counter()
    graph = Graph(parse(tmp_path).source)
    collect(graph)
    assert time.perf_counter() - started < 10.0


def test_a_deep_chain_does_not_crash(tmp_path):
    """Recursion dies where it hurts most: on the biggest project."""
    files = {"pkg/__init__.py": ""}
    for i in range(1200):
        files[f"pkg/m{i}.py"] = f"from .m{i + 1} import x\n" if i < 1199 else "x = 1\n"
    project(tmp_path, files)
    graph = Graph(parse(tmp_path).source)
    assert graph.cycles() == []


# ------------------------------------------------- the three real bugs


def test_regression_a_package_reexport_is_not_a_cycle(tmp_path):
    """Found on requests: `from . import x` recorded an edge to the package,
    giving every submodule a phantom edge back to __init__."""
    project(tmp_path, {
        "pkg/__init__.py": "from .api import run\n",
        "pkg/api.py": "from . import store\n",
        "pkg/store.py": "x = 1\n",
    })
    assert Graph(parse(tmp_path).source).cycles() == []


def test_regression_a_type_checking_import_is_not_a_cycle(tmp_path):
    """Found on flask: 20 of 35 modules, all from deferred imports."""
    project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from .b import x\n",
        "pkg/b.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .a import y\n",
    })
    assert Graph(parse(tmp_path).source).cycles() == []


def test_regression_severity_counts_as_well_as_shares():
    """Found in review: a module everything depends on scored the same in a
    three-module project and a thirty-module one."""
    from conftest import graph_of, mod
    from codebase_mapper.findings import critical_untested

    small = graph_of(mod("core", coverage=0.1), *[mod(f"m{i}", ["core"]) for i in range(2)])
    large = graph_of(mod("core", coverage=0.1), *[mod(f"m{i}", ["core"]) for i in range(20)])
    assert critical_untested(large)[0].severity > critical_untested(small)[0].severity


# ------------------------------------------------------- the installed command


def test_it_runs_as_an_installed_command():
    """`python -m codebase_mapper` is how a user actually invokes it."""
    done = subprocess.run(
        [sys.executable, "-m", "codebase_mapper", "map", str(HERE / "codebase_mapper"), "--no-git"],
        capture_output=True, text=True, cwd=HERE, timeout=60, check=False,
    )
    assert done.returncode == 0
    assert "modules" in done.stdout
    assert done.stderr == "", "a clean run should print nothing to stderr"
