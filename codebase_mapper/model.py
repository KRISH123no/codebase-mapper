"""What codebase_mapper deals in: a module, the graph it sits in, and a finding.

Nothing here parses or measures. Everything downstream works on these, which
is why the maths can be tested without a repository to point at.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Module:
    """One importable file, and what it declares."""

    name: str
    path: str
    #: Modules inside this project that it imports. External packages are not
    #: edges: you cannot refactor requests, so it is not part of your shape.
    imports: set[str] = field(default_factory=set)
    #: Each `from X import a, b` as (X, ("a", "b")), kept until every module is
    #: known. `from . import sessions` names the package and the thing taken
    #: out of it, and only the full set of modules says which of those two is
    #: the real target.
    raw: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    classes: int = 0
    #: Classes that are abstract — ABC, Protocol, or holding @abstractmethod.
    abstract_classes: int = 0
    functions: int = 0
    lines: int = 0
    #: Fraction of lines the test suite executes, when a coverage report exists.
    coverage: float | None = None
    is_test: bool = False

    @property
    def abstractness(self) -> float:
        """A, in Martin's terms: 0 is entirely concrete, 1 entirely abstract.

        A module with no classes is concrete by definition — a file of plain
        functions is something you edit, not something you implement against.
        """
        return self.abstract_classes / self.classes if self.classes else 0.0


@dataclass(slots=True)
class Finding:
    """Something worth telling someone, and how much it matters."""

    kind: str
    subject: str
    severity: float
    headline: str
    detail: str = ""
    #: What to do, when there is a clear answer.
    advice: str = ""

    def __lt__(self, other: Finding) -> bool:
        return self.severity < other.severity
