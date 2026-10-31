"""The ranking, which is the actual project."""


from conftest import graph_of, mod

from codebase_mapper.findings import (
    collect,
    critical_untested,
    cycles,
    over_tested_leaves,
)
from codebase_mapper.history import Coupling


def kinds(found):
    return [f.kind for f in found]


def test_load_bearing_and_untested_is_the_headline():
    g = graph_of(
        mod("core", classes=1, coverage=0.1),
        *[mod(f"m{i}", ["core"], coverage=0.9) for i in range(5)],
    )
    found = critical_untested(g)
    assert [f.subject for f in found] == ["core"]


def test_a_well_tested_core_is_not_a_finding():
    g = graph_of(mod("core", coverage=0.95), *[mod(f"m{i}", ["core"]) for i in range(5)])
    assert critical_untested(g) == []


def test_an_untested_leaf_is_not_a_finding():
    """Low coverage only matters when something depends on you."""
    g = graph_of(mod("leaf", coverage=0.0), mod("a"))
    assert critical_untested(g) == []


def test_without_a_coverage_report_the_check_stays_quiet():
    """Silence beats guessing."""
    g = graph_of(mod("core"), *[mod(f"m{i}", ["core"]) for i in range(5)])
    assert critical_untested(g) == []


def test_more_dependants_means_more_severe():
    few = graph_of(mod("core", coverage=0.1), *[mod(f"m{i}", ["core"]) for i in range(2)])
    many = graph_of(mod("core", coverage=0.1), *[mod(f"m{i}", ["core"]) for i in range(9)])
    assert critical_untested(many)[0].severity > critical_untested(few)[0].severity


def test_less_coverage_means_more_severe():
    bad = graph_of(mod("core", coverage=0.05), *[mod(f"m{i}", ["core"]) for i in range(5)])
    better = graph_of(mod("core", coverage=0.45), *[mod(f"m{i}", ["core"]) for i in range(5)])
    assert critical_untested(bad)[0].severity > critical_untested(better)[0].severity


# -------------------------------------------------------- zone of pain


def test_a_tested_types_module_is_ranked_far_below_an_untested_one():
    """Concrete and depended-upon is survivable when it is tested — a types
    module is exactly that shape and is usually fine."""
    tested = graph_of(mod("model", classes=3, coverage=0.95),
                      *[mod(f"m{i}", ["model"]) for i in range(4)])
    untested = graph_of(mod("model", classes=3, coverage=0.1),
                        *[mod(f"m{i}", ["model"]) for i in range(4)])
    from codebase_mapper.findings import zone_of_pain

    assert zone_of_pain(untested)[0].severity > zone_of_pain(tested)[0].severity * 3


# --------------------------------------------------------------- cycles


def test_a_cycle_is_reported_with_the_edge_to_cut():
    g = graph_of(mod("a", ["b"]), mod("b", ["a"]), mod("c", ["b"]))
    found = cycles(g)
    assert len(found) == 1 and "Cut a → b" in found[0].advice


def test_a_bigger_cycle_outranks_a_smaller_one():
    g = graph_of(
        mod("a", ["b"]), mod("b", ["c"]), mod("c", ["a"]),
        mod("x", ["y"]), mod("y", ["x"]),
    )
    assert cycles(g)[0].severity > cycles(g)[1].severity


# ------------------------------------------------------- hidden coupling


def test_files_that_change_together_are_reported():
    from codebase_mapper.findings import hidden_coupling

    found = hidden_coupling([Coupling("a.py", "b.py", together=8, either=10)])
    assert found and "8 of 10" in found[0].headline


def test_a_stronger_coupling_outranks_a_weaker_one():
    from codebase_mapper.findings import hidden_coupling

    found = hidden_coupling([
        Coupling("a.py", "b.py", together=9, either=10),
        Coupling("c.py", "d.py", together=4, either=10),
    ])
    assert found[0].severity > found[1].severity


# ---------------------------------------------------------------- wording


def test_a_proxy_check_says_it_is_a_proxy():
    """Claiming to count responsibilities is guessing with confidence."""
    from codebase_mapper.findings import wide_modules

    g = graph_of(mod("god", [f"m{i}" for i in range(10)]), *[mod(f"m{i}") for i in range(10)])
    assert "proxy" in wide_modules(g)[0].advice


def test_over_testing_a_leaf_is_noted_as_not_a_problem():
    g = graph_of(mod("leaf", coverage=0.99), mod("a", ["b"]), mod("b"))
    assert "Not a problem" in over_tested_leaves(g)[0].advice


# ------------------------------------------------------------- collecting


def test_findings_come_back_worst_first():
    g = graph_of(
        mod("core", classes=1, coverage=0.05),
        *[mod(f"m{i}", ["core"]) for i in range(8)],
        mod("x", ["y"]), mod("y", ["x"]),
    )
    found = collect(g)
    assert found == sorted(found, key=lambda f: -f.severity)
    assert found[0].kind in {"untested-core", "cycle"}


def test_a_tidy_project_produces_nothing():
    g = graph_of(mod("a", ["b"], coverage=0.8), mod("b", classes=1, abstract=1, coverage=0.8))
    assert collect(g) == []


def test_the_limit_is_respected():
    # Distinct subjects, because each module now contributes at most one line.
    g = graph_of(
        mod("core", classes=1, coverage=0.0),
        mod("other", classes=1, coverage=0.1),
        *[mod(f"m{i}", ["core", "other"], coverage=0.9) for i in range(8)],
        mod("x", ["y"]), mod("y", ["x"]),
        mod("p", ["q"]), mod("q", ["p"]),
        mod("god", [f"m{i}" for i in range(8)]),
    )
    assert len(collect(g)) > 3
    assert len(collect(g, limit=3)) == 3


# ------------------------------------------------- one line per module


def test_a_module_is_reported_once_with_the_worst_thing_true_about_it():
    """It was appearing twice, and the weaker entry often sorted higher."""
    g = graph_of(
        mod("core", classes=2, coverage=0.1),
        *[mod(f"m{i}", ["core"], coverage=0.9) for i in range(6)],
    )
    found = collect(g)
    subjects = [f.subject for f in found]
    assert subjects.count("core") == 1
    assert next(f for f in found if f.subject == "core").kind == "untested-core"


def test_the_measured_fact_outranks_the_proxy():
    """wide-module says "a proxy, not a verdict" in its own advice. It must
    never sort above something measured."""
    g = graph_of(
        mod("core", classes=1, coverage=0.1),
        *[mod(f"m{i}", ["core"], coverage=0.95) for i in range(6)],
        mod("god", [f"m{i}" for i in range(6)] + ["core"]),
    )
    found = collect(g)
    assert found[0].kind == "untested-core"


def test_nothing_scoring_zero_takes_up_a_line():
    g = graph_of(mod("a", classes=1, coverage=1.0), mod("b", ["a"], coverage=1.0))
    assert all(f.severity > 0 for f in collect(g))


def test_the_order_is_stable_when_severities_tie():
    g = graph_of(
        mod("core", classes=1, coverage=0.2),
        *[mod(f"m{i}", ["core"], coverage=0.2) for i in range(4)],
    )
    assert [f.subject for f in collect(g)] == [f.subject for f in collect(g)]
