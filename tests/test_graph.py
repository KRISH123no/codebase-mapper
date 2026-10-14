"""The arithmetic: coupling, instability, cycles, depth."""

import pytest
from conftest import graph_of, mod


def test_fan_in_counts_who_depends_on_you():
    g = graph_of(mod("a", ["c"]), mod("b", ["c"]), mod("c"))
    assert g.nodes["c"].fan_in == 2 and g.nodes["c"].fan_out == 0


def test_an_edge_to_something_outside_the_project_is_ignored():
    g = graph_of(mod("a", ["requests"]))
    assert g.nodes["a"].fan_out == 0


# ------------------------------------------------------------- instability


def test_a_module_nobody_depends_on_is_unstable():
    g = graph_of(mod("a", ["b"]), mod("b"))
    assert g.nodes["a"].instability == 1.0


def test_a_module_that_depends_on_nothing_is_stable():
    g = graph_of(mod("a", ["b"]), mod("b"))
    assert g.nodes["b"].instability == 0.0


def test_an_isolated_module_is_treated_as_unconstrained():
    assert graph_of(mod("a")).nodes["a"].instability == 1.0


def test_instability_is_the_ratio():
    g = graph_of(mod("a", ["b", "c"]), mod("b", ["a"]), mod("c"))
    # a depends on 2, 1 depends on a
    assert g.nodes["a"].instability == pytest.approx(2 / 3)


# --------------------------------------------------------------- distance


def test_stable_and_abstract_is_balanced():
    g = graph_of(mod("base", classes=2, abstract=2), mod("a", ["base"]))
    assert g.nodes["base"].distance == pytest.approx(0.0)


def test_unstable_and_concrete_is_balanced():
    g = graph_of(mod("leaf", ["base"], classes=1), mod("base"))
    assert g.nodes["leaf"].distance == pytest.approx(0.0)


def test_stable_and_concrete_is_the_painful_corner():
    g = graph_of(mod("core", classes=2), mod("a", ["core"]), mod("b", ["core"]))
    node = g.nodes["core"]
    assert node.distance == pytest.approx(1.0) and node.in_zone_of_pain


def test_a_leaf_nothing_depends_on_is_not_in_the_zone_of_pain():
    """Concrete is only painful when things lean on it."""
    assert not graph_of(mod("a", classes=1)).nodes["a"].in_zone_of_pain


# ----------------------------------------------------------------- cycles


def test_a_straight_chain_has_no_cycle():
    assert graph_of(mod("a", ["b"]), mod("b", ["c"]), mod("c")) .cycles() == []


def test_two_modules_importing_each_other():
    g = graph_of(mod("a", ["b"]), mod("b", ["a"]))
    assert g.cycles() == [["a", "b"]]


def test_a_longer_loop_is_found():
    g = graph_of(mod("a", ["b"]), mod("b", ["c"]), mod("c", ["a"]))
    assert g.cycles() == [["a", "b", "c"]]


def test_two_separate_cycles_are_both_found():
    g = graph_of(mod("a", ["b"]), mod("b", ["a"]), mod("x", ["y"]), mod("y", ["x"]))
    assert len(g.cycles()) == 2


def test_the_biggest_cycle_comes_first():
    g = graph_of(
        mod("a", ["b"]), mod("b", ["c"]), mod("c", ["a"]),
        mod("x", ["y"]), mod("y", ["x"]),
    )
    assert len(g.cycles()[0]) == 3


def test_a_deep_graph_does_not_blow_the_stack():
    """Recursion dies on a big project, which is when you want the answer."""
    chain = [mod(f"m{i}", [f"m{i + 1}"]) for i in range(3000)] + [mod("m3000")]
    assert graph_of(*chain).cycles() == []


def test_the_edge_to_cut_leaves_the_most_unstable_module():
    g = graph_of(mod("a", ["b"]), mod("b", ["a"]), mod("c", ["b"]))
    # b has something depending on it, so a is the freer end
    assert g.weakest_edge(["a", "b"]) == ("a", "b")


def test_nothing_to_cut_when_there_is_no_cycle():
    assert graph_of(mod("a"), mod("b")).weakest_edge(["a", "b"]) is None


# ------------------------------------------------------------------ depth


def test_depth_is_the_longest_chain():
    assert graph_of(mod("a", ["b"]), mod("b", ["c"]), mod("c")).depth() == 2


def test_a_flat_project_has_no_depth():
    assert graph_of(mod("a"), mod("b")).depth() == 0


def test_a_cycle_does_not_make_depth_infinite():
    assert graph_of(mod("a", ["b"]), mod("b", ["a"])).depth() < 10


def test_modules_rank_by_fan_in():
    g = graph_of(mod("a", ["c"]), mod("b", ["c"]), mod("c"), mod("d", ["a"]))
    assert g.ranked()[0].name == "c"
