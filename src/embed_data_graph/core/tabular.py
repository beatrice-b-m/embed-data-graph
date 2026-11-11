"""Deterministic scalar projections; pandas is imported only by DataFrame calls."""
from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from embed_data_graph.core.codes import Code
from embed_data_graph.core.source import Issue, is_null_scalar

if TYPE_CHECKING:
    from pandas import DataFrame  # type: ignore[import-untyped]
    from embed_data_graph.core.graph import DatasetGraph

Scalar = Union[str, int, float, bool, datetime, None]
"""A projected cell: scalar data only, with naive UTC datetime values."""


@dataclass(frozen=True)
class TableSchema:
    """Stable schema for one projection table.

    Attributes
    ----------
    name : str
        Table name accepted by records/table.
    columns : mapping of str to str
        Ordered columns and logical types: string, integer, number, boolean,
        datetime, or scalar. All non-key columns are nullable. A fresh read-only
        mapping is returned on each call. DataFrames use nullable pandas dtypes;
        scalar columns use object dtype.
    key : tuple of str
        Unique row key. Entity keys encode semantic identity, never row order.
        Supplementary record keys identify snapshot occurrences only.
    """

    name: str
    columns: Mapping[str, str]
    key: Tuple[str, ...]


_GRAINS = {"patients": "patient", "exams": "exam", "findings": "finding",
           "procedures": "procedure", "pathology": "pathology", "registry": "registry",
           "images": "image", "rois": "roi"}
_CODES = {
    "exams": ("density", "exam_type", "visit_type", "modality"),
    "findings": ("assessment", "recommendation", "mass", "asymmetry", "architectural_distortion",
                 "calcification", "mass_shape", "mass_margin", "mass_density", "calcification_morphology",
                 "calcification_distribution", "calcification_number", "other_finding", "implant_finding"),
    "procedures": ("procedure_type",),
    "pathology": ("procedure_type", *(f"descriptor_{i}" for i in range(1, 11))),
    "registry": ("estrogen_receptor", "progesterone_receptor", "her2"),
}
_FINDING_DESCRIPTORS = tuple(name for name in _CODES["findings"] if name not in {"assessment", "recommendation"})
_FIELDS = {
    "patients": "patient_id sex race ethnicity birth_year cohort_number",
    "exams": "accession_number patient_id exam_date description patient_age location_id accession_type total_left_findings total_right_findings contested owner_explicit imaged_laterality",
    "findings": "accession_number finding_number patient_id laterality finding_type record_type quadrant_ml quadrant_si depth clock_hour location_category distance_from_nipple_cm",
    "procedures": "patient_id performed_date laterality",
    "pathology": "patient_id record_id performed_date laterality diagnosis result_category malignant severity raw_severity report_documented_date",
    "registry": "patient_id registry_id diagnosis_date laterality source_laterality histology behavior icdo3 primary_site t_stage n_stage m_stage stage_group vital_status",
    "images": "image_id accession_number patient_id source_sop_instance_uid derived_from laterality view_position modality source_modality derived_image_type height width frame_count study_instance_uid series_instance_uid coordinate_frame_id manufacturer series_description view_modifier spot_magnification source_view_position",
    "rois": "image_id roi_key accession_number patient_id source_path collection_position annotation_source confidence coordinate_frame_id source_coordinate_convention frame_provenance frame_derivation_method y_min x_min y_stop x_stop source_y_min source_x_min source_y_max source_x_max",
}
_DATES = {"exam_date", "performed_date", "diagnosis_date", "report_documented_date"}
_INTS = {"birth_year", "height", "width", "frame_count", "collection_position", "clock_hour"}
_NUMBERS = {"patient_age", "total_left_findings", "total_right_findings", "distance_from_nipple_cm",
            "confidence", "y_min", "x_min", "y_stop", "x_stop", "source_y_min", "source_x_min", "source_y_max", "source_x_max", "age_at_diagnosis"}
_BOOLS = {"contested", "owner_explicit", "malignant", "spot_magnification", "incomplete"}
_LINKS = {
    "exam_registry": ("exam", "registry_references", "registry"),
    "exam_links": ("exam", "linked_accessions", "exam"),
    "exam_patients": ("exam", "asserted_patient_ids", "patient"),
    "procedure_findings": ("procedure", "finding_references", "finding"),
    "procedure_exams": ("procedure", "exam_references", "exam"),
    "pathology_procedures": ("pathology", "procedure_references", "procedure"),
    "pathology_findings": ("pathology", "finding_references", "finding"),
    "pathology_exams": ("pathology", "exam_references", "exam"),
}


def _type(name: str) -> str:
    return ("datetime" if name in _DATES else "integer" if name in _INTS else
            "number" if name in _NUMBERS else "boolean" if name in _BOOLS else
            "scalar" if name in {"severity", "raw_severity"} else "string")


def table_schema(name: str) -> TableSchema:
    """Return a fresh ordered schema; raise ValueError for an unknown table name."""

    key: Tuple[str, ...]
    if name in _GRAINS:
        columns = {"entity_key": "string", "incomplete": "boolean"}
        columns.update({field: _type(field) for field in _FIELDS[name].split()})
        for field in _CODES.get(name, ()):
            columns.update({field: "string", field + "_meaning": "string"})
        if name == "findings":
            columns.update(source_finding_number="string")
        if name == "registry":
            columns.update(record_id="string")
        key = ("entity_key",)
    elif name in _LINKS:
        columns = {"source_key": "string", "target_key": "string"}
        key = ("source_key", "target_key")
    elif name == "values":
        columns = {"kind": "string", "entity_key": "string", "field": "string", "value": "scalar"}
        key = ("kind", "entity_key", "field")
    elif name == "unresolved":
        columns = {"record_key": "string", "address": "string", "kind": "string", "reason": "string",
                   "patient_id": "string", "accession_number": "string", "incomplete": "boolean",
                   "assessment": "string", "assessment_meaning": "string", "recommendation": "string",
                   "recommendation_meaning": "string", "performed_date": "datetime", "procedure_type": "string",
                   "procedure_type_meaning": "string", "laterality": "string", "severity": "scalar",
                   "report_documented_date": "datetime"}
        columns.update(finding_number="string", reported_laterality="string")
        columns.update({field: _type(field) for field in _FIELDS["registry"].split()})
        for field in _CODES["registry"]:
            columns.update({field: "string", field + "_meaning": "string"})
        # Later additions are appended so earlier column positions stay stable.
        columns.update(raw_severity="scalar")
        for field in _FINDING_DESCRIPTORS:
            columns.update({field: "string", field + "_meaning": "string"})
        columns.update(record_id="string")
        key = ("record_key",)
    elif name == "unresolved_values":
        columns = {"record_key": "string", "field": "string", "value": "scalar"}
        key = ("record_key", "field")
    elif name == "issues":
        columns = {"issue_key": "string", "kind": "string", "entity_key": "string", "field": "string",
                   "code": "string", "message": "string", "severity": "string", "context": "string"}
        key = ("issue_key",)
    else:
        raise ValueError("Unknown projection table: " + str(name))
    return TableSchema(name, MappingProxyType(columns), key)


def _canonical(value: Any) -> Any:
    if is_null_scalar(value):
        return ["NoneType", None]
    # Type tags prevent semantic key collisions (e.g. text '1' versus integer 1).
    if isinstance(value, Code):
        return ["code", sorted(set(value.tokens)) if value.tokens else value.code]
    if isinstance(value, Enum):
        return [type(value).__name__, _canonical(value.value)]
    if isinstance(value, (datetime, date)):
        return [type(value).__name__, value.isoformat()]
    if is_dataclass(value) and not isinstance(value, type):
        return [type(value).__name__, [[f.name, _canonical(getattr(value, f.name))] for f in fields(value)]]
    if isinstance(value, Mapping):
        return ["map", sorted([[_encode(k), _canonical(v)] for k, v in value.items()])]
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [_canonical(v) for v in value]
        if isinstance(value, (set, frozenset)):
            items.sort(key=lambda v: json.dumps(v, sort_keys=True))
        return [type(value).__name__, items]
    if value is None or isinstance(value, (str, bool, int, float)):
        return [type(value).__name__, value]
    raise TypeError("Projection requires serializable semantic keys/values, got " + type(value).__name__)


def _encode(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _scalar(value: Any) -> Scalar:
    if is_null_scalar(value):
        return None
    if isinstance(value, Enum):
        return _scalar(value.value)
    if isinstance(value, Code):
        return ",".join(sorted(set(value.tokens))) if value.tokens else value.code
    if value is None or isinstance(value, (str, bool, int, float, datetime)):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return _encode(value)


def _leaves(value: Any, path: str = "") -> Iterable[Tuple[str, Scalar]]:
    if isinstance(value, Code):
        yield path, _scalar(value)
        yield path + "_meaning", value.meaning
    elif isinstance(value, Enum):
        yield path, _scalar(value)
    elif is_dataclass(value) and not isinstance(value, type):
        for f in fields(value):
            if f.name not in {"source", "metadata", "payload"}:
                yield from _leaves(getattr(value, f.name), path + "/" + f.name)
    elif isinstance(value, Mapping):
        for k in sorted(value, key=str):
            if k not in {"metadata", "source"}:
                escaped = str(k).replace("~", "~0").replace("/", "~1")
                yield from _leaves(value[k], path + "/" + escaped)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = sorted(value, key=_encode) if isinstance(value, (set, frozenset)) else value
        for index, item in enumerate(values):
            yield from _leaves(item, path + "/" + str(index))
    else:
        yield path, _scalar(value)


def _date(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    else:
        text = str(value).strip()
        try:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                result = datetime.strptime(text, "%m/%d/%Y")
            except ValueError:
                return None
    if result.tzinfo is not None:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)
    # Keep identical records/DataFrame semantics within nanosecond pandas bounds.
    return result if datetime(1678, 1, 1) <= result < datetime(2262, 1, 1) else None


def _code_fields(row: Dict[str, Any], name: str, value: Any) -> None:
    row[name] = _scalar(value)
    row[name + "_meaning"] = value.meaning if isinstance(value, Code) else None


def _entity_row(entity: Any, table: str, graph: DatasetGraph) -> Dict[str, Any]:
    row = {field: getattr(entity, field, None) for field in _FIELDS[table].split()}
    row.update(entity_key=_encode(entity.key), incomplete=False)
    if table in {"procedures", "pathology"}:
        identity = entity.identity
        if table == "pathology" and isinstance(identity, tuple) and len(identity) == 2 and identity[0] == "procedure":
            identity = identity[1]
        if hasattr(identity, "patient_id"):
            for name in ("patient_id", "performed_date", "procedure_type", "laterality"):
                row[name] = getattr(identity, name, None)
        else:
            row["patient_id"] = entity._scope_patient_id()
            if isinstance(identity, tuple) and len(identity) == 2:
                row["record_id"] = identity[1]
    if table in {"findings", "rois"}:
        exam = entity.exam if table == "findings" else (entity.image.exam if entity.image is not None else None)
        row["patient_id"] = exam.patient_id if exam is not None else None
        if table == "rois":
            row["accession_number"] = entity.image.accession_number if entity.image is not None else None
        row["incomplete"] = exam is None or exam.patient_id is None
    if table == "exams":
        row["incomplete"] = entity.patient_id is None
    if table == "pathology":
        row["incomplete"] = row.get("performed_date") is None or row.get("laterality") is None
    if table == "images":
        row["incomplete"] = entity.accession_number is None or graph.exam(entity.accession_number) is None
    if table == "registry":
        row["record_id"] = entity.record_id
        row["diagnosis_date"] = entity.payload.get("diagnosis_date")
    if table == "findings":
        row["source_finding_number"] = entity.source_finding_number
        position = entity.anatomical_position
        if position is not None:
            row.update(quadrant_ml=position.quadrant.ml, quadrant_si=position.quadrant.si,
                       depth=position.quadrant.depth, clock_hour=position.clock_position.hour if position.clock_position else None,
                       location_category=position.location_category, distance_from_nipple_cm=position.distance_from_nipple_cm)
    for name in _CODES.get(table, ()):
        value = row.get(name, getattr(entity, name, None))
        if table == "pathology" and name.startswith("descriptor_"):
            slot = int(name.split("_")[1])
            value = next((d.descriptor for d in entity.descriptors if d.source_ordinal == slot), None)
        if table == "findings":
            value = (getattr(entity.interpretation, name, None) if name in {"assessment", "recommendation"}
                     else entity.descriptors.get(name))
        _code_fields(row, name, value)
    if table == "rois":
        for prefix, box in (("", entity.coordinates), ("source_", entity.source_coordinates)):
            if box is not None:
                values = box.as_tuple() if hasattr(box, "as_tuple") else box
                names = ("y_min", "x_min", "y_max", "x_max") if prefix else ("y_min", "x_min", "y_stop", "x_stop")
                row.update(zip((prefix + n for n in names), values))
    return row


def _issue_row(issue: Issue, kind: Optional[str] = None, key: Optional[str] = None) -> Dict[str, Scalar]:
    context = issue.context
    if key is None and issue.code == "invalid_accession":
        # The sentinel never names an exam; retain patient-scoped diagnostics.
        if context.get("patient_id") is not None:
            kind, key = "patient", _encode(context["patient_id"])
    elif key is None:
        if "identity" in context and context.get("grain") in _GRAINS.values():
            kind, key = context["grain"], _encode(context["identity"])
        elif "identity" in context:
            for candidate in _GRAINS.values():
                if candidate in issue.code.split("_"):
                    kind, key = candidate, _encode(context["identity"])
                    break
        attachment = context.get("attachment")
        if isinstance(attachment, tuple) and len(attachment) == 2:
            kind, identity = attachment
            key = _encode(identity)
        elif key is None and context.get("accession_number") is not None:
            kind, key = "exam", _encode(context["accession_number"])
        elif key is None and context.get("patient_id") is not None:
            kind, key = "patient", _encode(context["patient_id"])
    row: Dict[str, Scalar] = dict(kind=kind, entity_key=key, field=_scalar(context.get("field")),
                                 code=issue.code, message=issue.message, severity=issue.severity.value,
                                 context=_encode(dict(context)))
    row["issue_key"] = _encode(row)
    return row


def project(graph: DatasetGraph, requested: Optional[Tuple[str, ...]] = None) -> Dict[str, List[Dict[str, Scalar]]]:
    """Build a fresh snapshot with no mutation or pandas import."""

    from embed_data_graph.clinical.incomplete import UnkeyedFinding
    from embed_data_graph.clinical.pathology import UnkeyedRegistryEntry, UnresolvedClinicalRecord

    names = (*_GRAINS, *_LINKS, "values", "unresolved", "unresolved_values", "issues")
    output: Dict[str, List[Dict[str, Scalar]]] = {name: [] for name in names}
    wanted = set(names if requested is None else requested)
    schemas = {name: table_schema(name) for name in names}
    diagnostics = [_issue_row(issue) for issue in graph.load_issues
                   if "unresolved_record" not in issue.context] if "issues" in wanted else []
    unresolved_issues: Dict[str, List[Issue]] = {}
    for issue in graph.load_issues if "issues" in wanted else ():
        if "unresolved_record" in issue.context:
            marker = _encode((issue.context["unresolved_address"], issue.context["unresolved_record"]))
            unresolved_issues.setdefault(marker, []).append(issue)

    def normalize(
        row: Dict[str, Any], table: str, kind: str, key: str,
        applicable_dates: Optional[Tuple[str, ...]] = None,
    ) -> Dict[str, Scalar]:
        normalized: Dict[str, Scalar] = {}
        for name, dtype in schemas[table].columns.items():
            value = row.get(name)
            if dtype == "datetime":
                if applicable_dates is not None and name not in applicable_dates:
                    normalized[name] = None
                    continue
                parsed = _date(value)
                if parsed is None:
                    issue = Issue("missing_date" if value is None or value == "" else "invalid_date",
                                  "Date is missing or cannot be represented as a datetime",
                                  context={"field": name, "value": _scalar(value)})
                    diagnostics.append(_issue_row(issue, kind, key))
                normalized[name] = parsed
            else:
                cell = _scalar(value)
                normalized[name] = str(cell) if dtype == "string" and cell is not None else cell
        return normalized

    for table, kind in _GRAINS.items():
        if table not in wanted and "values" not in wanted and "issues" not in wanted:
            continue
        for entity in graph._values(kind):
            key = _encode(entity.key)
            output[table].append(normalize(_entity_row(entity, table, graph), table, kind, key))
            if "values" not in wanted:
                continue
            data = entity._to_dict_data()
            omitted = {"metadata", "source", "sources", "unkeyed_findings", "invalid_accession_records", "unresolved_clinical_records", "unkeyed_registry_entries"}
            omitted.update(field for source, field, _ in _LINKS.values() if source == kind)
            for field, value in _leaves({k: v for k, v in data.items() if k not in omitted}):
                output["values"].append(dict(kind=kind, entity_key=key, field=field, value=value))
    for table, (kind, field, _) in _LINKS.items():
        if table not in wanted:
            continue
        for entity in graph._values(kind):
            targets = set(getattr(entity, field))
            if table == "exam_registry":
                targets = {resolved.key for target in targets
                           for resolved in graph._resolve_reference("registry", target)} | {
                               target for target in targets if not graph._resolve_reference("registry", target)}
            for target in targets:
                output[table].append(dict(source_key=_encode(entity.key), target_key=_encode(target)))

    unresolved: List[Tuple[Any, Any, str, str]] = []
    include_unresolved = bool(wanted & {"unresolved", "unresolved_values", "issues"})
    for address, entries in (graph.unresolved_records.items() if include_unresolved else ()):
        for entry in entries:
            record = entry.get("record")
            kind = getattr(record, "kind", entry.get("kind", "unknown"))
            unresolved.append((address, record, kind, entry.get("reason", "unresolved")))
    for patient in (graph.patients if include_unresolved else ()):
        for record in patient.unkeyed_registry_entries:
            unresolved.append((("registry", ("patient", patient.patient_id)), record, "registry", "missing_registry_identity"))
    occurrences: Dict[str, int] = {}
    for address, record, kind, reason in unresolved:
        # Diagnostic occurrence IDs have no cross-load clinical identity promise.
        leaves = dict(_leaves(record))
        if hasattr(record, "payload") and kind == "registry":
            leaves.update(dict(_leaves(record.payload, "/payload")))
        base = _encode((address, leaves, kind, reason))
        occurrence = occurrences.get(base, 0)
        occurrences[base] = occurrence + 1
        key = _encode((base, occurrence))
        marker = _encode((address, record.to_dict())) if hasattr(record, "to_dict") else ""
        for issue in unresolved_issues.get(marker, ()):
            diagnostics.append(_issue_row(issue, kind, key))
        row = {name: getattr(record, name, None) for name in table_schema("unresolved").columns}
        row.update(record_key=key, address=_encode(address), kind=kind, reason=reason, incomplete=True)
        for part in address if isinstance(address, tuple) else ():
            if not isinstance(part, tuple) or len(part) != 2:
                continue
            if part[0] == "finding":
                accession, number = part[1]
                if row["finding_number"] is None:
                    row["finding_number"] = number
            elif part[0] == "exam":
                accession = part[1]
            else:
                continue
            if row["accession_number"] is None:
                row["accession_number"] = accession
            if row["patient_id"] is None:
                exam = graph.exam(accession)
                row["patient_id"] = exam.patient_id if exam is not None else None
        applicable_dates: Tuple[str, ...] = ()
        if isinstance(record, UnresolvedClinicalRecord):
            applicable_dates = ("performed_date", "report_documented_date") if record.kind == "pathology" else ("performed_date",)
        elif isinstance(record, UnkeyedRegistryEntry):
            applicable_dates = ("diagnosis_date",)
            row["patient_id"] = address[1][1]
            # Match keyed registry projection: parse the original date rather
            # than the date property's truncated text; use typed code facts.
            row["diagnosis_date"] = record.payload.get("diagnosis_date")
            row["record_id"] = record.payload.get("record_id")
            for field in _CODES["registry"]:
                _code_fields(row, field, getattr(record, field))
        if isinstance(record, UnkeyedFinding):
            # Same typed descriptor columns and code normalization as findings.
            for field in _FINDING_DESCRIPTORS:
                _code_fields(row, field, record.descriptors.get(field))
        interpretation = getattr(record, "interpretation", None)
        for name in ("assessment", "recommendation"):
            _code_fields(row, name, getattr(interpretation, name, None))
        _code_fields(row, "procedure_type", getattr(record, "procedure_type", None))
        output["unresolved"].append(normalize(row, "unresolved", kind, key, applicable_dates))
        for field, value in leaves.items():
            output["unresolved_values"].append(dict(record_key=key, field=field, value=value))
    output["issues"] = list({row["issue_key"]: row for row in diagnostics}.values())
    output = {name: rows for name, rows in output.items() if name in wanted}
    for name, rows in output.items():
        keys = schemas[name].key
        rows.sort(key=lambda row: tuple(str(row[k]) for k in keys))
    return output


def dataframe(rows: List[Dict[str, Scalar]], schema: TableSchema) -> DataFrame:
    """Convert a projection table, importing optional pandas here only."""

    import pandas as pd  # type: ignore[import-untyped]

    frame = pd.DataFrame.from_records(rows, columns=list(schema.columns))
    for name, dtype in schema.columns.items():
        if dtype == "datetime":
            frame[name] = pd.to_datetime(frame[name]).astype("datetime64[ns]")
        elif dtype in {"string", "integer", "number", "boolean"}:
            frame[name] = frame[name].astype({"string": "string", "integer": "Int64", "number": "Float64", "boolean": "boolean"}[dtype])
        else:
            frame[name] = frame[name].astype(object)
    return frame


__all__ = ["Scalar", "TableSchema"]
