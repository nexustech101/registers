from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class Q:
    """Composable query predicate for manager ``filter``/``exclude`` calls."""

    def __init__(self, **criteria: Any) -> None:
        self.criteria = criteria
        self.children: tuple[Q, ...] = ()
        self.connector: Literal["and", "or"] = "and"
        self.negated = False

    @classmethod
    def _combined(cls, connector: Literal["and", "or"], *children: "Q") -> "Q":
        node = cls()
        node.children = tuple(children)
        node.connector = connector
        return node

    def __and__(self, other: "Q") -> "Q":
        return self._combined("and", self, other)

    def __or__(self, other: "Q") -> "Q":
        return self._combined("or", self, other)

    def __invert__(self) -> "Q":
        node = self._combined(self.connector, *self.children)
        node.criteria = dict(self.criteria)
        node.negated = not self.negated
        return node


@dataclass(frozen=True)
class Agg:
    """Aggregate expression used by ``Model.objects.aggregate(...)``."""

    function: Literal["count", "sum", "avg", "min", "max", "count_distinct"]
    field: str
    criteria: dict[str, Any]

    @classmethod
    def count(cls, field: str = "*", **criteria: Any) -> "Agg":
        return cls("count", field, dict(criteria))

    @classmethod
    def sum(cls, field: str, **criteria: Any) -> "Agg":
        return cls("sum", field, dict(criteria))

    @classmethod
    def avg(cls, field: str, **criteria: Any) -> "Agg":
        return cls("avg", field, dict(criteria))

    @classmethod
    def min(cls, field: str, **criteria: Any) -> "Agg":
        return cls("min", field, dict(criteria))

    @classmethod
    def max(cls, field: str, **criteria: Any) -> "Agg":
        return cls("max", field, dict(criteria))

    @classmethod
    def count_distinct(cls, field: str, **criteria: Any) -> "Agg":
        return cls("count_distinct", field, dict(criteria))


@dataclass(frozen=True)
class Page:
    """Cursor pagination result."""

    items: list[Any]
    next_cursor: str | None
    has_next: bool
