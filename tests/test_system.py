"""End to end, on real input, with the claims the README makes.

The unit tests check the pieces. These check the things a user would notice
and a reviewer would ask about: does it run on a real project, does it finish,
and is the output actually deterministic the way the README says.
"""

import subprocess
import sys
import time
from pathlib import Path

from conftest import project

from codebase_mapper.cli import main
from codebase_mapper.findings import collect
from codebase_mapper.graph import Graph
from codebase_mapper.parse import parse

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


# ----------------------------------------------------------- the artifact


def test_the_report_is_written_and_self_contained(tmp_path, tiny, capsys):
    """One file that works offline forever is the only kind worth sending."""
    out = tmp_path / "report.html"
    assert main(["map", str(tiny), "--no-git", "--html", str(out)]) == 0
    page = out.read_text()
    assert "<h2>Findings</h2>" in page
    assert "<h2>Structure</h2>" in page
    assert "<h2>Metrics</h2>" in page
    assert 'src="http' not in page and 'href="http' not in page


def test_the_layers_go_deepest_first(tmp_path):
    """Read it upwards and you are reading the project in build order."""
    from codebase_mapper.html import layers

    project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/base.py": "x = 1\n",
        "pkg/middle.py": "from .base import x\n",
        "pkg/top.py": "from .middle import x\n",
    })
    stack = layers(Graph(parse(tmp_path).source))
    assert "pkg.base" in stack[0]
    assert "pkg.middle" in stack[1]
    assert "pkg.top" in stack[2]


def test_a_module_in_a_cycle_still_gets_a_layer(tmp_path):
    """There is no correct answer for a cycle; looping forever is worse."""
    from codebase_mapper.html import layers

    project(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "from .b import x\n", "pkg/b.py": "from .a import y\n",
    })
    stack = layers(Graph(parse(tmp_path).source))
    placed = {n for layer in stack for n in layer}
    assert {"pkg.a", "pkg.b"} <= placed


def test_everything_the_graph_knows_appears_in_the_report(tmp_path, tiny):
    """A map that quietly omits modules is worse than no map."""
    from codebase_mapper.html import render

    graph = Graph(parse(tiny).source)
    page = render(graph, [], root=str(tiny))
    for name in graph.nodes:
        assert name in page


def test_a_module_name_cannot_inject_markup(tmp_path):
    """Paths come from the filesystem, and a filesystem will accept anything."""
    from codebase_mapper.html import render

    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "x = 1\n"})
    graph = Graph(parse(tmp_path).source)
    node = next(iter(graph.nodes.values()))
    graph.nodes["<script>alert(1)</script>"] = node
    page = render(graph, [], root="<script>bad</script>")
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
