# What "works" means

Written after the fact, which is itself worth admitting: the tool was built
iteratively and these criteria were reconstructed from it rather than agreed
first. They exist so that "does it work?" has an answer that is not an
opinion.

Each one says how it is checked and where.

## Functional

| # | It must | Verified by |
|---|---|---|
| F1 | Read a Python project without executing any of it | `ast.parse` only; no `exec`, `import`, or `subprocess` on project code |
| F2 | Resolve relative imports correctly at every depth | `test_parse.py` — sibling, `from . import x`, `from ..shared import x`, package vs module |
| F3 | Exclude imports that are not runtime dependencies | `test_parse.py::test_an_import_under_type_checking_is_not` and the function-body case |
| F4 | Exclude external packages from the graph | `test_parse.py::test_external_packages_are_not_edges` |
| F5 | Find every circular dependency, and none that are not | `test_graph.py` cycles group; `test_system.py` regressions |
| F6 | Attach a coverage report to the right modules | `test_coverage_history.py` — exact, relocated, and too-weak matches |
| F7 | Rank findings by blast radius, worst first | `test_findings.py::test_findings_come_back_worst_first` |
| F8 | Say nothing rather than guess when data is missing | `test_findings.py::test_without_a_coverage_report_the_check_stays_quiet` |

## Non-functional

| # | It must | Verified by |
|---|---|---|
| N1 | Produce identical output for identical input | `test_system.py::test_the_same_input_gives_the_same_output` |
| N2 | Not depend on filesystem ordering | `test_system.py::test_the_order_files_are_read_in_does_not_change_the_answer` |
| N3 | Finish on a large project | Django: 920 modules, 2,933 files, 9.7s. Floor enforced by `test_a_large_project_finishes_quickly` |
| N4 | Not crash on deep or recursive graphs | `test_a_deep_chain_does_not_crash` — 1,200 modules, iterative Tarjan |
| N5 | Survive files it cannot parse | `test_parse.py::test_a_file_that_will_not_parse_is_reported_not_fatal` |
| N6 | Print nothing to stderr on a clean run | `test_system.py::test_it_runs_as_an_installed_command` |
| N7 | Have no runtime dependencies | `pyproject.toml` — `dependencies = []` |
| N8 | Make no network or model calls | No HTTP client is imported anywhere in the package |

## Out of scope, deliberately

Stated so that "it doesn't do X" is a decision rather than a gap.

- **Languages other than Python.** `ast` is stdlib and cannot run what it reads.
- **Imports resolved at runtime** — string imports, plugin registries, dependency injection.
  The graph is a floor, not the truth.
- **Any judgement that is not measurable.** It will not report "violates single
  responsibility", because a responsibility is not a countable thing.
- **Writing the fix.** It reports; you decide.

## How it was tested

| Level | What | Count |
|---|---|---|
| Unit | Each module in isolation, with hand-built inputs | 102 |
| Integration | The CLI against projects written to a temp directory | included above |
| System | Its own source, determinism, scale, and the installed command | 11 |
| Regression | One test per bug found in real use — see below | 3 |
| Acceptance | This document | — |

## Bugs found by running it on real projects

Each one became a regression test. All three were found by pointing it at
libraries whose shape was already known, which is the only reason they were
recognisable as wrong.

1. **requests reported an 11-module cycle.** `from . import sessions` recorded an
   edge to the *package*, so every submodule gained a phantom edge back to
   `__init__`. Any package that re-exports looked circular.
2. **Flask reported a 20-module cycle out of 35.** `ast.walk` flattens the tree,
   so `if TYPE_CHECKING:` imports counted as runtime dependencies — the tool was
   reporting the workaround as the problem.
3. **Severity was a share, not a count.** A module every other module depended on
   scored the same in a 3-module project as a 30-module one.

After (2), Flask, requests and black all report **zero runtime cycles**, which is
the correct answer for three libraries that each solved this deliberately.
