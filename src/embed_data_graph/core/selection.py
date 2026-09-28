"""Non-owning selections of live graph entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Iterator, Tuple, TypeVar

if TYPE_CHECKING:
    from embed_data_graph.core.graph import DatasetGraph

_SelectedT = TypeVar("_SelectedT")


@dataclass(frozen=True)
class Selection(Generic[_SelectedT]):
    """A snapshot of live entities chosen by ``DatasetGraph.select``.

    The selection does not own its entities: editing one edits the graph, and
    membership is not recomputed when entities or the graph change. Use
    ``DatasetGraph.partition`` for independent copies.

    Attributes
    ----------
    graph : DatasetGraph
        Graph the entities belong to.
    level : str
        Registry kind that was selected.
    objects : tuple
        Selected live entities in registration order.
    """

    graph: "DatasetGraph"
    """Graph the entities belong to."""
    level: str
    """Registry kind that was selected."""
    objects: Tuple[_SelectedT, ...]
    """Selected live entities in registration order."""

    def __iter__(self) -> Iterator[_SelectedT]:
        return iter(self.objects)

    def __len__(self) -> int:
        return len(self.objects)


__all__ = ["Selection"]
