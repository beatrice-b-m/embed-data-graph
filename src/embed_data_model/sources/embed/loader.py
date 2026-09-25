"""Semantic-grain EMBED loading with mutable refresh and merge semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from numbers import Integral, Real
from typing import Any, Callable, Literal, Mapping, Optional, Sequence, Union

from embed_data_model.clinical.attributes import PatientAttributeObservation
from embed_data_model.clinical.exams import Exam
from embed_data_model.clinical.findings import (
    Finding,
    FindingNormalizationEvidence,
    FindingNormalizationWarning,
    FindingRecordType,
)
from embed_data_model.clinical.histories import (
    MedicationHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_model.clinical.interpretations import ImagingInterpretation
from embed_data_model.clinical.patients import Patient
from embed_data_model.core.anatomy import AnatomicalPosition, Quadrant
from embed_data_model.core.codes import Code, Vocabulary
from embed_data_model.core.graph import DatasetGraph
from embed_data_model.core.primitives import Laterality
from embed_data_model.core.source import Issue, IssueSeverity, SourceRef
from embed_data_model.core.tables import TableNormalizationError, TableRecord, _TableInput, iter_records
from embed_data_model.sources.embed._values import (
    cell,
    code,
    identifier,
    is_missing,
    outside_graph_issue,
    reconcile_merge,
    same as _same,
    scalar,
    text,
)
from embed_data_model.sources.embed import vocabulary
from embed_data_model.sources.embed.columns import resolve_columns
from embed_data_model.sources.embed.histories import (
    normalize_medication_history,
    normalize_procedure_history,
)
from embed_data_model.sources.embed.magview import normalize_magview_location


SourceKeySelector = Union[str, Callable[[Mapping[str, Any]], Any]]
_MISSING = object()


@dataclass(frozen=True)
class LoadReport:
    """Result of one synchronous loading invocation.

    Attributes
    ----------
    graph : DatasetGraph
        Live owning graph, identical to ``into`` when supplied to load_embed.
    issues : tuple of Issue
        Diagnostics from this invocation only, in adapter emission order. An
        empty tuple is not a guarantee of clinical completeness or validity.
    source_scope : str
        Effective physical-source label used for this invocation.

    Notes
    -----
    The report is frozen; its graph remains mutable. Run validate explicitly
    for quality checks.
    """

    graph: DatasetGraph
    """Live owning graph, identical to ``into`` when supplied to load_embed."""
    issues: tuple[Issue, ...]
    """Diagnostics from this invocation only, in adapter emission order. An empty
    tuple is not a guarantee of clinical completeness or validity.
    """
    source_scope: str
    """Effective physical-source label used for this invocation."""


@dataclass(frozen=True)
class _InputRow:
    """One materialized source mapping and optional physical diagnostics."""

    table: str
    mapping: Mapping[str, Any]
    source: Optional[SourceRef]
    ordinal: int


def load_embed(
    *,
    patients: Optional[_TableInput] = None,
    exams: Optional[_TableInput] = None,
    findings: Optional[_TableInput] = None,
    images: Optional[_TableInput] = None,
    rois: Optional[_TableInput] = None,
    hormone_history: Optional[_TableInput] = None,
    procedure_history: Optional[_TableInput] = None,
    procedures: Optional[_TableInput] = None,
    pathology: Optional[_TableInput] = None,
    magview: Optional[_TableInput] = None,
    registry: Optional[_TableInput] = None,
    into: Optional[DatasetGraph] = None,
    source_scope: Optional[str] = None,
    source_keys: Optional[Mapping[str, SourceKeySelector]] = None,
    columns: Optional[Mapping[str, Mapping[str, Optional[str]]]] = None,
    mode: Literal["refresh", "merge"] = "refresh",
    parents: Literal["create", "existing"] = "create",
) -> LoadReport:
    """Load any supported subset of EMBED tables into a mutable graph.

    Parameters
    ----------
    patients, exams, findings : iterable of mappings or DataFrame-like, optional
        Narrow clinical tables. Default None skips the grain. Each iterable is
        consumed and materialized once; rows need semantic IDs in mapped columns.
    images, rois : iterable of mappings or DataFrame-like, optional
        Image metadata and complete image-local ROI collections. Default None
        skips explicit input. Image rows can also project ROI collections.
        Missing/null ROI coordinates preserve the collection; an explicit empty
        list clears it. Explicit rois take precedence for addressed images.
    hormone_history, procedure_history : iterable of mappings or DataFrame-like, optional
        Patient-reported facts, not verified performed procedures. Default None
        skips the table. Merge of unkeyed history requires explicit record IDs.
    procedures, pathology : iterable of mappings or DataFrame-like, optional
        Performed procedures and reported pathology bundles; default None.
    magview : iterable of mappings or DataFrame-like, optional
        Wide rows projected into clinical grains and supplied associations.
        Default None. Wide and narrow projections are reconciled together.
    registry : iterable of mappings or DataFrame-like, optional
        Patient-scoped registry entries. Default None. Payload columns are
        unbound by default and must be configured explicitly.
    into : DatasetGraph or None, optional
        Existing graph to mutate in place; None creates a graph. Existing entity
        objects and consumer metadata survive refresh at matching semantic keys.
    source_scope : str or None, optional
        Non-empty diagnostic materialization label. None uses the target graph's
        scope ("in-memory" for a new graph); does not change an existing scope.
    source_keys : mapping or None, optional
        Table name to physical column name or row callback. None omits physical
        keys. These diagnose rows; neither keys, indexes nor ordinals supply
        missing clinical identity. Callback/key failures become issues.
    columns : mapping or None, optional
        Table name to semantic-field-to-column overrides. None uses
        ``sources.embed.columns.DEFAULT_COLUMNS``. Partial maps retain defaults;
        a None binding disables an optional field. Required fields cannot be
        unbound. Supported table names are the input table names.
    mode : {"refresh", "merge"}, optional
        Default "refresh" replaces bound adapter-managed scalars at addressed
        grains whose columns the rows supply, including explicit nulls; a
        column absent from every row leaves its field unchanged. "merge"
        applies non-null values; a value conflicting with another supplied
        value or with the populated graph value becomes unknown with an
        issue. Missing tables
        and unspecified descendant grains survive either mode.
    parents : {"create", "existing"}, optional
        Whether rows may add the patients and exams they address. Default
        "create" registers any that are missing, and ROI rows register the
        images they address. "existing" requires ``into`` and loads a row
        only when every patient and exam it addresses is already in the
        graph when the call starts, so loading a whole table into a subset
        graph attaches to that subset without growing it. ROI rows then
        attach only to images already present or loaded by admitted image
        rows. History, patient and registry rows are checked by patient only;
        their accession is context, not an exam they create. A row that
        addresses no patient or exam is not loaded. Skipped rows are counted
        in one INFO issue per table with code ``"rows_outside_graph"``.

    Returns
    -------
    LoadReport
        The live graph, invocation-local issues, and effective source scope.
        Loading does not automatically run quality validation.

    Raises
    ------
    TypeError
        Invalid into, source_keys or columns shape.
    ValueError
        Invalid mode or parents, ``parents="existing"`` without ``into``, or
        an invalid scope, column binding or source-key table.

    Notes
    -----
    One invocation is one complete grouped snapshot. Assemble complete semantic
    objects across stream chunks before refresh. The call is synchronous, has no
    cancellation control, and may partially mutate the graph before an exception.
    There is no row limit; memory use grows with the materialized inputs. No files
    or pixels are opened. Objects own metadata, not file resources.

    Coded values (assessment, recommendation, procedure type, pathology
    descriptors) are trimmed and uppercased before comparison and storage.

    ROI input replaces the complete addressed collection in either mode, including
    manual annotations. Save/pop manual ROIs before replacement if needed.
    Association refresh replaces supplied sets; merge unions them. Explicit null
    clears a supplied association set in refresh; absent columns preserve it.

    Examples
    --------
    >>> from embed_data_model import load_embed
    >>> report = load_embed(patients=[{"empi_anon": "P1"}])
    >>> report.graph.patient("P1").patient_id
    'P1'
    >>> report.issues
    ()

    Load a whole image table into a graph without adding exams to it:

    >>> graph = load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}]).graph
    >>> report = load_embed(
    ...     images=[
    ...         {"acc_anon": "A1", "empi_anon": "P1", "anon_dicom_path": "cohort1/P1/S/SE/I1.dcm"},
    ...         {"acc_anon": "A2", "empi_anon": "P2", "anon_dicom_path": "cohort1/P2/S/SE/I2.dcm"},
    ...     ],
    ...     into=graph,
    ...     parents="existing",
    ... )
    >>> [image.image_id for image in graph.exam("A1").images], graph.exam("A2")
    (['I1'], None)
    >>> [(issue.code, issue.context["rows"]) for issue in report.issues]
    [('rows_outside_graph', 1)]
    """

    if into is not None and not isinstance(into, DatasetGraph):
        raise TypeError("into must be a DatasetGraph or None")
    if mode not in {"refresh", "merge"}:
        raise ValueError("mode must be 'refresh' or 'merge'")
    if parents not in {"create", "existing"}:
        raise ValueError("parents must be 'create' or 'existing'")
    if parents == "existing" and into is None:
        raise ValueError("parents='existing' requires an existing graph in into")
    if source_scope is not None and (
        not isinstance(source_scope, str) or not source_scope.strip()
    ):
        raise ValueError("source_scope must be a non-empty string or None")

    column_maps = resolve_columns(columns)
    selectors = _resolve_source_keys(source_keys)
    graph = into or DatasetGraph(source_scope=source_scope)
    resolved_scope = source_scope or graph.source_scope
    issues: list[Issue] = []

    materialized = {
        table: _materialize(
            value,
            table,
            selectors[table],
            resolved_scope,
            issues,
        )
        for table, value in (
            ("patients", patients),
            ("exams", exams),
            ("findings", findings),
            ("images", images),
            ("rois", rois),
            ("hormone_history", hormone_history),
            ("procedure_history", procedure_history),
            ("procedures", procedures),
            ("pathology", pathology),
            ("magview", magview),
            ("registry", registry),
        )
    }
    if parents == "existing":
        materialized = _keep_existing_parents(materialized, graph, column_maps, issues)

    magview_rows = materialized["magview"]
    projected = _project_core_rows(magview_rows, column_maps)
    core_rows = {
        "patients": materialized["patients"] + projected["patients"],
        "exams": materialized["exams"] + projected["exams"],
        "findings": materialized["findings"] + projected["findings"],
    }
    # Source patient claims per accession, applied once after every adapter ran.
    claims: dict[str, set[str]] = {}
    _load_patients(core_rows["patients"], graph, column_maps["patients"], mode, issues)
    _load_exams(core_rows["exams"], graph, column_maps["exams"], mode, issues, claims)
    _load_findings(core_rows["findings"], graph, column_maps["findings"], mode, issues, resolved_scope, claims)

    _load_history(
        materialized["hormone_history"],
        graph,
        column_maps["hormone_history"],
        mode,
        issues,
        kind="medication",
    )
    _load_history(
        materialized["procedure_history"],
        graph,
        column_maps["procedure_history"],
        mode,
        issues,
        kind="reported_procedure",
    )

    # Source adapters share the one normalized invocation snapshot.
    from embed_data_model.sources.embed.clinical import load_clinical
    from embed_data_model.sources.embed.imaging import load_imaging

    load_clinical(
        procedures=[dict(item.mapping) for item in materialized["procedures"]],
        pathology=[dict(item.mapping) for item in materialized["pathology"]],
        magview=[dict(item.mapping) for item in materialized["magview"]],
        registry=[dict(item.mapping) for item in materialized["registry"]],
        graph=graph,
        columns=column_maps,
        mode=mode,
        issues=issues,
        claims=claims,
    )
    load_imaging(
        images=[dict(item.mapping) for item in materialized["images"]],
        rois=None if rois is None else [dict(item.mapping) for item in materialized["rois"]],
        graph=graph,
        columns=column_maps,
        mode=mode,
        issues=issues,
        claims=claims,
        create_images=parents == "create",
    )
    _apply_patient_claims(graph, claims, mode)

    return LoadReport(graph=graph, issues=tuple(issues), source_scope=resolved_scope)


def _resolve_source_keys(
    source_keys: Optional[Mapping[str, SourceKeySelector]],
) -> dict[str, Optional[SourceKeySelector]]:
    tables = (
        "patients",
        "exams",
        "findings",
        "images",
        "rois",
        "hormone_history",
        "procedure_history",
        "procedures",
        "pathology",
        "magview",
        "registry",
    )
    resolved: dict[str, Optional[SourceKeySelector]] = {table: None for table in tables}
    if source_keys is None:
        return resolved
    if not isinstance(source_keys, Mapping):
        raise TypeError("source_keys must be a mapping")
    unknown = set(source_keys).difference(resolved)
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise ValueError(f"Unknown source_keys table(s): {names}")
    for table, selector in source_keys.items():
        if not callable(selector) and not (
            isinstance(selector, str) and selector.strip()
        ):
            raise TypeError(
                f"source_keys[{table!r}] must be a non-empty column name or callable"
            )
        resolved[table] = selector
    return resolved


def _materialize(
    table: Any,
    table_name: str,
    source_key: Optional[SourceKeySelector],
    source_scope: str,
    issues: list[Issue],
) -> list[_InputRow]:
    if table is None:
        return []
    try:
        records = iter_records(table, key=source_key)
        result: list[_InputRow] = []
        for record in records:
            source = _record_source(record, source_scope, table_name)
            for table_issue in record.issues:
                issues.append(
                    Issue(
                        code=table_issue.code,
                        message=table_issue.message,
                        severity=IssueSeverity(table_issue.severity),
                        source=source,
                        context={
                            "table": table_name,
                            "ordinal": table_issue.ordinal,
                            "key_name": table_issue.key_name,
                            "raw_key": table_issue.raw_key,
                        },
                    )
                )
            result.append(
                _InputRow(
                    table=table_name,
                    mapping=dict(record.mapping),
                    source=source,
                    ordinal=record.ordinal,
                )
            )
        return result
    except TableNormalizationError as error:
        issues.append(
            Issue(
                code=error.code,
                message=str(error),
                severity=IssueSeverity.ERROR,
                context={"table": table_name, "ordinal": error.ordinal},
            )
        )
        return []


def _record_source(
    record: TableRecord,
    source_scope: str,
    table_name: str,
) -> Optional[SourceRef]:
    if record.source_key is None:
        return None
    return SourceRef(source_scope, table_name, record.source_key)


# The identity fields whose absent targets each table's rows would register.
# ROI rows address images and are scoped by the imaging adapter instead.
_CREATED_PARENTS: dict[str, tuple[str, ...]] = {
    "patients": ("patient_id",),
    "exams": ("patient_id", "accession"),
    "findings": ("patient_id", "accession"),
    "images": ("patient_id", "accession"),
    "hormone_history": ("patient_id",),
    "procedure_history": ("patient_id",),
    "procedures": ("patient_id", "accession"),
    "pathology": ("patient_id", "accession"),
    "registry": ("patient_id",),
    "magview": ("patient_id", "accession"),
}


def _keep_existing_parents(
    materialized: Mapping[str, list[_InputRow]],
    graph: DatasetGraph,
    columns: Mapping[str, Mapping[str, Optional[str]]],
    issues: list[Issue],
) -> dict[str, list[_InputRow]]:
    """Drop rows that would add a patient or exam, counting them per table.

    Membership is read once, before any adapter runs, so the rows of one call
    cannot admit each other and the outcome does not depend on table order.
    """

    result: dict[str, list[_InputRow]] = {}
    for table, rows in materialized.items():
        fields = _CREATED_PARENTS.get(table)
        if fields is None:
            result[table] = rows
            continue
        kept = [row for row in rows if _parents_present(row.mapping, table, fields, graph, columns[table])]
        if len(kept) < len(rows):
            issues.append(outside_graph_issue(table, len(rows) - len(kept)))
        result[table] = kept
    return result


def _parents_present(
    row: Mapping[str, Any],
    table: str,
    fields: Sequence[str],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
) -> bool:
    """Return whether the row addresses a patient or exam and all are present."""

    patient = _id_at(row, columns.get("patient_id")) if "patient_id" in fields else None
    if table == "images" and patient is None:
        # The imaging adapter claims the patient named by an EMBED path.
        from embed_data_model.sources.embed.imaging import _parse_embed_path

        parsed = _parse_embed_path(_id_at(row, columns.get("source_path")))
        patient = parsed["patient_id"] if parsed else None
    accession = _id_at(row, columns.get("accession")) if "accession" in fields else None
    if patient is None and accession is None:
        return False
    return (patient is None or graph.patient(patient) is not None) and (
        accession is None or graph.exam(accession) is not None
    )


def _project_core_rows(
    rows: Sequence[_InputRow],
    columns: Mapping[str, Mapping[str, Optional[str]]],
) -> dict[str, list[_InputRow]]:
    result: dict[str, list[_InputRow]] = {
        "patients": [],
        "exams": [],
        "findings": [],
    }
    for row in rows:
        for grain, identity in (
            ("patients", ("patient_id",)),
            ("exams", ("accession",)),
            ("findings", ("accession", "finding_number")),
        ):
            cmap = columns[grain]
            if _semantic_key(row.mapping, cmap, identity) is not None:
                result[grain].append(row)
    return result


def _load_patients(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
) -> None:
    """Record patient attributes per exam context and derive stable scalars.

    Patient attributes repeat on every exam row and may legitimately change
    over time. Each row contributes an observation for its exam context
    (accession and exam date); refresh replaces the observation for a supplied
    context and merge fills it. The scalar attribute keeps a value only when
    every observation of the patient agrees; otherwise consumers choose one
    with ``Patient.attribute_as_of``.
    """

    converters = {"sex": text, "race": text, "ethnicity": text, "birth_year": _birth_year_value}
    groups = _group_rows(rows, columns, ("patient_id",), "patient", issues)
    for key in sorted(groups, key=repr):
        patient = _ensure_patient(graph, key)
        date_column = columns.get("context_date")
        contexts: dict[tuple[Optional[str], Optional[date]], list[_InputRow]] = {}
        for row in groups[key]:
            context = (
                _id_at(row.mapping, columns.get("accession")),
                _date_value(row.mapping.get(date_column)) if date_column else None,
            )
            contexts.setdefault(context, []).append(row)
        touched: set[str] = set()
        for (accession, context_date), context_rows in sorted(contexts.items(), key=repr):
            fields, conflicts = _combine_fields(context_rows, columns, converters, "patient", key, issues)
            updates = _updates_for_mode(fields, conflicts, mode)
            current = {
                item.attribute: item.value
                for item in patient.attribute_observations
                if item.accession_number == accession and item.context_date == context_date
            }
            if mode == "merge":
                reconcile_merge({name: current.get(name) for name in updates}, updates, grain="patient", key=key, issues=issues)
            for attribute, value in updates.items():
                patient.add_attribute_observation(
                    PatientAttributeObservation(attribute, value, accession, context_date)
                )
                touched.add(attribute)
        scalars = {}
        for attribute in sorted(touched):
            values: list[Any] = []
            for item in patient.attribute_observations:
                if item.attribute == attribute and item.value is not None and item.value not in values:
                    values.append(item.value)
            scalars[attribute] = values[0] if len(values) == 1 else None
        if scalars:
            graph.update(patient, **scalars)


def _load_exams(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
    claims: dict[str, set[str]],
) -> None:
    groups = _group_rows(rows, columns, ("accession",), "exam", issues)
    for key in sorted(groups, key=repr):
        group = groups[key]
        exam = _ensure_exam(graph, key)
        fields, conflicts = _combine_fields(
            group,
            columns,
            {
                "exam_date": text,
                "exam_description": text,
                "density": _decoder(vocabulary.DENSITY),
                "exam_type": _decoder(vocabulary.EXAM_TYPE, uppercase=False),
                "visit_type": _decoder(vocabulary.VISIT_TYPE),
                "modality": _decoder(vocabulary.EXAM_MODALITY),
                "patient_age": _number,
            },
            "exam",
            key,
            issues,
        )
        renamed = {"exam_description": "description"}
        updates = _updates_for_mode(
            {renamed.get(name, name): value for name, value in fields.items()},
            {renamed.get(name, name): value for name, value in conflicts.items()},
            mode,
        )
        if mode == "merge":
            reconcile_merge(_current(exam, updates), updates, grain="exam", key=key, issues=issues)
        if updates:
            graph.update(exam, **updates)
        _claim_exam_from_rows(graph, exam, group, columns, claims)


def _load_findings(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
    source_scope: str,
    claims: dict[str, set[str]],
) -> None:
    groups = _group_rows(
        rows,
        columns,
        ("accession", "finding_number"),
        "finding",
        issues,
    )
    for key in sorted(groups, key=repr):
        group = groups[key]
        accession, finding_number = key
        exam = _ensure_exam(graph, accession)
        _claim_exam_from_rows(graph, exam, group, columns, claims)
        fields, conflicts = _combine_fields(
            group,
            columns,
            {
                "laterality": lambda value: Laterality.coerce(value),
                "finding_type": text,
                "assessment": _decoder(vocabulary.ASSESSMENT),
                "recommendation": _decoder(vocabulary.RECOMMENDATION),
                "record_type": text,
                "location": _raw_value,
                "depth": _raw_value,
                "distance": _raw_value,
                **{name: _decoder(table) for name, table in FINDING_DESCRIPTORS.items()},
            },
            "finding",
            key,
            issues,
        )
        laterality = _finding_laterality(fields, conflicts, group, columns)
        if laterality is Laterality.BILATERAL:
            # A supplied null side is a populated bilateral fact, so merge
            # applies it like any other supplied value.
            fields["laterality"] = laterality
        record_type = _finding_record_type(fields.get("record_type"), finding_number)
        interpretation = _interpretation(
            fields.get("assessment"),
            fields.get("recommendation"),
            _semantic_source(group),
        )
        anatomy = _finding_anatomy(
            fields,
            laterality,
            group,
            source_scope,
            key,
            issues,
        )
        source = _semantic_source(group)
        evidence = anatomy["evidence"]
        warnings = anatomy["warnings"]
        updates = {
            "laterality": laterality,
            "finding_type": fields.get("finding_type"),
            "interpretation": interpretation,
            "anatomical_position": anatomy["position"],
            "source_location_codes": anatomy["location_codes"],
            "source_depth_codes": anatomy["depth_codes"],
            "source_distance_codes": anatomy["distance_codes"],
            "normalization_evidence": evidence,
            "normalization_warnings": warnings,
            "record_type": record_type,
        }
        dependencies = {
            "interpretation": ("assessment", "recommendation"),
            "anatomical_position": ("location", "depth", "distance"),
            "normalization_evidence": ("location", "depth", "distance"),
            "normalization_warnings": ("location", "depth", "distance"),
        }
        managed_updates = {}
        for name, value in updates.items():
            semantics = dependencies.get(name, (_finding_field(name),))
            if not any(semantic in fields for semantic in semantics):
                continue
            if mode == "refresh" or any(conflicts.get(semantic) or fields.get(semantic) is not None for semantic in semantics):
                managed_updates[name] = value
        updates = managed_updates
        existing = graph.get("finding", key)
        descriptors = _finding_descriptors(existing, fields, conflicts, mode, key, issues)
        if descriptors is not None:
            updates["descriptors"] = descriptors
        if existing is not None and mode == "merge":
            scalars = {name: updates[name] for name in ("laterality", "finding_type") if name in updates}
            reconcile_merge(_current(existing, scalars), scalars, grain="finding", key=key, issues=issues)
            updates.update(scalars)
        if existing is not None and "interpretation" in updates and existing.interpretation is not None:
            # Interpretations share the finding grain; refresh their bound fields
            # without discarding a consumer's live reference or extension state.
            current = existing.interpretation
            for name in ("assessment", "recommendation"):
                if name in fields and (
                    mode == "refresh" or conflicts.get(name) or fields.get(name) is not None
                ):
                    change = {name: fields.get(name)}
                    if mode == "merge":
                        reconcile_merge(_current(current, change), change, grain="finding", key=key, issues=issues)
                    current.update(**change)
            updates["interpretation"] = current
        if existing is None:
            finding = Finding(
                accession_number=accession,
                laterality=laterality,
                finding_number=finding_number,
                finding_type=updates.get("finding_type"),
                interpretation=updates.get("interpretation"),
                anatomical_position=updates.get("anatomical_position"),
                source_location_codes=updates.get("source_location_codes", {}),
                source_depth_codes=updates.get("source_depth_codes", {}),
                source_distance_codes=updates.get("source_distance_codes", {}),
                normalization_evidence=updates.get("normalization_evidence", ()),
                descriptors=updates.get("descriptors", {}),
                normalization_warnings=updates.get("normalization_warnings", ()),
                record_type=updates.get("record_type", record_type),
                source=source,
            )
            graph.register(finding)
        elif updates:
            graph.update(existing, **updates)


def _load_history(
    rows: Sequence[_InputRow],
    graph: DatasetGraph,
    columns: Mapping[str, Optional[str]],
    mode: str,
    issues: list[Issue],
    *,
    kind: str,
) -> None:
    groups = _group_rows(rows, columns, ("patient_id",), f"{kind}_history", issues)
    normalizer = (
        normalize_medication_history
        if kind == "medication"
        else normalize_procedure_history
    )
    observation_type = (
        MedicationHistoryObservation
        if kind == "medication"
        else ProcedureHistoryObservation
    )
    for patient_id in sorted(groups, key=repr):
        patient = _ensure_patient(graph, patient_id)
        observations: list[Any] = []
        for row in groups[patient_id]:
            source = row.source
            record_id = _id_at(row.mapping, columns.get("record_id"))
            observation, row_issues = normalizer(row.mapping, columns, source, record_id=record_id)
            issues.extend(row_issues)
            if observation is not None and isinstance(observation, observation_type):
                observations.append(observation)
        if not observations and not groups[patient_id]:
            continue
        _apply_history_snapshot(
            patient,
            observations,
            kind,
            mode,
            issues,
        )


def _apply_history_snapshot(
    patient: Any,
    incoming: Sequence[Any],
    kind: str,
    mode: str,
    issues: list[Issue],
) -> None:
    current = list(patient.history_observations)
    other = [item for item in current if not _history_kind(item, kind)]
    old_facts = [item for item in current if _history_kind(item, kind) and item.record_id is None]
    keyed = {item.record_id: item for item in current if _history_kind(item, kind) and item.record_id is not None}
    incoming_groups: dict[str, list[Any]] = {}
    facts = []
    for item in incoming:
        if item.record_id is None:
            facts.append(item)
        else:
            incoming_groups.setdefault(item.record_id, []).append(item)
    managed = ("category", "medication", "context_accession", "continuous", "current", "reported_duration", "started", "stopped", "comment") if kind == "medication" else ("category", "procedure", "context_accession", "laterality", "reported_result")
    for record_id, observations in incoming_groups.items():
        target = keyed.get(record_id)
        updates: dict[str, Any] = {}
        for field in managed:
            candidates: list[tuple[Any, Any]] = []
            for observation in observations:
                value: Any = getattr(observation, field, None)
                comparable = value.to_dict() if hasattr(value, "to_dict") else value
                if value is not None and not any(_same(comparable, existing[0]) for existing in candidates):
                    candidates.append((comparable, value))
            if len(candidates) > 1:
                issues.append(Issue("conflicting_history_field", "Conflicting reported record values become unknown", context={"patient_id":patient.patient_id,"record_id":record_id,"field":field}))
                updates[field] = None
            elif candidates:
                updates[field] = candidates[0][1]
            elif mode == "refresh":
                updates[field] = None
        if target is None:
            target = observations[0]
        target.update(**updates)
        keyed[record_id] = target
    if mode == "merge":
        if facts:
            issues.append(Issue("history_merge_requires_record_id", "Unkeyed history merge requires supplied record IDs; existing facts preserved", context={"patient_id":patient.patient_id,"kind":kind}))
        facts = old_facts
    elif not facts and incoming_groups:
        facts = old_facts
    _set_history_values(patient, other + list(keyed.values()) + facts)


def _history_kind(item: Any, kind: str) -> bool:
    if kind == "medication":
        return isinstance(item, MedicationHistoryObservation)
    return isinstance(item, ProcedureHistoryObservation)


def _set_history_values(patient: Any, values: Sequence[Any]) -> None:
    patient.replace_history("medication", [item for item in values if isinstance(item, MedicationHistoryObservation)])
    patient.replace_history("procedure", [item for item in values if isinstance(item, ProcedureHistoryObservation)])


def _ensure_patient(graph: DatasetGraph, patient_id: str) -> Any:
    patient = graph.get("patient", patient_id)
    if patient is not None:
        return patient
    return graph.register(Patient(patient_id))


def _ensure_exam(graph: DatasetGraph, accession: str) -> Any:
    exam = graph.get("exam", accession)
    if exam is not None:
        return exam
    return graph.register(Exam(accession))


def _claim_exam_from_rows(
    graph: DatasetGraph,
    exam: Any,
    rows: Sequence[_InputRow],
    columns: Mapping[str, Optional[str]],
    claims_by_exam: dict[str, set[str]],
) -> None:
    patient_column = columns.get("patient_id")
    claims = {pid for pid in (_id_at(row.mapping, patient_column) for row in rows) if pid is not None}
    for patient_id in claims:
        _ensure_patient(graph, patient_id)
    claims_by_exam.setdefault(exam.accession_number, set()).update(claims)


def _apply_patient_claims(
    graph: DatasetGraph,
    claims_by_exam: Mapping[str, set[str]],
    mode: str,
) -> None:
    """Apply the patient claims one invocation supplied for each exam.

    Refresh replaces an exam's claims with this snapshot's claims, so a
    corrected source patient ID replaces the old one. Merge adds them.
    """

    for accession, claims in claims_by_exam.items():
        exam = graph.exam(accession)
        if exam is None or not claims:
            continue
        if mode == "refresh":
            graph.set_patient_claims(exam, claims)
        else:
            graph.claim_patient(exam, claims)


def _group_rows(
    rows: Sequence[_InputRow],
    columns: Mapping[str, Optional[str]],
    identity: Sequence[str],
    grain: str,
    issues: list[Issue],
) -> dict[Any, list[_InputRow]]:
    result: dict[Any, list[_InputRow]] = {}
    for row in rows:
        key = _semantic_key(row.mapping, columns, identity)
        if key is None:
            fields = ", ".join(identity)
            issues.append(
                Issue(
                    code=f"missing_{grain}_identity",
                    message=f"{grain} row has no usable semantic identity ({fields})",
                    severity=IssueSeverity.ERROR,
                    source=row.source,
                    context={"table": row.table, "ordinal": row.ordinal},
                )
            )
            continue
        result.setdefault(key, []).append(row)
    return result


def _semantic_key(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    identity: Sequence[str],
) -> Any:
    values = tuple(_id_at(row, columns.get(field)) for field in identity)
    if any(value is None for value in values):
        return None
    return values[0] if len(values) == 1 else values


def _combine_fields(
    rows: Sequence[_InputRow],
    columns: Mapping[str, Optional[str]],
    converters: Mapping[str, Callable[[Any], Any]],
    grain: str,
    key: Any,
    issues: list[Issue],
) -> tuple[dict[str, Any], dict[str, bool]]:
    values: dict[str, Any] = {}
    conflicts: dict[str, bool] = {}
    for semantic, converter in converters.items():
        physical = columns.get(semantic)
        if physical is None or not _column_supplied(rows, physical):
            # An unbound column, or one absent from every row, is not part of
            # this snapshot: refresh leaves the current value alone.
            continue
        candidates: list[Any] = []
        for row in rows:
            if physical not in row.mapping:
                continue
            raw = scalar(row.mapping.get(physical))
            if is_missing(raw):
                continue
            try:
                candidate = converter(raw)
            except (TypeError, ValueError, OverflowError, InvalidOperation):
                candidate = None
            if candidate is not None and not any(_same(candidate, item) for item in candidates):
                candidates.append(candidate)
        candidates.sort(key=repr)
        if len(candidates) > 1:
            conflicts[semantic] = True
            values[semantic] = None
            issues.append(
                Issue(
                    code=f"conflicting_{grain}_{semantic}",
                    message="Conflicting populated values became unknown",
                    severity=IssueSeverity.WARNING,
                    context={"identity": key, "field": semantic, "values": candidates},
                )
            )
        else:
            conflicts[semantic] = False
            values[semantic] = candidates[0] if candidates else None
    return values, conflicts


def _updates_for_mode(
    fields: Mapping[str, Any],
    conflicts: Mapping[str, bool],
    mode: str,
) -> dict[str, Any]:
    """Select supplied field values to apply: all in refresh, populated in merge."""

    result: dict[str, Any] = {}
    for semantic, value in fields.items():
        if mode == "refresh" or conflicts.get(semantic, False) or value is not None:
            result[semantic] = value
    return result


def _current(entity: Any, updates: Mapping[str, Any]) -> dict[str, Any]:
    """Return the entity's current values for the fields an update addresses."""

    return {name: getattr(entity, name, None) for name in updates}


def _finding_anatomy(
    fields: Mapping[str, Any],
    laterality: Laterality,
    rows: Sequence[_InputRow],
    source_scope: str,
    key: Any,
    issues: list[Issue],
) -> dict[str, Any]:
    location = fields.get("location")
    depth = fields.get("depth")
    distance_raw = fields.get("distance")
    location_codes = {"location": location} if location is not None else {}
    depth_codes = {"depth": depth} if depth is not None else {}
    distance_codes = {"distance": distance_raw} if distance_raw is not None else {}
    has_anatomy = any(value is not None for value in (location, depth, distance_raw))
    position: Optional[AnatomicalPosition] = None
    evidence: list[FindingNormalizationEvidence] = []
    warnings: list[FindingNormalizationWarning] = []
    source = _semantic_source(rows)
    if has_anatomy:
        normalized = normalize_magview_location(
            laterality=laterality,
            location_code=location,
            depth_code=depth,
        )
        position = normalized.position
        source_fields = {
            "location_code": ("location", location),
            "depth_code": ("depth", depth),
            "laterality": ("laterality", laterality.value),
        }
        for item in normalized.evidence:
            source_field, raw_value = source_fields.get(
                item.field, (item.field, item.raw_value)
            )
            evidence.append(
                FindingNormalizationEvidence(
                    source=source,
                    source_field=source_field,
                    raw_value=raw_value,
                    normalized_kind=item.normalized_kind,
                    normalized_value=item.normalized_value,
                )
            )
        for warning in normalized.warnings:
            source_field, raw_value = source_fields.get(
                warning.field or "", (warning.field or "location", warning.raw_value)
            )
            warnings.append(
                FindingNormalizationWarning(
                    source=source,
                    source_field=source_field,
                    raw_value=raw_value,
                    code=warning.code,
                    message=warning.message,
                )
            )
        for warning in normalized.warnings:
            issues.append(
                Issue(
                    code=warning.code,
                    message=warning.message,
                    severity=IssueSeverity.WARNING,
                    source=source,
                    context={"identity": key},
                )
            )
    distance: Optional[float] = None
    if distance_raw is not None:
        try:
            distance = float(distance_raw)
            if not isfinite(distance):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            issues.append(
                Issue(
                    code="invalid_finding_distance",
                    message="finding distance could not be parsed as a finite number",
                    severity=IssueSeverity.WARNING,
                    source=source,
                    context={"identity": key, "value": distance_raw},
                )
            )
        if distance is not None and distance < 0:
            # EMBED uses negative values such as -2 and -99 as undocumented
            # exceptional representations, never as physical measurements.
            # The raw code stays in source_distance_codes.
            distance = None
            issues.append(
                Issue(
                    code="exceptional_finding_distance",
                    message="negative finding distance is an exceptional source code, not a measurement",
                    severity=IssueSeverity.WARNING,
                    source=source,
                    context={"identity": key, "value": distance_raw},
                )
            )
        if distance is not None and position is None and laterality is not Laterality.UNKNOWN:
            position = AnatomicalPosition(
                laterality=laterality,
                quadrant=Quadrant(laterality=laterality),
            )
        if distance is not None and position is not None:
            position = AnatomicalPosition(
                laterality=position.laterality,
                quadrant=position.quadrant,
                clock_position=position.clock_position,
                location_category=position.location_category,
                distance_from_nipple_cm=distance,
            )
    return {
        "position": position,
        "location_codes": location_codes,
        "depth_codes": depth_codes,
        "distance_codes": distance_codes,
        "evidence": tuple(evidence),
        "warnings": tuple(warnings),
    }


def _interpretation(
    assessment: Any,
    recommendation: Any,
    source: Optional[SourceRef],
) -> Optional[ImagingInterpretation]:
    if assessment is None and recommendation is None:
        return None
    return ImagingInterpretation(
        assessment=assessment,
        recommendation=recommendation,
        sources=(source,) if source is not None else (),
    )


FINDING_DESCRIPTORS: Mapping[str, Vocabulary] = {
    "mass": vocabulary.PRESENCE,
    "asymmetry": vocabulary.PRESENCE,
    "architectural_distortion": vocabulary.PRESENCE,
    "calcification": vocabulary.PRESENCE,
    "mass_shape": vocabulary.MASS_SHAPE,
    "mass_margin": vocabulary.MASS_MARGIN,
    "mass_density": vocabulary.MASS_DENSITY,
    "calcification_morphology": vocabulary.CALCIFICATION_MORPHOLOGY,
    "calcification_distribution": vocabulary.CALCIFICATION_DISTRIBUTION,
    "calcification_number": vocabulary.CALCIFICATION_NUMBER,
    "other_finding": vocabulary.OTHER_FINDING,
    "implant_finding": vocabulary.IMPLANT_FINDING,
}
"""Finding descriptors loaded into ``Finding.descriptors``, with the vocabulary decoding each."""


def _source_code(value: Any) -> Optional[str]:
    """Return a source code as text: whole numbers as ``"2"``, other text trimmed and uppercased."""

    number = scalar(value)
    if isinstance(number, Real) and not isinstance(number, bool) and float(number).is_integer():
        return str(int(float(number)))
    return code(number)


def _decoder(table: Vocabulary, *, uppercase: bool = True) -> Callable[[Any], Optional[Code]]:
    """Return a converter that decodes a source value with ``table``.

    ``uppercase=False`` keeps the source case, for label-like codes such as the
    exam type ``"screening and diagnostic"``; the lookup ignores case either way.
    """

    return lambda value: table.decode(_source_code(value) if uppercase else text(value))


def _finding_descriptors(
    existing: Any,
    fields: Mapping[str, Any],
    conflicts: Mapping[str, bool],
    mode: str,
    key: Any,
    issues: list[Issue],
) -> Optional[dict[str, Any]]:
    """Return the finding's descriptor dict after applying supplied descriptor columns.

    Each supplied descriptor follows the refresh and merge rules separately;
    descriptors whose columns are absent stay as they are. Returns None when
    no descriptor column was supplied.
    """

    supplied = [name for name in FINDING_DESCRIPTORS if name in fields]
    if not supplied:
        return None
    current = dict(existing.descriptors) if existing is not None else {}
    incoming = _updates_for_mode({name: fields[name] for name in supplied}, conflicts, mode)
    if mode == "merge":
        reconcile_merge({name: current.get(name) for name in incoming}, incoming, grain="finding", key=key, issues=issues)
    for name, value in incoming.items():
        if value is None:
            current.pop(name, None)
        else:
            current[name] = value
    return current


def _finding_laterality(
    fields: Mapping[str, Any],
    conflicts: Mapping[str, bool],
    rows: Sequence[_InputRow],
    columns: Mapping[str, Optional[str]],
) -> Laterality:
    """Return finding side, reading a supplied null side as bilateral.

    In EMBED MagView a null finding side is equivalent to code ``B`` and
    projects to both breast sides. Only a column that is absent from every row,
    or conflicting populated values, leave the side unknown.
    """

    value = fields.get("laterality")
    if value is not None:
        return value
    if conflicts.get("laterality"):
        return Laterality.UNKNOWN
    if _column_supplied(rows, columns.get("laterality")):
        return Laterality.BILATERAL
    return Laterality.UNKNOWN


def _column_supplied(rows: Sequence[_InputRow], column: Optional[str]) -> bool:
    """Return whether any row carries ``column``, including an explicit null."""

    return column is not None and any(column in row.mapping for row in rows)


def _finding_record_type(value: Any, finding_number: str) -> FindingRecordType:
    if value is None and finding_number == "-9":
        return FindingRecordType.SYNTHETIC_CONTRALATERAL_NEGATIVE
    if value is None:
        return FindingRecordType.FINDING
    try:
        return FindingRecordType(value)
    except ValueError:
        return FindingRecordType.FINDING


def _finding_field(name: str) -> str:
    return {
        "laterality": "laterality",
        "finding_type": "finding_type",
        "interpretation": "assessment",
        "anatomical_position": "location",
        "source_location_codes": "location",
        "source_depth_codes": "depth",
        "source_distance_codes": "distance",
        "normalization_evidence": "location",
        "normalization_warnings": "location",
        "record_type": "record_type",
    }.get(name, name)


def _semantic_source(rows: Sequence[_InputRow]) -> Optional[SourceRef]:
    """Return the first physical source reference among a grain's rows."""

    for row in rows:
        if row.source is not None:
            return row.source
    return None


def _id_at(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    """Return the normalized identifier in a bound column of a row, or None."""

    return identifier(cell(row, column))


def _raw_value(value: Any) -> Any:
    return None if is_missing(value) else scalar(value)


def _number(value: Any) -> Optional[float]:
    """Return a finite number (whole numbers as int), or None when not numeric."""

    value = scalar(value)
    if is_missing(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _birth_year_value(value: Any) -> Optional[int]:
    value = scalar(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric = float(value)
        return int(numeric) if isfinite(numeric) and numeric.is_integer() else None
    if isinstance(value, str):
        try:
            decimal_numeric = Decimal(value.strip())
        except InvalidOperation:
            return None
        return int(decimal_numeric) if decimal_numeric.is_finite() and decimal_numeric == decimal_numeric.to_integral() else None
    return None


def _date_value(value: Any) -> Optional[date]:
    value = scalar(value)
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        try:
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


__all__ = ["LoadReport", "load_embed"]
