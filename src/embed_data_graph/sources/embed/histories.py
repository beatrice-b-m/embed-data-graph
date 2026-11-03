"""EMBED patient-history row normalization."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Optional

from embed_data_graph.clinical.histories import (
    CancerHistoryObservation,
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_graph.core.primitives import Laterality
from embed_data_graph.core.source import Issue, IssueSeverity, SourceRef
from embed_data_graph.core.codes import Code, Vocabulary
from embed_data_graph.sources.embed._values import cell, code, text, whole_number
from embed_data_graph.sources.embed.vocabulary import (
    BREAST_PROCEDURE,
    CONTRACEPTIVE,
    EXPOSURE_CATEGORY,
    GYNECOLOGICAL_PROCEDURE,
    HORMONE,
    PROCEDURE_HISTORY_CATEGORY,
    PROCEDURE_HISTORY_RESULT,
    THERAPY,
)


# The history code tables are scoped by category: the same code means
# different things in different categories.
_MEDICATIONS = {"H": HORMONE, "T": THERAPY, "O": CONTRACEPTIVE}
_PROCEDURES = {"B": BREAST_PROCEDURE, "G": GYNECOLOGICAL_PROCEDURE}
_UNKNOWN_FLAGS = {"", "U", "NA", "N/A", "NAN", "UNKNOWN"}


def normalize_medication_history(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: Optional[SourceRef],
    record_id: Optional[str] = None,
) -> tuple[Optional[MedicationHistoryObservation], tuple[Issue, ...]]:
    """Normalize one patient-reported medication row.

    Parameters
    ----------
    row : mapping
        Source column names to raw values; not mutated.
    columns : mapping
        Semantic field names to physical columns; None bindings omit fields.
        Use the matching map from resolve_columns for EMBED defaults.
    source : SourceRef or None
        Physical diagnostic provenance, not clinical identity.
    record_id : str or None, optional
        Explicit patient-scoped record ID; None (default) is an unkeyed snapshot.

    Returns
    -------
    MedicationHistoryObservation or None, tuple of Issue
        Reported fact and diagnostics; None if required category/medication is absent.
        Category and medication are decoded into Code values; the medication
        code is read in its category's table. An unknown category or code
        keeps its source code without a meaning and adds a warning.

    Notes
    -----
    No graph is mutated, no files are read and no scientific validity is inferred.
    """

    issues: list[Issue] = []
    raw_category = _upper(row, columns["category"])
    raw_code = _upper(row, columns["medication"])
    if not raw_category or not raw_code:
        return None, (
            Issue(
                code="incomplete_medication_history_identity",
                message="medication history requires category and medication code",
                source=source,
            ),
        )
    category, medication = _decode_pair(
        raw_category, raw_code, EXPOSURE_CATEGORY, _MEDICATIONS, "medication", source, issues
    )
    observation = MedicationHistoryObservation(
        source=source,
        record_id=_record_id(row, columns, record_id),
        category=category,
        medication=medication,
        context_accession=_text(row, columns["accession"]),
        continuous=_flag(row, columns["continuous"], source, "continuous", issues),
        current=_flag(row, columns["current"], source, "current", issues),
        reported_duration=_text(row, columns["duration"]),
        started=_time_estimate(
            row,
            columns,
            source,
            issues,
            prefix="start",
        ),
        stopped=_time_estimate(
            row,
            columns,
            source,
            issues,
            prefix="stop",
        ),
        comment=_text(row, columns["comment"]),
    )
    return observation, tuple(issues)


def normalize_procedure_history(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: Optional[SourceRef],
    record_id: Optional[str] = None,
) -> tuple[Optional[ProcedureHistoryObservation], tuple[Issue, ...]]:
    """Normalize one patient-reported prior procedure row.

    Parameters
    ----------
    row : mapping
        Source column names to raw values; not mutated.
    columns : mapping
        Semantic field names to physical columns; None bindings omit fields.
        Use the matching map from resolve_columns for EMBED defaults.
    source : SourceRef or None
        Physical diagnostic provenance, not clinical identity.
    record_id : str or None, optional
        Explicit patient-scoped record ID; None (default) is an unkeyed snapshot.

    Returns
    -------
    ProcedureHistoryObservation or None, tuple of Issue
        Reported fact and diagnostics; None if required category/procedure is absent.
        Category, procedure and result are decoded into Code values; the
        procedure code is read in its category's table. A combined result such
        as ``FA,SF`` is not split. Unknown codes keep their source code without
        a meaning and add a warning.

    Notes
    -----
    No graph is mutated, no files are read and no scientific validity is inferred.
    """

    issues: list[Issue] = []
    raw_category = _upper(row, columns["category"])
    raw_code = _upper(row, columns["procedure"])
    if not raw_category or not raw_code:
        return None, (
            Issue(
                code="incomplete_procedure_history_identity",
                message="procedure history requires category and procedure code",
                source=source,
            ),
        )
    category, procedure = _decode_pair(
        raw_category, raw_code, PROCEDURE_HISTORY_CATEGORY, _PROCEDURES, "procedure", source, issues
    )
    result = PROCEDURE_HISTORY_RESULT.decode(_upper(row, columns["result"]))
    if result is not None and not result.is_known:
        issues.append(
            Issue(
                code="unknown_procedure_history_result",
                message="procedure history result is not in the EMBED vocabulary",
                severity=IssueSeverity.WARNING,
                source=source,
                context={"result": result.code},
            )
        )
    observation = ProcedureHistoryObservation(
        source=source,
        record_id=_record_id(row, columns, record_id),
        category=category,
        procedure=procedure,
        context_accession=_text(row, columns["accession"]),
        laterality=Laterality.coerce(_text(row, columns["laterality"])),
        reported_result=result,
    )
    return observation, tuple(issues)


def normalize_cancer_history(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: Optional[SourceRef],
    record_id: Optional[str] = None,
) -> tuple[CancerHistoryObservation, tuple[Issue, ...]]:
    """Normalize one reported cancer-history row about the patient or a relative.

    Parameters
    ----------
    row : mapping
        Source column names to raw values; not mutated.
    columns : mapping
        Semantic field names to physical columns; None bindings omit fields.
        Use the matching map from resolve_columns for EMBED defaults.
    source : SourceRef or None
        Physical diagnostic provenance, not clinical identity.
    record_id : str or None, optional
        Explicit patient-scoped record ID; None (default) is an unkeyed snapshot.

    Returns
    -------
    CancerHistoryObservation, tuple of Issue
        The reported entry and diagnostics. The subject flag 1 is the patient
        and 0 a relative; another value leaves ``about_relative`` None with an
        ``unknown_cancer_history_subject`` warning. Relationship, category and
        cancer codes are uppercased source codes without meanings, because the
        catalog's dictionaries for them are provisional or not code lists.
        Every other field is raw text.

    Notes
    -----
    No graph is mutated, no files are read and no scientific validity is inferred.
    """

    issues: list[Issue] = []
    subject = _upper(row, columns.get("subject"))
    flag = whole_number(cell(row, columns.get("subject")))
    about_relative = {1: False, 0: True}.get(flag) if flag is not None else None
    if subject and about_relative is None:
        issues.append(
            Issue(
                code="unknown_cancer_history_subject",
                message="cancer-history subject is neither 1 (patient) nor 0 (relative)",
                severity=IssueSeverity.WARNING,
                source=source,
                context={"value": subject},
            )
        )
    observation = CancerHistoryObservation(
        source=source,
        record_id=_record_id(row, columns, record_id),
        about_relative=about_relative,
        relationship=Code.coerce(_upper(row, columns.get("relationship")) or None),
        category=Code.coerce(_upper(row, columns.get("category")) or None),
        cancer_code=Code.coerce(_upper(row, columns.get("cancer_code")) or None),
        context_accession=_text(row, columns.get("accession")),
        **{name: _text(row, columns.get(name)) for name in _CANCER_TEXT_COLUMNS},
    )
    return observation, tuple(issues)


_CANCER_TEXT_COLUMNS = (
    "side", "bilateral", "premenopausal", "diagnosis_age", "diagnosis_month", "diagnosis_year",
    "current_age", "brca1", "brca2", "comment",
)


def _decode_pair(
    raw_category: str,
    raw_code: str,
    categories: Vocabulary,
    codes: Mapping[str, Vocabulary],
    kind: str,
    source: Optional[SourceRef],
    issues: list[Issue],
) -> tuple[Code, Code]:
    """Decode a category and the code read in that category's table.

    An unknown category or code keeps its source code without a meaning and
    adds a warning.
    """

    category = categories.decode(raw_category)
    table = codes.get(raw_category)
    decoded = table.decode(raw_code) if table is not None else Code(raw_code, unknown=(raw_code,))
    assert category is not None and decoded is not None
    if not category.is_known:
        issues.append(
            Issue(
                code=f"unknown_{kind}_history_category",
                message=f"{kind} history category is not in the EMBED vocabulary",
                severity=IssueSeverity.WARNING,
                source=source,
                context={"category": raw_category},
            )
        )
    if not decoded.is_known:
        issues.append(
            Issue(
                code=f"unknown_{kind}_history_code",
                message=f"{kind} history code is not in the EMBED vocabulary",
                severity=IssueSeverity.WARNING,
                source=source,
                context={"category": raw_category, "code": raw_code},
            )
        )
    return category, decoded


def _text(row: Mapping[str, Any], column: Optional[str]) -> Optional[str]:
    return text(cell(row, column))


def _upper(row: Mapping[str, Any], column: Optional[str]) -> str:
    return code(cell(row, column)) or ""


def _flag(
    row: Mapping[str, Any],
    column: Optional[str],
    source: Optional[SourceRef],
    semantic: str,
    issues: list[Issue],
) -> Optional[bool]:
    value = _upper(row, column)
    if value == "Y":
        return True
    if value == "N":
        return False
    if value in _UNKNOWN_FLAGS:
        return None
    issues.append(
        Issue(
            code="unrecognized_history_flag",
            message="patient-history boolean flag was not recognized",
            severity=IssueSeverity.WARNING,
            source=source,
            context={"field": semantic, "value": value},
        )
    )
    return None


def _number(
    row: Mapping[str, Any],
    column: Optional[str],
    source: Optional[SourceRef],
    semantic: str,
    issues: list[Issue],
    *,
    minimum: float,
    maximum: float,
    integer: bool,
) -> Optional[float]:
    """Parse a numeric fact without applying clinical plausibility rules.

    ``minimum``, ``maximum``, and ``integer`` remain in the private signature
    for callers from the pre-validation adapter, but range and integral checks
    belong to W7 validation.  A finite numeric value is retained even when it
    is clinically implausible.
    """

    text = _text(row, column)
    if text is None:
        return None
    try:
        value = float(text)
    except ValueError:
        value = float("nan")
    if not isfinite(value):
        issues.append(
            Issue(
                code="invalid_history_time_component",
                message="patient-history time component could not be normalized",
                severity=IssueSeverity.WARNING,
                source=source,
                context={"field": semantic, "value": text},
            )
        )
        return None
    if integer and value.is_integer():
        return int(value)
    return value


def _time_estimate(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    source: Optional[SourceRef],
    issues: list[Issue],
    *,
    prefix: str,
) -> Optional[HistoryTimeEstimate]:
    age = _number(
        row,
        columns[f"{prefix}_age"],
        source,
        f"{prefix}_age",
        issues,
        minimum=0,
        maximum=150,
        integer=False,
    )
    month = _number(
        row,
        columns[f"{prefix}_month"],
        source,
        f"{prefix}_month",
        issues,
        minimum=1,
        maximum=12,
        integer=True,
    )
    year = _number(
        row,
        columns[f"{prefix}_year"],
        source,
        f"{prefix}_year",
        issues,
        minimum=1,
        maximum=9999,
        integer=True,
    )
    estimate = HistoryTimeEstimate(
        age=age,
        month=month if month is not None else None,
        year=year if year is not None else None,
    )
    return None if estimate.is_empty else estimate


def _record_id(
    row: Mapping[str, Any],
    columns: Mapping[str, Optional[str]],
    explicit: Optional[str],
) -> Optional[str]:
    """Return the explicit record ID, else the mapped record-ID column value."""

    return explicit if explicit is not None else _text(row, columns.get("record_id"))
