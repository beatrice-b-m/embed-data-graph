"""DatasetGraph: owns entities and resolves the keys they store into objects."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Hashable,
    Iterable,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    TypeVar,
    overload,
)

from embed_data_model.core.entity import MutableEntity, Reference
from embed_data_model.core.source import UnresolvedReference

if TYPE_CHECKING:
    from embed_data_model.clinical.exams import Exam
    from embed_data_model.clinical.findings import Finding
    from embed_data_model.clinical.pathology import CancerRegistryEntry, Pathology
    from embed_data_model.clinical.patients import Patient
    from embed_data_model.clinical.procedures import Procedure, ProcedureIdentity
    from embed_data_model.core.selection import Selection
    from embed_data_model.core.validation import ValidationResult
    from embed_data_model.imaging.images import MammogramImage
    from embed_data_model.imaging.rois import RegionOfInterest

_EntityT = TypeVar("_EntityT", bound=MutableEntity)

KINDS = ("patient", "exam", "finding", "procedure", "pathology", "registry", "image", "roi")
"""Registry kinds, one per entity class."""

Level = Literal["patient", "exam", "finding", "procedure", "pathology", "registry", "image", "roi"]


class DatasetGraph:
    """Owns entities, resolves their key references and keeps lookup indexes.

    Entities store the keys of related entities (a finding stores its exam's
    accession). The graph resolves those keys through indexes, so entities can
    be registered in any order and a relationship appears as soon as both ends
    are present. A key whose target is absent is reported by
    ``unresolved_references`` rather than rejected.

    Parameters
    ----------
    source_scope : str or None, optional
        Default label for SourceRef diagnostics created by loads into this
        graph. None or empty means ``"in-memory"``.

    Attributes
    ----------
    unresolved_records : dict
        Source payload snapshots whose clinical identity could not be resolved,
        keyed by the attachment the adapter could establish. They are not
        entities or inferred events.

    Notes
    -----
    Lookups return live objects or None. Collection properties are tuples in
    registration order; a rekeyed entity moves to the end. The graph opens no
    files and owns no pixels.

    Examples
    --------
    >>> from embed_data_model import DatasetGraph, Exam, Finding
    >>> graph = DatasetGraph()
    >>> finding = graph.register(Finding("A1", "L", "1"))
    >>> exam = graph.register(Exam("A1"))
    >>> exam.findings == (finding,)
    True
    """

    def __init__(self, source_scope: Optional[str] = None) -> None:
        self.source_scope = source_scope or "in-memory"
        self._entities: Dict[str, Dict[Hashable, Any]] = {kind: {} for kind in KINDS}
        self._referrers: Dict[Tuple[str, Hashable], Dict[Tuple[int, str], MutableEntity]] = defaultdict(dict)
        self._aliases: Dict[str, Dict[Hashable, MutableEntity]] = defaultdict(dict)
        self._context: Set[int] = set()
        self.unresolved_records: Dict[Any, Any] = {}

    # -- registries ----------------------------------------------------------

    def _values(self, kind: str) -> Tuple[Any, ...]:
        return tuple(self._entities[kind].values())

    @property
    def patients(self) -> Tuple[Patient, ...]:
        """Registered patients in registration order."""
        return self._values("patient")

    @property
    def exams(self) -> Tuple[Exam, ...]:
        """Registered exams in registration order."""
        return self._values("exam")

    @property
    def findings(self) -> Tuple[Finding, ...]:
        """Registered findings in registration order."""
        return self._values("finding")

    @property
    def procedures(self) -> Tuple[Procedure, ...]:
        """Registered procedures in registration order."""
        return self._values("procedure")

    @property
    def pathology(self) -> Tuple[Pathology, ...]:
        """Registered pathology bundles in registration order."""
        return self._values("pathology")

    @property
    def registry_entries(self) -> Tuple[CancerRegistryEntry, ...]:
        """Registered cancer-registry entries in registration order."""
        return self._values("registry")

    @property
    def images(self) -> Tuple[MammogramImage, ...]:
        """Registered images in registration order."""
        return self._values("image")

    @property
    def rois(self) -> Tuple[RegionOfInterest, ...]:
        """Registered regions of interest in registration order."""
        return self._values("roi")

    @overload
    def get(self, kind: Literal["patient"], key: Any) -> Optional[Patient]: ...
    @overload
    def get(self, kind: Literal["exam"], key: Any) -> Optional[Exam]: ...
    @overload
    def get(self, kind: Literal["finding"], key: Any) -> Optional[Finding]: ...
    @overload
    def get(self, kind: Literal["procedure"], key: Any) -> Optional[Procedure]: ...
    @overload
    def get(self, kind: Literal["pathology"], key: Any) -> Optional[Pathology]: ...
    @overload
    def get(self, kind: Literal["registry"], key: Any) -> Optional[CancerRegistryEntry]: ...
    @overload
    def get(self, kind: Literal["image"], key: Any) -> Optional[MammogramImage]: ...
    @overload
    def get(self, kind: Literal["roi"], key: Any) -> Optional[RegionOfInterest]: ...
    @overload
    def get(self, kind: str, key: Any) -> Any: ...

    def get(self, kind: str, key: Any) -> Any:
        """Return the entity of ``kind`` with exactly ``key``, or None.

        Raises
        ------
        KeyError
            ``kind`` is not one of the eight registry kinds.
        """

        return self._entities[kind].get(key)

    def patient(self, patient_id: str) -> Optional[Patient]:
        """Return the patient with ``patient_id``, or None."""
        return self.get("patient", patient_id)

    def exam(self, accession: str) -> Optional[Exam]:
        """Return the exam with ``accession``, or None."""
        return self.get("exam", accession)

    def finding(self, accession: str, finding_number: Any) -> Optional[Finding]:
        """Return the finding ``(accession, str(finding_number))``, or None."""
        return self.get("finding", (accession, str(finding_number)))

    def procedure(self, identity: ProcedureIdentity) -> Optional[Procedure]:
        """Return the procedure with this ProcedureIdentity, or None."""
        return self.get("procedure", identity)

    def image(self, image_id: str) -> Optional[MammogramImage]:
        """Return the image with model ``image_id``, or None."""
        return self.get("image", image_id)

    def roi(self, image_id: str, roi_key: Any) -> Optional[RegionOfInterest]:
        """Return the ROI ``(image_id, str(roi_key))``, or None."""
        return self.get("roi", (image_id, str(roi_key)))

    def registry_entry(self, patient_id: str, registry_id: Any) -> Optional[CancerRegistryEntry]:
        """Return the registry entry ``(patient_id, str(registry_id))``, or None."""
        return self.get("registry", (patient_id, str(registry_id)))

    def source_image(self, sop_uid: str) -> Optional[MammogramImage]:
        """Return the original (non-derived) image with this source SOP UID, or None."""
        return self._aliases["sop"].get(sop_uid)  # type: ignore[return-value]

    def image_at_path(self, path: str) -> Optional[MammogramImage]:
        """Return the original image with this source path alias, or None."""
        return self._aliases["path"].get(path)  # type: ignore[return-value]

    def roi_at_source(self, path: str, position: int) -> Optional[RegionOfInterest]:
        """Return the ROI at a zero-based position of a source path's collection.

        The original image with that path is searched first; otherwise an ROI
        whose own ``source_path`` matches is returned. None when nothing matches.
        """

        image = self.image_at_path(path)
        if image is not None:
            for candidate in image.rois:
                if candidate.collection_position == position:
                    return candidate
        return self._aliases["roi_source"].get((path, position))  # type: ignore[return-value]

    # -- structure -----------------------------------------------------------

    @staticmethod
    def _targets(entity: MutableEntity, ref: Reference) -> Tuple[Hashable, ...]:
        value = getattr(entity, ref.field, None)
        if ref.many:
            return tuple(value or ())
        return () if value is None else (value,)

    @staticmethod
    def _reference(entity: MutableEntity, field: str) -> Reference:
        for ref in entity._references:
            if ref.field == field:
                return ref
        raise KeyError(field)

    def _referenced(self, entity: MutableEntity, role: str) -> List[MutableEntity]:
        found = []
        for ref in entity._references:
            if ref.role == role:
                for target in self._targets(entity, ref):
                    obj = self._entities[ref.kind].get(target)
                    if obj is not None:
                        found.append(obj)
        return found

    def _referring(self, entity: MutableEntity, role: str, field: Optional[str] = None) -> List[MutableEntity]:
        found = []
        for (_, name), referrer in self._referrers.get((entity.kind, entity.key), {}).items():
            if (field is None or name == field) and self._reference(referrer, name).role == role:
                found.append(referrer)
        return found

    def children(self, entity: MutableEntity, kind: Optional[str] = None) -> Tuple[Any, ...]:
        """Entities that ``entity`` directly contains, optionally of one kind."""

        found = _unique([*self._referring(entity, "parent"), *self._referenced(entity, "child")])
        return tuple(item for item in found if kind is None or item.kind == kind)

    def parents(self, entity: MutableEntity, kind: Optional[str] = None) -> Tuple[Any, ...]:
        """Entities that directly contain ``entity``, optionally of one kind."""

        found = _unique([*self._referenced(entity, "parent"), *self._referring(entity, "child")])
        return tuple(item for item in found if kind is None or item.kind == kind)

    def descendants(self, entity: MutableEntity) -> Tuple[MutableEntity, ...]:
        """Entities ``entity`` contains directly or indirectly, once each."""

        return self._walk(entity, self.children)

    def ancestors(self, entity: MutableEntity) -> Tuple[MutableEntity, ...]:
        """Entities that contain ``entity`` directly or indirectly, once each."""

        return self._walk(entity, self.parents)

    @staticmethod
    def _walk(entity: MutableEntity, step: Callable[[MutableEntity], Tuple[Any, ...]]) -> Tuple[MutableEntity, ...]:
        seen = {id(entity)}
        result: List[MutableEntity] = []
        pending = list(reversed(step(entity)))
        while pending:
            current = pending.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            result.append(current)
            pending.extend(reversed(step(current)))
        return tuple(result)

    def linked_exams(self, exam: Exam) -> Tuple[Exam, ...]:
        """Exams linked to ``exam`` from either side, present in this graph.

        A link is symmetric: it counts whether ``exam`` lists the other
        accession or the other exam lists this one.
        """

        return tuple(
            _unique([*self._referenced(exam, "association"), *self._referring(exam, "association", "linked_accessions")])
        )

    @property
    def unresolved_references(self) -> Tuple[UnresolvedReference, ...]:
        """Stored keys whose target entity is not registered, in no set order."""

        result = []
        for kind in KINDS:
            for entity in self._entities[kind].values():
                for ref in entity._references:
                    for target in self._targets(entity, ref):
                        if target not in self._entities[ref.kind]:
                            result.append(
                                UnresolvedReference(kind, str(entity.key), ref.kind, str(target), "missing endpoint")
                            )
        return tuple(result)

    # -- indexing ------------------------------------------------------------

    def _index(self, entity: MutableEntity) -> None:
        self._entities[entity.kind][entity.key] = entity
        object.__setattr__(entity, "_graph", self)
        for ref in entity._references:
            for target in self._targets(entity, ref):
                self._referrers[(ref.kind, target)][(id(entity), ref.field)] = entity
        for index, alias, _ in _aliases(entity, {}):
            self._aliases[index][alias] = entity

    def _unindex(self, entity: MutableEntity) -> None:
        registry = self._entities[entity.kind]
        if registry.get(entity.key) is entity:
            del registry[entity.key]
        for ref in entity._references:
            for target in self._targets(entity, ref):
                referrers = self._referrers.get((ref.kind, target))
                if referrers is not None:
                    referrers.pop((id(entity), ref.field), None)
                    if not referrers:
                        del self._referrers[(ref.kind, target)]
        for index, alias, _ in _aliases(entity, {}):
            if self._aliases[index].get(alias) is entity:
                del self._aliases[index][alias]

    def _check_available(self, planned: Dict[int, Tuple[MutableEntity, Dict[str, Any]]]) -> None:
        """Reject planned keys or unique aliases that another entity holds."""

        claimed: Dict[Tuple[str, Hashable], MutableEntity] = {}
        for entity, overrides in planned.values():
            address = (entity.kind, entity._key_with(overrides))
            try:
                occupant = self._entities[entity.kind].get(address[1])
            except TypeError as exc:
                raise ValueError(f"Key must be hashable: {address!r}") from exc
            if occupant is not None and occupant is not entity and id(occupant) not in planned:
                raise ValueError(f"Distinct objects cannot share key {address!r}")
            if claimed.setdefault(address, entity) is not entity:
                raise ValueError(f"Distinct objects cannot share key {address!r}")
            for index, alias, unique in _aliases(entity, overrides):
                if not unique:
                    continue
                holder = self._aliases[index].get(alias)
                if holder is not None and holder is not entity and id(holder) not in planned:
                    raise ValueError(f"Source {index} collision: {alias!r}")
                if claimed.setdefault((index, alias), entity) is not entity:
                    raise ValueError(f"Source {index} collision: {alias!r}")

    def _add(self, entities: Iterable[MutableEntity]) -> None:
        additions = list(entities)
        self._check_available({id(entity): (entity, {}) for entity in additions})
        for entity in additions:
            self._index(entity)

    def _require_member(self, entity: MutableEntity) -> None:
        if getattr(entity, "graph", None) is not self:
            raise ValueError("Entity does not belong to this graph")

    # -- membership ----------------------------------------------------------

    def register(self, entity: _EntityT) -> _EntityT:
        """Add an entity, moving it and everything it contains from another graph.

        Parameters
        ----------
        entity : MutableEntity
            Any of the eight entity types; subclasses are preserved.

        Returns
        -------
        MutableEntity
            The same object, now owned by this graph.

        Raises
        ------
        ValueError
            An entity to be added has a key or source SOP UID already held by
            a different object here. Nothing moves in that case.

        Notes
        -----
        Moving follows ``pop``: contained entities move with it, and a
        contained entity that another entity outside the moved set also
        contains is copied instead of moved.
        """

        if entity.graph is self:
            return entity
        if entity.kind not in self._entities:
            raise TypeError(f"Unsupported entity: {type(entity).__name__}")
        source = entity.graph
        if source is None:
            self._add([entity])
            return entity
        members: Tuple[MutableEntity, ...] = (entity, *source.descendants(entity))
        self._check_available({id(member): (member, {}) for member in members})
        self._add(source._extract(entity))
        return entity

    def pop(self, entity: _EntityT) -> _EntityT:
        """Remove an entity and everything it contains into a new graph.

        Contained entities move with it and keep their Python identity. A
        contained entity that is also contained by something staying here, such
        as a procedure attached to findings of two exams, stays here and is
        deep-copied into the new graph. Keys that point back into this graph
        stay as unresolved references in the new one.

        Returns
        -------
        MutableEntity
            The same object; ``entity.graph`` is the new DatasetGraph.

        Raises
        ------
        ValueError
            ``entity`` belongs to another graph, or a shared entity cannot be
            deep-copied.
        """

        self._require_member(entity)
        extracted = self._extract(entity)
        DatasetGraph(source_scope=self.source_scope)._add(extracted)
        return entity

    def _extract(self, entity: MutableEntity) -> List[MutableEntity]:
        """Unindex ``entity`` and its exclusive descendants; copy shared ones."""

        members = [entity, *self.descendants(entity)]
        member_ids = {id(member) for member in members}
        copied: Set[int] = set()
        for member in members[1:]:
            if id(member) not in copied and any(id(parent) not in member_ids for parent in self.parents(member)):
                copied.add(id(member))
                copied.update(id(item) for item in self.descendants(member))
        memo: Dict[int, Any] = {}
        try:
            clones = [deepcopy(member, memo) for member in members if id(member) in copied]
        except Exception as exc:
            raise ValueError("Shared state cannot be independently copied; provide __deepcopy__") from exc
        moving = [member for member in members if id(member) not in copied]
        for member in moving:
            self._unindex(member)
            object.__setattr__(member, "_graph", None)
        return moving + clones

    def remove(self, entity: MutableEntity) -> None:
        """Drop one entity from the graph without touching what it contains.

        Entities that stored its key keep it as an unresolved reference.
        """

        self._require_member(entity)
        self._unindex(entity)
        object.__setattr__(entity, "_graph", None)

    # -- relationships ---------------------------------------------------------

    @staticmethod
    def _link(parent: MutableEntity, child: MutableEntity) -> Tuple[MutableEntity, Reference]:
        for ref in child._references:
            if ref.role == "parent" and ref.kind == parent.kind:
                return child, ref
        for ref in parent._references:
            if ref.role == "child" and ref.kind == child.kind:
                return parent, ref
        raise TypeError(f"Unsupported containment relationship: {parent.kind} -> {child.kind}")

    def attach(self, parent: MutableEntity, child: _EntityT) -> _EntityT:
        """Make ``parent`` contain ``child``, registering or moving both as needed.

        The child's reference to the parent is set (or added, for a set of
        references). Supported pairs: patient/exam, exam/finding, exam/image,
        exam/procedure, exam/pathology, exam/registry entry, finding/procedure,
        finding/pathology, procedure/pathology and image/ROI.

        Raises
        ------
        TypeError
            The pair is not a supported containment.
        ValueError
            The child already references a different parent in a single-valued
            field, such as a finding with another accession.
        """

        holder, ref = self._link(parent, child)
        target = child.key if holder is parent else parent.key
        if not ref.many:
            current = getattr(holder, ref.field)
            if current is not None and current != target:
                raise ValueError(f"{holder.kind} {ref.field} must match {parent.kind if holder is child else child.kind}")
        self.register(parent)
        self.register(child)
        if ref.many:
            self.update(holder, **{ref.field: {*getattr(holder, ref.field), target}})
        elif getattr(holder, ref.field) is None:
            self.update(holder, **{ref.field: target})
        return child

    def detach(self, parent: MutableEntity, child: _EntityT) -> _EntityT:
        """Remove the containment of ``child`` by ``parent``; both stay registered.

        Raises
        ------
        ValueError
            An endpoint belongs elsewhere, or the reference is part of the
            child's key (a finding's accession, an ROI's image); pop the child
            or rekey it instead.
        TypeError
            The pair is not a supported containment.
        """

        self._require_member(parent)
        self._require_member(child)
        holder, ref = self._link(parent, child)
        target = child.key if holder is parent else parent.key
        if ref.many:
            self.update(holder, **{ref.field: set(getattr(holder, ref.field)) - {target}})
        elif ref.field in holder.__key_fields__:
            raise ValueError(f"{holder.kind}.{ref.field} is part of its key; pop or rekey it instead")
        elif getattr(holder, ref.field) == target:
            self.update(holder, **{ref.field: None})
        return child

    def claim_patient(self, exam: Exam, patient_ids: Iterable[str]) -> None:
        """Add source patient claims to an exam and reconcile its owner.

        A single distinct claim makes that patient the owner; conflicting claims
        leave the exam unowned. An owner chosen with ``assign_patient`` persists.
        """

        self.set_patient_claims(exam, set(exam.asserted_patient_ids) | set(patient_ids))

    def set_patient_claims(self, exam: Exam, patient_ids: Iterable[str]) -> None:
        """Replace an exam's source patient claims and reconcile its owner.

        This replaces every claim, whichever table supplied it; ``load_embed``
        refresh replaces only the claims of the tables it loads. Ownership
        chosen with ``assign_patient`` persists.
        """

        self._require_member(exam)
        claims = set(patient_ids)
        changes: Dict[str, Any] = {"asserted_patient_ids": claims, "_owner_explicit": exam.owner_explicit}
        if not exam.owner_explicit:
            changes["patient_id"] = next(iter(claims)) if len(claims) == 1 else None
        self.update(exam, **changes)

    def assign_patient(self, exam: Exam, patient_id: Optional[str]) -> None:
        """Choose an exam's owning patient explicitly, or None for no owner.

        The choice persists across reloads and does not change the source
        claims in ``asserted_patient_ids``. The patient need not exist yet.
        """

        self._require_member(exam)
        self.update(exam, patient_id=patient_id, _owner_explicit=True)

    def set_linked_accessions(self, exam: Exam, accessions: Iterable[str], *, merge: bool = False) -> None:
        """Replace (or with ``merge=True``, extend) the accessions ``exam`` links to.

        Linked exams belong to the same imaging episode, never prior or
        follow-up exams. Links are symmetric when read; targets are never
        deleted and missing targets resolve when registered.
        """

        values = set(accessions) | (set(exam.linked_accessions) if merge else set())
        self.update(exam, linked_accessions=values)

    def set_registry_assignments(self, exam: Exam, keys: Iterable[Tuple[str, str]], *, merge: bool = False) -> None:
        """Replace (or with ``merge=True``, extend) an exam's registry assignments.

        Keys are ``(patient_id, registry_id)``; entries are never deleted and
        missing entries resolve when registered.
        """

        values = set(keys) | (set(exam.registry_references) if merge else set())
        self.update(exam, registry_references=values)

    # -- mutation ------------------------------------------------------------

    def update(self, entity: _EntityT, **values: Any) -> _EntityT:
        """Change fields of a registered entity in place, keeping indexes coherent.

        Parameters
        ----------
        entity : MutableEntity
            Entity owned by this graph.
        **values
            Field names, including consumer attributes, to new values.

        Returns
        -------
        MutableEntity
            The same object.

        Raises
        ------
        ValueError
            ``entity`` belongs elsewhere, or a new key or original-image source
            SOP UID is held by another entity. Nothing changes in that case.

        Notes
        -----
        A key change is propagated: every entity that stored the old key now
        stores the new one, and entities whose own key includes it (a finding
        under a rekeyed exam) are rekeyed too, after checking all of them for
        collisions. No quality validation runs.
        """

        self._require_member(entity)
        prepared = entity._prepare_update({name: entity._coerce(name, value) for name, value in values.items()})
        if not entity._indexed_fields().intersection(prepared):
            for name, value in prepared.items():
                object.__setattr__(entity, name, value)
            return entity
        plan = self._plan(entity, prepared)
        self._check_available(plan)
        for member, _ in plan.values():
            self._unindex(member)
        for member, changes in plan.values():
            for name, value in changes.items():
                object.__setattr__(member, name, value)
        for member, _ in plan.values():
            self._index(member)
        return entity

    def rekey(self, entity: _EntityT, **identifiers: Any) -> _EntityT:
        """Change key fields of a registered entity; see ``update``.

        Raises
        ------
        TypeError
            A name is not one of the entity's key fields.
        """

        unknown = set(identifiers).difference(entity.__key_fields__)
        if unknown:
            raise TypeError("rekey() accepts only key fields: " + ", ".join(entity.__key_fields__))
        return self.update(entity, **identifiers)

    def _plan(self, entity: MutableEntity, values: Dict[str, Any]) -> Dict[int, Tuple[MutableEntity, Dict[str, Any]]]:
        """Collect the field changes a key change implies for referring entities."""

        plan: Dict[int, Tuple[MutableEntity, Dict[str, Any]]] = {id(entity): (entity, dict(values))}
        pending = [entity]
        while pending:
            current = pending.pop()
            changes = plan[id(current)][1]
            old, new = current.key, current._key_with(changes)
            if old == new:
                continue
            for (referrer_id, field), referrer in list(self._referrers.get((current.kind, old), {}).items()):
                referrer_changes = plan.setdefault(referrer_id, (referrer, {}))[1]
                ref = self._reference(referrer, field)
                base = referrer_changes.get(field, getattr(referrer, field))
                if ref.many:
                    referrer_changes[field] = {new if item == old else item for item in base}
                else:
                    referrer_changes[field] = new if base == old else base
                    for name, value in referrer._renamed_reference(field).items():
                        referrer_changes.setdefault(name, value)
                if field in referrer.__key_fields__:
                    pending.append(referrer)
        return plan

    def replace_rois(self, image: MammogramImage, rois: Iterable[RegionOfInterest]) -> None:
        """Replace an image's complete ROI collection, including manual ROIs.

        ``rois`` is consumed once; each must carry this image's ``image_id`` and
        a distinct ``roi_key``. The old ROI objects are removed from the graph.

        Raises
        ------
        ValueError
            Keys are duplicated or belong to another image.
        """

        replacement = tuple(rois)
        keys = [roi.key for roi in replacement]
        if len(set(keys)) != len(keys) or any(roi.image_id != image.image_id for roi in replacement):
            raise ValueError("Replacement requires unique image-local ROI keys")
        for old in image.rois:
            self.remove(old)
        for roi in replacement:
            self.register(roi)

    # -- selection and copies --------------------------------------------------

    @overload
    def select(self, *, level: Literal["patient"], predicate: Callable[[Patient], bool]) -> Selection[Patient]: ...
    @overload
    def select(self, *, level: Literal["exam"], predicate: Callable[[Exam], bool]) -> Selection[Exam]: ...
    @overload
    def select(self, *, level: Literal["finding"], predicate: Callable[[Finding], bool]) -> Selection[Finding]: ...
    @overload
    def select(self, *, level: Literal["procedure"], predicate: Callable[[Procedure], bool]) -> Selection[Procedure]: ...
    @overload
    def select(self, *, level: Literal["pathology"], predicate: Callable[[Pathology], bool]) -> Selection[Pathology]: ...
    @overload
    def select(
        self, *, level: Literal["registry"], predicate: Callable[[CancerRegistryEntry], bool]
    ) -> Selection[CancerRegistryEntry]: ...
    @overload
    def select(
        self, *, level: Literal["image"], predicate: Callable[[MammogramImage], bool]
    ) -> Selection[MammogramImage]: ...
    @overload
    def select(
        self, *, level: Literal["roi"], predicate: Callable[[RegionOfInterest], bool]
    ) -> Selection[RegionOfInterest]: ...

    def select(self, *, level: Level, predicate: Callable[[Any], bool]) -> Selection[Any]:
        """Return a non-owning Selection of live entities at one level.

        ``predicate`` is called once per entity in registration order; truthy
        results are included. Later changes do not re-run it.

        Raises
        ------
        ValueError
            Unknown level.
        """

        from embed_data_model.core.selection import Selection

        if level not in self._entities:
            raise ValueError("Unknown selection level: " + str(level))
        return Selection(self, level, tuple(obj for obj in self._values(level) if predicate(obj)))

    @overload
    def partition(self, *, level: Literal["patient"], key: Callable[[Patient], Any]) -> Dict[Any, DatasetGraph]: ...
    @overload
    def partition(self, *, level: Literal["exam"], key: Callable[[Exam], Any]) -> Dict[Any, DatasetGraph]: ...
    @overload
    def partition(self, *, level: Literal["finding"], key: Callable[[Finding], Any]) -> Dict[Any, DatasetGraph]: ...
    @overload
    def partition(self, *, level: Literal["procedure"], key: Callable[[Procedure], Any]) -> Dict[Any, DatasetGraph]: ...
    @overload
    def partition(self, *, level: Literal["pathology"], key: Callable[[Pathology], Any]) -> Dict[Any, DatasetGraph]: ...
    @overload
    def partition(
        self, *, level: Literal["registry"], key: Callable[[CancerRegistryEntry], Any]
    ) -> Dict[Any, DatasetGraph]: ...
    @overload
    def partition(self, *, level: Literal["image"], key: Callable[[MammogramImage], Any]) -> Dict[Any, DatasetGraph]: ...
    @overload
    def partition(self, *, level: Literal["roi"], key: Callable[[RegionOfInterest], Any]) -> Dict[Any, DatasetGraph]: ...

    def partition(self, *, level: Level, key: Callable[[Any], Any]) -> Dict[Any, DatasetGraph]:
        """Split entities of one level into independent graphs by a group key.

        Parameters
        ----------
        level : str
            Registry kind to group.
        key : callable
            Returns a hashable group key, or a list/set/frozenset of keys to place
            the entity in several groups; an empty list omits it. A tuple is one
            key.

        Returns
        -------
        dict of hashable to DatasetGraph
            One graph per group, in first-seen order. Each holds deep copies of
            the grouped entities, everything they contain, and their ancestors
            as context (``graph.is_context(entity)`` is True for those). Copies
            keep their stored keys, so a relationship to an entity outside the
            group remains an unresolved reference.

        Raises
        ------
        ValueError
            Unknown level, or consumer state that cannot be deep-copied.
        TypeError
            A group key is not hashable.
        """

        if level not in self._entities:
            raise ValueError("Unknown partition level: " + str(level))
        groups: Dict[Any, List[MutableEntity]] = {}
        for obj in self._values(level):
            result = key(obj)
            for group in result if isinstance(result, (list, set, frozenset)) else (result,):
                groups.setdefault(group, []).append(obj)
        return {group: self._copy(selected) for group, selected in groups.items()}

    def _copy(self, selected: List[MutableEntity]) -> DatasetGraph:
        members: Dict[int, MutableEntity] = {}
        for obj in selected:
            for item in (obj, *self.descendants(obj)):
                members.setdefault(id(item), item)
        context: Dict[int, MutableEntity] = {}
        for obj in selected:
            for item in self.ancestors(obj):
                if id(item) not in members:
                    context.setdefault(id(item), item)
        memo: Dict[int, Any] = {}
        try:
            copies = {marker: deepcopy(item, memo) for marker, item in {**members, **context}.items()}
        except Exception as exc:
            raise ValueError("Consumer state cannot be independently copied; provide a __deepcopy__ hook") from exc
        output = DatasetGraph(source_scope=self.source_scope)
        output._add(copies.values())
        output._context = {id(copies[marker]) for marker in context}
        addresses = {(item.kind, item.key) for item in (*members.values(), *context.values())}
        for address, payload in self.unresolved_records.items():
            if isinstance(address, tuple) and any(part in addresses for part in address if isinstance(part, tuple)):
                output.unresolved_records[deepcopy(address)] = deepcopy(payload)
        return output

    def is_context(self, entity: MutableEntity) -> bool:
        """True when ``entity`` was copied into this partition only as an ancestor."""

        return id(entity) in self._context

    def partition_by_validation(
        self,
        *,
        level: Level,
        validator: Optional[Callable[[Any], ValidationResult]] = None,
    ) -> Tuple[DatasetGraph, DatasetGraph]:
        """Partition into ``(valid, invalid)`` graphs using ``validate`` by default.

        Either graph may be empty. Copy rules match ``partition``.
        """

        from embed_data_model.core.validation import validate

        check = validator or validate
        parts = self.partition(level=level, key=lambda obj: check(obj).valid)
        return parts.get(True, DatasetGraph()), parts.get(False, DatasetGraph())

    def to_dict(self) -> Dict[str, Any]:
        """Return ``{kind: [entity.to_dict(), ...]}`` in registration order.

        Relationships appear as stored keys. This is an export, not a round trip.
        """

        return {kind: [entity.to_dict() for entity in self._entities[kind].values()] for kind in KINDS}


def _unique(items: Iterable[Any]) -> List[Any]:
    seen: Set[int] = set()
    result = []
    for item in items:
        if id(item) not in seen:
            seen.add(id(item))
            result.append(item)
    return result


def _aliases(entity: MutableEntity, overrides: Dict[str, Any]) -> Tuple[Tuple[str, Hashable, bool], ...]:
    aliases = getattr(entity, "_source_aliases", None)
    return tuple(aliases(overrides)) if aliases is not None else ()


def ensure_graph(entity: MutableEntity) -> DatasetGraph:
    """Return the entity's graph, first registering it in a new one if needed."""

    graph = entity.graph
    if graph is None:
        graph = DatasetGraph()
        graph.register(entity)
    return graph
