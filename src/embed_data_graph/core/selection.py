"""Non-owning selections of live graph entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Generic, Iterator, List, Tuple, TypeVar

from embed_data_graph.core.tabular import Scalar, TableSchema

if TYPE_CHECKING:
    from pandas import DataFrame  # type: ignore[import-untyped]
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

    def _projection(self) -> DatasetGraph:
        # A non-owning temporary registry: no graph pointers or entities mutate.
        from embed_data_graph.core.graph import DatasetGraph, KINDS
        from embed_data_graph.core.tabular import _encode, _issue_row
        members = self.graph._members(self.objects)  # type: ignore[arg-type]
        for obj in self.objects:
            for ancestor in self.graph.ancestors(obj):  # type: ignore[arg-type]
                members.setdefault(id(ancestor), ancestor)
        result = DatasetGraph(source_scope=self.graph.source_scope)
        result._entities = {kind: {obj.key: obj for obj in members.values() if obj.kind == kind} for kind in KINDS}
        addresses = {(obj.kind, obj.key) for obj in members.values()}
        record_index = self.graph._record_index()
        matched = {entry for address in addresses for entry in record_index.get(address, ())}
        result.unresolved_records = {address: self.graph.unresolved_records[address]
                                     for _, address in sorted(matched, key=lambda entry: entry[0])}
        keys = {(kind, _encode(key)) for kind, key in addresses}
        result.load_issues = tuple(issue for issue in self.graph.load_issues
                                  if (_issue_row(issue)["kind"], _issue_row(issue)["entity_key"]) in keys
                                  or issue.context.get("unresolved_address") in result.unresolved_records)
        return result

    def records(self, name: str) -> List[Dict[str, Scalar]]:
        """Project selected roots, descendants and ancestor context as flat rows.

        Parameters
        ----------
        name : str
            Table name accepted by DatasetGraph.records.

        Returns
        -------
        list of dict
            Fresh scalar rows with the graph projection schema and ordering.
            Patient roots include patient-scoped and claimed entities. Selection
            membership remains a snapshot; values reflect the current live
            objects. No copying of consumer metadata or graph mutation occurs.

        Raises
        ------
        ValueError, TypeError
            Same table/key errors as DatasetGraph.records.
        """

        return self._projection().records(name)

    def table_schema(self, name: str) -> TableSchema:
        """Return a graph-compatible schema, including for an empty selection.

        Parameters
        ----------
        name : str
            Projection table name.

        Returns
        -------
        TableSchema
            Ordered columns and key. Unknown names raise ValueError.
        """

        return self.graph.table_schema(name)

    def table(self, name: str) -> DataFrame:
        """Return selected records as a detached pandas DataFrame.

        Parameters
        ----------
        name : str
            Projection table name.

        Returns
        -------
        pandas.DataFrame
            Same rows as records, with graph.table dtypes. Raises ImportError
            without optional pandas; invalid names raise ValueError.
        """

        return self._projection().table(name)

    def tables(self) -> Dict[str, DataFrame]:
        """Return all selection tables with DatasetGraph.tables semantics.

        Returns
        -------
        dict of str to pandas.DataFrame
            One snapshot of selected roots, descendants and ancestor context.
            Optional pandas is required; otherwise ImportError is raised.
        """

        return self._projection().tables()

    def __iter__(self) -> Iterator[_SelectedT]:
        return iter(self.objects)

    def __len__(self) -> int:
        return len(self.objects)


__all__ = ["Selection"]
