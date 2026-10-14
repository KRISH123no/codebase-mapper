"""Deciding what is worth saying, and in what order.

Everything before this file is measurement, and measurement is the easy half.
A tool that prints forty numbers has told you nothing; the work is choosing
which three matter.

The ordering principle throughout is **blast radius**: how much of the project
is exposed if this is wrong. A problem in a module nine others depend on
outranks the same problem in a leaf, every time.

Where a check is a proxy rather than the thing itself, the wording says so.
"Possible duplication — worth a look" is a claim this tool can support;
"violates the single responsibility principle" is not, because a
responsibility is not a measurable quantity and any tool claiming to count
them is guessing with confidence.
"""

from __future__ import annotations

from .graph import Graph
from .history import Coupling
from .model import Finding

#: Below this, a module everything depends on is a liability.
THIN_COVERAGE = 0.5
#: Above this on a leaf, effort is going somewhere it is not needed.
THOROUGH = 0.95
#: Depending on more than this is usually a module doing several jobs.
WIDE_FAN_OUT = 8


def critical_untested(graph: Graph) -> list[Finding]:
    """The headline: load-bearing and unverified.

    Neither number says much alone. Coverage of 14% is fine on something
    nothing depends on; a fan-in of nine is fine when the thing is tested.
    Together they are the single most actionable fact about a codebase.
    """
    out = []
    for node in graph.nodes.values():
        coverage = node.module.coverage
        if coverage is None or node.fan_in < 2 or coverage >= THIN_COVERAGE:
            continue
        # Both the count and the share matter, and neither alone is enough.
        # Share alone calls "every module depends on it" equally bad in a
        # three-module project and a thirty-module one; count alone ignores
        # that nine of ten is worse than nine of three hundred.
        share = node.fan_in / max(len(graph) - 1, 1)
        severity = node.fan_in * share * (1.0 - coverage)
        out.append(
            Finding(
                kind="untested-core",
                subject=node.name,
                severity=severity * 10,
                headline=f"{node.fan_in} modules depend on it · {coverage:.0%} covered",
                detail=(
                    f"A bug here reaches {node.fan_in} of {len(graph) - 1} modules "
                    f"and the suite would not catch it."
                ),
                advice="Test this before anything else in the project.",
            )
        )
    return out


def zone_of_pain(graph: Graph) -> list[Finding]:
    """Stable and concrete: depended upon, and impossible to extend.

    Ranked below the untested check on purpose. A concrete module everything
    leans on is uncomfortable but survivable when it is well tested — a types
    module is exactly this and is usually fine. It is the untested ones that
    hurt, so coverage lowers the severity rather than deciding the finding.
    """
    out = []
    for node in graph.nodes.values():
        if not node.in_zone_of_pain:
            continue
        coverage = node.module.coverage
        comfort = coverage if coverage is not None else 0.5
        severity = node.fan_in * node.distance * (1.0 - comfort) * 6
        out.append(
            Finding(
                kind="zone-of-pain",
                subject=node.name,
                severity=severity,
                headline=(
                    f"stable and concrete · I={node.instability:.2f} "
                    f"A={node.abstractness:.2f} · {node.fan_in} depend on it"
                ),
                detail=(
                    "Everything leans on it and there is nothing abstract to "
                    "implement against, so every change here is a change to them."
                ),
                advice="If it keeps changing, put an interface in front of it.",
            )
        )
    return out


def cycles(graph: Graph) -> list[Finding]:
    """Circular dependencies, with the cheapest edge to cut."""
    out = []
    for group in graph.cycles():
        edge = graph.weakest_edge(group)
        exposure = sum(graph.nodes[n].fan_in for n in group)
        out.append(
            Finding(
                kind="cycle",
                subject=" → ".join(group[:4]) + (" → …" if len(group) > 4 else ""),
                severity=len(group) * 8 + exposure * 2,
                headline=f"{len(group)} modules depend on each other",
                detail="None of them can be understood, tested or moved on its own.",
                advice=(
                    f"Cut {edge[0]} → {edge[1]} first; it is the most unstable "
                    "end, so inverting it is cheapest."
                ) if edge else "",
            )
        )
    return out


def hidden_coupling(found: list[Coupling], *, limit: int = 5) -> list[Finding]:
    """Files that change together with nothing in the source to explain it."""
    out = []
    for coupling in found[:limit]:
        out.append(
            Finding(
                kind="hidden-coupling",
                subject=f"{coupling.left} + {coupling.right}",
                severity=coupling.strength * coupling.together * 2,
                headline=(
                    f"changed together in {coupling.together} of "
                    f"{coupling.either} commits ({coupling.strength:.0%})"
                ),
                detail=(
                    "Neither imports the other, so the dependency is not in the "
                    "code — a shared schema, a duplicated constant, a protocol "
                    "both ends implement."
                ),
                advice="Find what they share. That is the real module boundary.",
            )
        )
    return out


def wide_modules(graph: Graph) -> list[Finding]:
    """Depending on most of the project usually means doing several jobs.

    A proxy, and labelled as one. Some modules legitimately coordinate — a CLI
    is supposed to touch everything — so this says "worth a look", not
    "violates a principle".
    """
    out = []
    for node in graph.nodes.values():
        if node.fan_out < WIDE_FAN_OUT:
            continue
        out.append(
            Finding(
                kind="wide-module",
                subject=node.name,
                severity=node.fan_out * 1.5,
                headline=f"depends on {node.fan_out} modules",
                detail="Often a coordinator, sometimes a module doing several jobs.",
                advice="Worth a look — this is a proxy, not a verdict.",
            )
        )
    return out


def over_tested_leaves(graph: Graph) -> list[Finding]:
    """Effort spent where a bug could not travel."""
    out = []
    for node in graph.nodes.values():
        coverage = node.module.coverage
        if coverage is None or node.fan_in > 0 or coverage < THOROUGH:
            continue
        out.append(
            Finding(
                kind="over-tested-leaf",
                subject=node.name,
                severity=1.0,
                headline=f"{coverage:.0%} covered · {node.fan_in} depend on it",
                detail="Thoroughly tested, and nothing downstream to protect.",
                advice="Not a problem. Noted because the effort could go elsewhere.",
            )
        )
    return out


def collect(
    graph: Graph,
    coupling: list[Coupling] | None = None,
    *,
    limit: int | None = None,
) -> list[Finding]:
    """Everything worth saying, worst first."""
    found = (
        critical_untested(graph)
        + cycles(graph)
        + hidden_coupling(coupling or [])
        + zone_of_pain(graph)
        + wide_modules(graph)
        + over_tested_leaves(graph)
    )
    found.sort(key=lambda f: -f.severity)
    return found[:limit] if limit else found
