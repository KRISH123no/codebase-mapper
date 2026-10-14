"""Matching a coverage report to modules, and reading git for coupling."""

import subprocess

import pytest
from conftest import mod

from codebase_mapper.coverage import attach, read
from codebase_mapper.history import Coupling, commits, couplings, undeclared

XML = """<?xml version="1.0" ?>
<coverage>
  <packages><package><classes>
    <class filename="pkg/core.py" line-rate="0.14"/>
    <class filename="pkg/leaf.py" line-rate="0.96"/>
  </classes></package></packages>
</coverage>
"""


def test_line_rates_are_read(tmp_path):
    path = tmp_path / "coverage.xml"
    path.write_text(XML)
    assert read(path) == {"pkg/core.py": 0.14, "pkg/leaf.py": 0.96}


def test_a_missing_report_is_empty_not_an_error(tmp_path):
    assert read(tmp_path / "nope.xml") == {}


def test_a_corrupt_report_is_empty_not_an_error(tmp_path):
    path = tmp_path / "coverage.xml"
    path.write_text("not xml at all")
    assert read(path) == {}


def test_coverage_attaches_to_the_right_module():
    modules = {"pkg.core": mod("pkg.core"), "pkg.leaf": mod("pkg.leaf")}
    modules["pkg.core"].path = "/abs/repo/pkg/core.py"
    modules["pkg.leaf"].path = "/abs/repo/pkg/leaf.py"
    assert attach(modules, {"pkg/core.py": 0.14, "pkg/leaf.py": 0.96}, "/abs/repo") == 2
    assert modules["pkg.core"].coverage == 0.14


def test_a_report_rooted_somewhere_else_still_matches():
    """Reports disagree about whether paths are absolute or relative."""
    modules = {"pkg.core": mod("pkg.core")}
    modules["pkg.core"].path = "/abs/repo/src/pkg/core.py"
    assert attach(modules, {"/build/src/pkg/core.py": 0.5}, "/abs/repo") == 1


def test_a_bare_filename_is_too_weak_to_match():
    """One segment is a guess; two means a directory agreed as well."""
    modules = {"pkg.core": mod("pkg.core")}
    modules["pkg.core"].path = "/abs/repo/pkg/core.py"
    assert attach(modules, {"core.py": 0.5}, "/abs/repo") == 0


def test_nothing_to_attach_is_not_an_error():
    assert attach({"a": mod("a")}, {}, "/repo") == 0


# ------------------------------------------------------------- co-change


def test_files_changed_together_are_counted():
    log = [["a.py", "b.py"]] * 5
    found = couplings(log)
    assert found[0].together == 5 and found[0].strength == 1.0


def test_a_pair_that_rarely_coincides_is_not_coupled():
    log = [["a.py", "b.py"]] + [["a.py"]] * 9 + [["b.py"]] * 9
    assert couplings(log) == []


def test_too_few_commits_together_is_not_evidence():
    assert couplings([["a.py", "b.py"]] * 2) == []


def test_a_sweeping_commit_does_not_couple_the_whole_project():
    """A reformat touches everything and says nothing about design."""
    sweep = [[f"f{i}.py" for i in range(40)]] * 10
    assert couplings(sweep) == []


def test_strength_is_together_over_either():
    log = [["a.py", "b.py"]] * 6 + [["a.py"]] * 2 + [["b.py"]] * 2
    assert couplings(log)[0].strength == pytest.approx(6 / 10)


def test_coupling_explained_by_an_import_is_not_news():
    modules = {"pkg.a": mod("pkg.a", ["pkg.b"]), "pkg.b": mod("pkg.b")}
    modules["pkg.a"].path = "/repo/pkg/a.py"
    modules["pkg.b"].path = "/repo/pkg/b.py"
    found = [Coupling("pkg/a.py", "pkg/b.py", together=8, either=10)]
    assert undeclared(found, modules, "/repo") == []


def test_coupling_with_no_import_between_them_is_news():
    modules = {"pkg.a": mod("pkg.a"), "pkg.b": mod("pkg.b")}
    modules["pkg.a"].path = "/repo/pkg/a.py"
    modules["pkg.b"].path = "/repo/pkg/b.py"
    found = [Coupling("pkg/a.py", "pkg/b.py", together=8, either=10)]
    assert len(undeclared(found, modules, "/repo")) == 1


def test_files_that_are_not_modules_are_ignored():
    """A template or a config file changing alongside code is not a module edge."""
    modules = {"pkg.a": mod("pkg.a")}
    modules["pkg.a"].path = "/repo/pkg/a.py"
    found = [Coupling("pkg/a.py", "README.md", together=8, either=10)]
    assert undeclared(found, modules, "/repo") == []


def test_a_folder_that_is_not_a_repo_returns_nothing(tmp_path):
    assert commits(tmp_path) == []


def test_a_real_repository_is_read(tmp_path):
    run = lambda *a: subprocess.run(a, cwd=tmp_path, capture_output=True, check=False)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 1\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "first")
    assert commits(tmp_path) and set(commits(tmp_path)[0]) == {"a.py", "b.py"}
