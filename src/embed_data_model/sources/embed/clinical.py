"""Procedures, pathology, registry entries and exam associations from EMBED rows.

Narrow ``procedures``/``pathology`` tables and wide MagView rows are grouped
together. A procedure is identified by patient, procedure date, type and biopsy
side. Pathology is identified by an explicit record ID or by the procedure it
belongs to. Rows that cannot establish an identity are kept as unresolved
payload snapshots; no row position, payload hash or date becomes an identity.
One call is one snapshot of every grain it addresses.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Hashable, Iterable, List, Mapping, Optional, Set, Tuple

from embed_data_model.clinical.exams import Exam
from embed_data_model.clinical.pathology import CancerRegistryEntry, Pathology, PathologyObservation
from embed_data_model.clinical.patients import Patient
from embed_data_model.clinical.procedures import Procedure
from embed_data_model.core.codes import Code
from embed_data_model.core.graph import DatasetGraph
from embed_data_model.core.source import Issue, IssueSeverity
from embed_data_model.sources.embed._values import Claims, cell, identifier, reconcile_merge, record_claims
from embed_data_model.sources.embed.procedures_pathology import normalize_pathology, normalize_procedure

ColumnMap = Mapping[str, Optional[str]]
Attachment = Optional[Tuple[str, Any]]

_PROCEDURE_IDENTITY_FIELDS = frozenset(
    {"patient_id", "performed_date", "procedure_date", "procedure_type", "laterality", "accession", "finding_number"}
)
_PATHOLOGY_FIELDS = ("diagnosis", "result_category", "malignant", "severity", "report_documented_date")
_REFERENCE_FIELDS = {"finding": "finding_references", "exam": "exam_references", "procedure": "procedure_references"}


@dataclass
class _Snapshot:
    """State shared by the steps of one invocation."""

    graph: DatasetGraph
    merge: bool
    issues: List[Issue]
    claims: Claims
    addressed: Set[Any] = field(default_factory=set)
    unresolved: Dict[Any, List[Dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    def keep_unresolved(self, kind: str, attachment: Attachment, row: Mapping[str, Any], reason: str) -> None:
        address = ("clinical", kind, attachment)
        self.addressed.add(address)
        self.unresolved[address].append({"payload": deepcopy(dict(row)), "attachment": attachment, "reason": reason})
        self.issues.append(Issue(reason, "Clinical record needs explicit identity", context={"attachment": attachment}))


@dataclass(frozen=True)
class _ProcedureRow:
    procedure: Procedure
    attachment: Attachment
    row: Mapping[str, Any]
    payload_columns: ColumnMap


@dataclass(frozen=True)
class _PathologyRow:
    descriptors: Tuple[PathologyObservation, ...]
    attachment: Attachment
    row: Mapping[str, Any]
    columns: ColumnMap
    explicit: bool


def load_clinical(
    *,
    procedures: List[Mapping[str, Any]],
    pathology: List[Mapping[str, Any]],
    magview: List[Mapping[str, Any]],
    registry: List[Mapping[str, Any]],
    graph: DatasetGraph,
    columns: Mapping[str, ColumnMap],
    mode: str,
    issues: List[Issue],
    claims: Claims,
) -> None:
    """Apply procedure, pathology, registry and association rows to ``graph``.

    Source patient claims are recorded in ``claims`` by accession and source
    table for the caller to apply once for the whole invocation.
    """

    if mode not in {"refresh", "merge"}:
        raise ValueError("mode must be 'refresh' or 'merge'")
    state = _Snapshot(graph, mode == "merge", issues, claims)
    procedure_rows: Dict[Hashable, List[_ProcedureRow]] = defaultdict(list)
    pathology_rows: Dict[Hashable, List[_PathologyRow]] = defaultdict(list)
    for rows, wide in ((procedures, False), (magview, True)):
        for row in rows:
            _collect_procedure(state, row, columns["procedures"], wide, procedure_rows)
    for table, rows in (("pathology", pathology), ("magview", magview)):
        for row in rows:
            _collect_pathology(state, row, table, columns["pathology"], procedure_rows, pathology_rows)
    for key, group in procedure_rows.items():
        _apply_procedure(state, key, group)
    for key, pathology_group in pathology_rows.items():
        _apply_pathology(state, key, pathology_group)
    _store_unresolved(state)
    _apply_registry(state, registry, columns["registry"])
    _apply_associations(state, magview, {**columns["exams"], **columns["magview"]})


# -- grouping ------------------------------------------------------------------


def _collect_procedure(
    state: _Snapshot,
    row: Mapping[str, Any],
    columns: ColumnMap,
    wide: bool,
    grouped: Dict[Hashable, List[_ProcedureRow]],
) -> None:
    if wide and cell(row, columns.get("performed_date")) is None and cell(row, columns.get("procedure_type")) is None:
        return  # A MagView row without procedure facts describes only a finding.
    attachment = _attachment(row, columns)
    _claim(state, row, "magview" if wide else "procedures", columns)
    state.addressed.add(("clinical", "procedure", attachment))
    procedure, _ = normalize_procedure(row, columns)
    if procedure is None:
        state.keep_unresolved("procedure", attachment, row, "incomplete_procedure_identity")
        return
    payload = {name: column for name, column in columns.items() if name not in _PROCEDURE_IDENTITY_FIELDS}
    grouped[procedure.identity].append(_ProcedureRow(procedure, attachment, row, payload))


def _collect_pathology(
    state: _Snapshot,
    row: Mapping[str, Any],
    table: str,
    columns: ColumnMap,
    procedure_rows: Dict[Hashable, List[_ProcedureRow]],
    grouped: Dict[Hashable, List[_PathologyRow]],
) -> None:
    fields, descriptors = normalize_pathology(row, columns)
    record_id = _id_at(row, columns.get("record_id"))
    if not fields and not descriptors and record_id is None:
        return
    _claim(state, row, table, columns)
    attachment = _attachment(row, columns)
    procedure, _ = normalize_procedure(row, columns)
    if procedure is not None:
        # Pathology rows also establish the procedure they were reported for.
        procedure_rows[procedure.identity].append(_ProcedureRow(procedure, attachment, row, {}))
        attachment = ("procedure", procedure.identity)
    state.addressed.add(("clinical", "pathology", attachment))
    patient_id = _id_at(row, columns.get("patient_id"))
    if record_id is not None and patient_id is not None:
        key: Hashable = (patient_id, record_id)
    elif record_id is None and procedure is not None:
        # The procedure tuple is the reliable identity; the provisional report
        # date is an attribute, never part of the key.
        key = ("procedure", procedure.identity)
    else:
        state.keep_unresolved("pathology", attachment, row, "incomplete_pathology_identity")
        return
    grouped[key].append(_PathologyRow(descriptors, attachment, row, columns, record_id is not None))


# -- applying ------------------------------------------------------------------


def _apply_procedure(state: _Snapshot, key: Hashable, group: List[_ProcedureRow]) -> None:
    graph = state.graph
    entity = graph.get("procedure", key)
    if entity is None:
        entity = graph.register(group[0].procedure)
    values, conflicts = _combine([(item.row, item.payload_columns) for item in group], state.issues, key)
    updates = _for_mode(values, conflicts, state.merge)
    if state.merge:
        reconcile_merge(_current(entity, updates), updates, grain="procedure", key=key, issues=state.issues)
    graph.update(entity, **updates)
    for item in group:
        _link(graph, "procedure", key, item.attachment)


def _apply_pathology(state: _Snapshot, key: Hashable, group: List[_PathologyRow]) -> None:
    graph = state.graph
    slots = _descriptor_slots(group)
    if not group[0].explicit and any(len(values) > 1 for values in slots.values()):
        # Rows of one procedure disagree on a descriptor slot; without a record
        # ID there is no way to tell which report is which.
        existing = graph.get("pathology", key)
        if existing is not None and not state.merge:
            graph.pop(existing)
        for item in group:
            state.keep_unresolved("pathology", item.attachment, item.row, "ambiguous_pathology_identity")
        return
    for slot, candidates in slots.items():
        if len(candidates) > 1:
            state.issues.append(
                Issue(
                    "conflicting_clinical_values",
                    "Conflicting descriptor slot becomes unknown",
                    IssueSeverity.WARNING,
                    context={"identity": key, "slot": slot, "values": candidates},
                )
            )
    scalar_columns = [
        (item.row, {name: column for name, column in item.columns.items() if name in _PATHOLOGY_FIELDS})
        for item in group
    ]
    values, conflicts = _combine(scalar_columns, state.issues, key)
    normalized, _ = normalize_pathology(values, {name: name for name in values})
    updates = {name: normalized.get(name) for name in values}
    if "severity" in values:
        updates["raw_severity"] = values["severity"]
        if "severity" in conflicts:
            conflicts.add("raw_severity")
    updates = _for_mode(updates, conflicts, state.merge)
    agreed = tuple(
        next(descriptor for item in group for descriptor in item.descriptors if descriptor.source_ordinal == slot)
        for slot in sorted(slots)
        if len(slots[slot]) == 1
    )
    entity = graph.get("pathology", key)
    if entity is None:
        graph.register(Pathology(identity=key, descriptors=agreed, **updates))
    else:
        if state.merge:
            reconcile_merge(_current(entity, updates), updates, grain="pathology", key=key, issues=state.issues)
        supplied = {
            int(name.split("_")[1])
            for item in group
            for name, column in item.columns.items()
            if name.startswith("descriptor_") and column is not None and column in item.row
        }
        if supplied:
            kept = {d.source_ordinal: d for d in entity.descriptors if state.merge or d.source_ordinal not in supplied}
            for slot, candidates in slots.items():
                if len(candidates) > 1:
                    kept.pop(slot, None)
            kept.update({descriptor.source_ordinal: descriptor for descriptor in agreed})
            updates["descriptors"] = tuple(kept[slot] for slot in sorted(kept))
        graph.update(entity, **updates)
    for item in group:
        _link(graph, "pathology", key, item.attachment)


def _store_unresolved(state: _Snapshot) -> None:
    """Replace each addressed attachment's unresolved snapshot with this call's.

    Unkeyed facts have no identity to merge by, so the latest snapshot is kept
    rather than accumulating repeated loads; merge leaves untouched ones alone.
    """

    for address in state.addressed:
        incoming = state.unresolved.get(address)
        if incoming:
            state.graph.unresolved_records[address] = incoming
        elif not state.merge:
            state.graph.unresolved_records.pop(address, None)


def _apply_registry(state: _Snapshot, rows: Iterable[Mapping[str, Any]], columns: ColumnMap) -> None:
    grouped: Dict[Tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        patient_id = _id_at(row, columns.get("patient_id"))
        registry_id = _id_at(row, columns.get("registry_id"))
        if patient_id is None or registry_id is None:
            state.issues.append(
                Issue("incomplete_registry_identity", "Registry needs patient and entry IDs", context={"payload": dict(row)})
            )
            continue
        grouped[(patient_id, registry_id)].append(row)
    payload_columns = {name: column for name, column in columns.items() if name not in {"patient_id", "registry_id"}}
    for key, group in grouped.items():
        payload, conflicts = _combine([(row, payload_columns) for row in group], state.issues, key)
        entity = state.graph.registry_entry(*key)
        if entity is None:
            state.graph.register(CancerRegistryEntry(key[0], key[1], payload=payload))
            continue
        updates = _for_mode(payload, conflicts, state.merge)
        current = dict(entity.payload)
        if state.merge:
            reconcile_merge(current, updates, grain="registry", key=key, issues=state.issues)
        state.graph.update(entity, payload={**current, **updates})


def _apply_associations(state: _Snapshot, rows: Iterable[Mapping[str, Any]], columns: ColumnMap) -> None:
    """Set each exam's linked accessions and registry assignments from MagView rows.

    Refresh replaces a supplied set and merge extends it. A column absent from
    the rows leaves the set unchanged; an explicit null clears it.
    """

    assignment_column = columns.get("registry_assignment")
    linked_column = columns.get("linked_accession")
    assignments: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    links: Dict[str, Set[str]] = defaultdict(set)
    for row in rows:
        accession = _id_at(row, columns.get("accession"))
        if accession is None:
            continue
        _claim(state, row, "magview", columns)
        if assignment_column is not None and assignment_column in row:
            patient_id = _id_at(row, columns.get("patient_id"))
            for registry_id in _identifiers(cell(row, assignment_column)):
                if patient_id is None:
                    state.issues.append(
                        Issue(
                            "incomplete_registry_assignment",
                            "Confirmed registry assignment lacks source patient",
                            context={"accession": accession, "registry_id": registry_id},
                        )
                    )
                else:
                    assignments[accession].add((patient_id, registry_id))
            assignments.setdefault(accession, set())
        if linked_column is not None and linked_column in row:
            links[accession].update(_identifiers(cell(row, linked_column)))
    for accession, keys in assignments.items():
        state.graph.set_registry_assignments(_exam(state.graph, accession), keys, merge=state.merge)
    for accession, targets in links.items():
        state.graph.set_linked_accessions(_exam(state.graph, accession), targets, merge=state.merge)


# -- helpers -------------------------------------------------------------------


def _id_at(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    """Return the normalized identifier in a bound column of a row, or None."""

    return identifier(cell(row, column))


def _identifiers(value: Any) -> List[str]:
    """Return the identifiers in a scalar or list-like cell, skipping missing ones."""

    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [normalized for normalized in (identifier(item) for item in values) if normalized is not None]


def _attachment(row: Mapping[str, Any], columns: ColumnMap) -> Attachment:
    accession = _id_at(row, columns.get("accession"))
    if accession is None:
        return None
    finding = _id_at(row, columns.get("finding_number"))
    return ("finding", (accession, finding)) if finding is not None else ("exam", accession)


def _exam(graph: DatasetGraph, accession: str) -> Exam:
    """Return the exam with this accession, registering an empty one if needed."""

    return graph.exam(accession) or graph.register(Exam(accession))


def _claim(state: _Snapshot, row: Mapping[str, Any], table: str, columns: ColumnMap) -> None:
    """Ensure the row's patient and exam exist and record its claim for ``table``."""

    accession = _id_at(row, columns.get("accession"))
    patient_id = _id_at(row, columns.get("patient_id"))
    if patient_id is not None and state.graph.patient(patient_id) is None:
        state.graph.register(Patient(patient_id))
    if accession is not None:
        _exam(state.graph, accession)
        if patient_id is not None:
            record_claims(state.claims, accession, table, (patient_id,))


def _link(graph: DatasetGraph, kind: str, key: Hashable, attachment: Attachment) -> None:
    """Add the attachment's key to the entity's reference set for that kind."""

    entity = graph.get(kind, key)
    if attachment is None or entity is None:
        return
    name = _REFERENCE_FIELDS[attachment[0]]
    current = getattr(entity, name)
    if attachment[1] not in current:
        graph.update(entity, **{name: {*current, attachment[1]}})


def _descriptor_slots(group: List[_PathologyRow]) -> Dict[int, List[Code]]:
    slots: Dict[int, List[Code]] = defaultdict(list)
    for item in group:
        for descriptor in item.descriptors:
            if descriptor.descriptor not in slots[descriptor.source_ordinal]:
                slots[descriptor.source_ordinal].append(descriptor.descriptor)
    return slots


def _combine(
    rows: Iterable[Tuple[Mapping[str, Any], ColumnMap]],
    issues: List[Issue],
    key: Any,
) -> Tuple[Dict[str, Any], Set[str]]:
    """Combine supplied columns across rows; conflicting values become None.

    Returns the combined values and the names of fields that conflicted. A
    column absent from every row is not part of the result.
    """

    grouped: Dict[str, List[Any]] = defaultdict(list)
    for row, columns in rows:
        for name, column in columns.items():
            if column is None or column not in row:
                continue
            values = grouped[name]
            value = cell(row, column)
            if value is not None and value not in values:
                values.append(value)
    result: Dict[str, Any] = {}
    conflicts: Set[str] = set()
    for name, values in grouped.items():
        result[name] = values[0] if len(values) == 1 else None
        if len(values) > 1:
            conflicts.add(name)
            issues.append(
                Issue(
                    "conflicting_clinical_values",
                    "Conflicting populated values become unknown",
                    IssueSeverity.WARNING,
                    context={"identity": key, "field": name, "values": values},
                )
            )
    return result, conflicts


def _for_mode(values: Mapping[str, Any], conflicts: Set[str], merge: bool) -> Dict[str, Any]:
    """Keep every supplied value in refresh; in merge only populated or conflicting ones."""

    return {name: value for name, value in values.items() if not merge or value is not None or name in conflicts}


def _current(entity: Any, updates: Mapping[str, Any]) -> Dict[str, Any]:
    return {name: getattr(entity, name, None) for name in updates}
