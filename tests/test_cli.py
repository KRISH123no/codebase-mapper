"""The command, end to end on a small project."""

import pytest
from conftest import project

from codebase_mapper.cli import main


def run(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_it_reports_on_a_real_directory(capsys, tiny):
    code, out = run(capsys, "map", str(tiny), "--no-git")
    assert code == 0 and "4 modules" in out


def test_a_path_that_is_not_a_directory_is_refused(capsys, tmp_path):
    code, out = run(capsys, "map", str(tmp_path / "nope"), "--no-git")
    assert code == 1 and "not a directory" in out


def test_a_directory_with_no_python_says_so(capsys, tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    code, out = run(capsys, "map", str(tmp_path), "--no-git")
    assert code == 1 and "no Python modules" in out


def test_without_coverage_it_says_what_to_run(capsys, tiny):
    code, out = run(capsys, "map", str(tiny), "--no-git")
    assert "coverage xml" in out


def test_with_coverage_the_strongest_finding_becomes_available(capsys, tmp_path):
    project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "class Thing:\n    pass\n",
        **{f"pkg/m{i}.py": "from .core import Thing\n" for i in range(5)},
    })
    (tmp_path / "coverage.xml").write_text(
        '<coverage><class filename="pkg/core.py" line-rate="0.05"/></coverage>'
    )
    code, out = run(capsys, "map", str(tmp_path), "--no-git")
    assert code == 0
    assert "5 modules depend on it" in out and "5% covered" in out


def test_tests_are_excluded_from_the_graph_by_default(capsys, tiny):
    _, without = run(capsys, "map", str(tiny), "--no-git")
    _, with_tests = run(capsys, "map", str(tiny), "--no-git", "--include-tests")
    assert "4 modules" in without and "5 modules" in with_tests


def test_the_numbers_table_explains_its_columns(capsys, tiny):
    code, out = run(capsys, "numbers", str(tiny), "--no-git")
    assert code == 0 and "instability" in out and "Ca" in out


def test_a_bare_path_works_without_naming_the_subcommand(capsys, tiny):
    """`codebase-mapper .` is what people will actually type."""
    code, out = run(capsys, str(tiny), "--no-git")
    assert code == 0 and "modules" in out


def test_unparseable_files_are_counted_in_the_output(capsys, tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/ok.py": "x = 1\n", "pkg/bad.py": "def (\n"})
    code, out = run(capsys, "map", str(tmp_path), "--no-git")
    assert "could not be parsed" in out


def test_a_tidy_project_is_told_so(capsys, tmp_path):
    project(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "x = 1\n"})
    code, out = run(capsys, "map", str(tmp_path), "--no-git")
    assert code == 0 and "tidy" in out


@pytest.mark.parametrize(
    "argv,expected",
    [([], ["map"]), (["."], ["map", "."]), (["map", "."], ["map", "."]),
     (["numbers"], ["numbers"]), (["--version"], ["--version"])],
)
def test_the_subcommand_is_optional(argv, expected):
    from codebase_mapper.cli import normalise

    assert normalise(argv) == expected
