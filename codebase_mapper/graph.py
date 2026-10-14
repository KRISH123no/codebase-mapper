"""The arithmetic. Given modules and edges, what shape is this project?

Three ideas, all thirty years old and all computable:

**Coupling.** How many modules depend on this one (afferent, Ca) and how many
it depends on (efferent, Ce).

**Instability** `I = Ce / (Ca + Ce)`. Zero means nothing can force this module
to change. One means everything can.

**Distance from the main sequence** `D = |A + I - 1|`, where A is
abstractness. The claim is that a module should be either stable *and*
abstract — safe for the whole project to lean on, because you extend it
rather than edit it — or unstable *and* concrete, free to change because
nothing depends on it. Being stable and concrete is the painful corner:
everything depends on you and you cannot be extended without being edited.

These are heuristics with a formal definition, not laws. They tell you where
to look, and the output says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Module


@dataclass(slots=True)
class Node:
    module: Module
    #: Modules that depend on this one.
    fan_in: int = 0
    #: Modules this one depends on.
    fan_out: int = 0

    @property
    def name(self) -> str:
        return self.module.name

    @property
    def instability(self) -> float:
        """0 = nothing can make it change, 1 = everything can.

        A module nobody depends on and which depends on nothing is maximally
        unstable by convention — it is unconstrained, which is the honest
        reading even though the arithmetic is undefined.
        """
        total = self.fan_in + self.fan_out
        return self.fan_out / total if total else 1.0

    @property
    def abstractness(self) -> float:
        return self.module.abstractness

    @property
    def distance(self) -> float:
        """How far off the main sequence. 0 is balanced, 1 is a corner."""
        return abs(self.abstractness + self.instability - 1.0)

    @property
    def in_zone_of_pain(self) -> bool:
        """Stable and concrete: everything leans on it and it cannot be
        extended without editing it."""
        return self.instability <= 0.3 and self.abstractness <= 0.2 and self.fan_in >= 2


class Graph:
    def __init__(self, modules: dict[str, Module]) -> None:
        self.modules = modules
        self.edges: dict[str, set[str]] = {
            name: {t for t in module.imports if t in modules}
            for name, module in modules.items()
        }
        self.nodes: dict[str, Node] = {n: Node(m) for n, m in modules.items()}
        for source, targets in self.edges.items():
            self.nodes[source].fan_out = len(targets)
            for target in targets:
                self.nodes[target].fan_in += 1

    def __len__(self) -> int:
        return len(self.nodes)

    def ranked(self, by: str = "fan_in") -> list[Node]:
        return sorted(self.nodes.values(), key=lambda n: -getattr(n, by))

    # ------------------------------------------------------------- cycles

    def cycles(self) -> list[list[str]]:
        """Every group of modules that can reach each other.

        Tarjan's strongly-connected components, iteratively — a recursive
        version blows the stack on a large project, which is exactly when you
        want the answer.
        """
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        counter = 0
        found: list[list[str]] = []

        for root in self.edges:
            if root in index:
                continue
            work: list[tuple[str, list[str]]] = [(root, sorted(self.edges[root]))]
            index[root] = low[root] = counter
            counter += 1
            stack.append(root)
            on_stack.add(root)

            while work:
                node, pending = work[-1]
                if pending:
                    child = pending.pop()
                    if child not in index:
                        index[child] = low[child] = counter
                        counter += 1
                        stack.append(child)
                        on_stack.add(child)
                        work.append((child, sorted(self.edges[child])))
                    elif child in on_stack:
                        low[node] = min(low[node], index[child])
                    continue

                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        group.append(member)
                        if member == node:
                            break
                    if len(group) > 1:
                        found.append(sorted(group))

        return sorted(found, key=len, reverse=True)

    def weakest_edge(self, cycle: list[str]) -> tuple[str, str] | None:
        """The edge to cut to break a cycle: the one carrying least weight.

        Among the edges inside the cycle, prefer the one leaving the most
        unstable module — the one already free to change — because that is the
        cheapest place to invert a dependency.
        """
        inside = [
            (source, target)
            for source in cycle
            for target in self.edges[source]
            if target in cycle
        ]
        if not inside:
            return None
        return max(inside, key=lambda e: (self.nodes[e[0]].instability, e[0]))

    # -------------------------------------------------------------- depth

    def depth(self) -> int:
        """The longest chain of dependencies, ignoring cycles."""
        memo: dict[str, int] = {}
        visiting: set[str] = set()

        def walk(node: str) -> int:
            if node in memo:
                return memo[node]
            if node in visiting:
                return 0  # a cycle; reported separately, not counted here
            visiting.add(node)
            best = 0
            for child in self.edges.get(node, ()):
                best = max(best, 1 + walk(child))
            visiting.discard(node)
            memo[node] = best
            return best

        return max((walk(n) for n in self.edges), default=0)
