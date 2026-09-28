"""Base class for the eight graph entities and value serialization helpers.

An entity stores its own fields plus the *keys* of related entities, for
example ``Finding.accession_number`` or ``Procedure.finding_references``.
Relationships are never stored as object pointers: a :class:`DatasetGraph`
resolves keys into live objects through its indexes. Related entities may
therefore arrive in any order, and a key whose target is missing is simply an
unresolved reference until that target is registered.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    FrozenSet,
    Hashable,
    Mapping,
    Optional,
    Tuple,
    TypeVar,
)

if TYPE_CHECKING:
    from embed_data_graph.core.graph import DatasetGraph


_EntitySelf = TypeVar("_EntitySelf", bound="MutableEntity")


@dataclass(frozen=True)
class Reference:
    """Declares a field that holds the key of another entity.

    Attributes
    ----------
    field : str
        Attribute holding one key, or a set of keys when ``many`` is True.
    kind : str
        Registry kind of the referenced entity.
    role : {"parent", "child", "association"}
        ``parent``: the referenced entity contains this one (a finding's exam).
        ``child``: this entity contains the referenced one (an exam's registry
        entries). ``association``: neither contains the other (linked exams).
    many : bool
        Whether the field is a set of keys.
    """

    field: str
    kind: str
    role: str = "parent"
    many: bool = False


class MutableEntity:
    """Base class for Patient, Exam, Finding, Procedure, Pathology,
    CancerRegistryEntry, MammogramImage and RegionOfInterest.

    An entity belongs to at most one graph (``entity.graph``). Assigning or
    updating a key, reference or source-alias field of a registered entity goes
    through the graph, which keeps its indexes and every dependent key coherent;
    other attributes, including consumer-defined ones, are plain attributes.
    An entity without a graph has no relationships.

    Subclasses set ``kind``, ``__key_fields__`` and ``_references``.
    """

    kind: ClassVar[str] = ""
    """Registry kind, such as ``"exam"``."""
    __key_fields__: ClassVar[Tuple[str, ...]] = ()
    _references: ClassVar[Tuple[Reference, ...]] = ()
    _alias_fields: ClassVar[FrozenSet[str]] = frozenset()

    def __init__(self) -> None:
        object.__setattr__(self, "_graph", None)

    # -- graph integration -------------------------------------------------

    @classmethod
    def _indexed_fields(cls) -> FrozenSet[str]:
        """Fields whose change requires the graph to update its indexes."""

        return frozenset(cls.__key_fields__) | {ref.field for ref in cls._references} | cls._alias_fields

    def __setattr__(self, name: str, value: Any) -> None:
        graph = self.__dict__.get("_graph")
        if graph is not None and name in self._indexed_fields():
            graph.update(self, **{name: value})
        else:
            self._assign(name, value)

    def _assign(self, name: str, value: Any) -> None:
        """Store a value after the subclass coercion hook; used by the graph."""

        object.__setattr__(self, name, self._coerce(name, value))

    def _coerce(self, name: str, value: Any) -> Any:
        """Normalize a value before storage; subclasses override per field."""

        return value

    def _prepare_update(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Add derived field changes to a requested update; default none."""

        return values

    def _renamed_reference(self, field: str) -> Dict[str, Any]:
        """Extra changes when a referenced entity is rekeyed; default none."""

        return {}

    def _scope_patient_id(self) -> Optional[str]:
        """Patient this entity belongs to by its own identity, when not contained.

        Registry entries, procedures and pathology name their patient in their
        key, so a patient partition or move carries them even when no exam
        reaches them. Contained kinds return None.
        """

        return None

    @property
    def graph(self) -> Optional["DatasetGraph"]:
        """The owning DatasetGraph, or None for an entity without relationships."""

        return self.__dict__.get("_graph")

    @property
    def key(self) -> Hashable:
        """Registry key: the single key field's value, or a tuple of them."""

        return self._key_with({})

    def _key_with(self, overrides: Mapping[str, Any]) -> Hashable:
        values = tuple(overrides.get(name, getattr(self, name)) for name in self.__key_fields__)
        return values[0] if len(values) == 1 else values

    def update(self: _EntitySelf, **values: Any) -> _EntitySelf:
        """Set fields in place and return this same object.

        Parameters
        ----------
        **values
            Field names, including consumer-defined attributes, to new values.
            A registered entity delegates to its graph, which rejects a key
            collision before changing anything and rewrites the keys stored by
            related entities. No quality validation runs.

        Returns
        -------
        MutableEntity
            ``self``, with its concrete type.
        """

        graph = self.graph
        if graph is not None:
            graph.update(self, **values)
        else:
            for name, value in self._prepare_update(dict(values)).items():
                self._assign(name, value)
        return self

    def rekey(self: _EntitySelf, **identifiers: Any) -> _EntitySelf:
        """Change key fields; like ``update`` but accepts only ``__key_fields__``.

        Raises
        ------
        TypeError
            A name is not a key field.
        ValueError
            The new key is taken by another entity in the graph.
        """

        unknown = set(identifiers).difference(self.__key_fields__)
        if unknown:
            raise TypeError("rekey() accepts only key fields: " + ", ".join(self.__key_fields__))
        return self.update(**identifiers)

    def descendants(self) -> Tuple["MutableEntity", ...]:
        """Entities this one contains, directly or indirectly, once each.

        An entity without a graph has none.
        """

        graph = self.graph
        return graph.descendants(self) if graph is not None else ()

    def __deepcopy__(self, memo: Dict[int, Any]) -> "MutableEntity":
        """Copy every attribute except graph membership; the copy has no graph."""

        existing = memo.get(id(self))
        if existing is not None:
            return existing
        result = self.__class__.__new__(self.__class__)
        memo[id(self)] = result
        object.__setattr__(result, "_graph", None)
        for name, value in self.__dict__.items():
            if name != "_graph":
                object.__setattr__(result, name, copy.deepcopy(value, memo))
        return result

    # -- serialization -----------------------------------------------------

    def _to_dict_data(self) -> Dict[str, Any]:
        """Return the fields ``to_dict`` exports; subclasses override."""

        return {name: getattr(self, name) for name in self.__key_fields__}

    def to_dict(self) -> Dict[str, Any]:
        """Return this entity's fields as JSON-compatible values.

        Related entities appear as their keys, not nested objects. Consumer
        attributes are not exported. This is an export, not a round trip.
        """

        return {name: plain_value(value) for name, value in self._to_dict_data().items()}


def readonly_mapping(values: Optional[Mapping[Any, Any]] = None) -> Mapping[Any, Any]:
    """Return a shallow read-only copy of a mapping."""

    return MappingProxyType(dict(values or {}))


def plain_value(value: Any) -> Any:
    """Convert enums, dataclasses, collections and ``to_dict`` values to JSON types.

    Sets are sorted by ``repr`` so output is deterministic.
    """

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {plain_value(key): plain_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        items = list(value)
        if isinstance(value, (set, frozenset)):
            items.sort(key=repr)
        return [plain_value(item) for item in items]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict) and not isinstance(value, (str, bytes, type)):
        return plain_value(to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: plain_value(getattr(value, item.name)) for item in fields(value)}
    return value
