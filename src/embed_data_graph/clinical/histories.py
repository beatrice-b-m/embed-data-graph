"""Patient-reported history: prior exposures and prior procedures.

History rows are reported or previously documented facts, not treatments or
procedures performed at the associated exam. A row without an explicit
``record_id`` is one fact in a snapshot of the patient's history; its source
location is evidence and never becomes an event identity. Observations are
stored on their Patient and do not repeat the patient ID.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from numbers import Real
from typing import Any, Dict, Optional

from embed_data_graph.core.codes import Code
from embed_data_graph.core.entity import plain_value
from embed_data_graph.core.primitives import Laterality
from embed_data_graph.core.source import SourceRef, optional_source


@dataclass(frozen=True)
class HistoryTimeEstimate:
    """Partial reported timing with raw numeric components.

    Values are kept as reported, without imputation or range checks; validate
    checks plausibility. An estimate with every component None is empty.

    Attributes
    ----------
    age : float or None, optional
        Reported age in years. Default None.
    year : float or None, optional
        Reported calendar year. Default None.
    month : float or None, optional
        Reported month number, normally 1-12. Default None.
    """

    age: Optional[float] = None
    """Reported age in years; None means absent."""
    year: Optional[float] = None
    """Reported calendar year; None means absent."""
    month: Optional[float] = None
    """Reported month number; None means absent."""

    def __post_init__(self) -> None:
        for name in ("age", "year", "month"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, Real)):
                raise TypeError(f"{name} must be numeric or None")

    @property
    def is_empty(self) -> bool:
        """True when age, year and month are all None; zero is a supplied value."""

        return self.age is None and self.year is None and self.month is None

    def to_dict(self) -> Dict[str, object]:
        """Return ``{"age", "year", "month"}`` as supplied."""

        return {"age": self.age, "year": self.year, "month": self.month}


class PatientHistoryObservation:
    """Base for one reported history fact, optionally with an explicit record ID.

    Observations are mutable: the loader refreshes a keyed record in place so a
    consumer's reference and extra attributes survive. Equality is identity.
    Every observation has a ``source`` and a ``record_id``:

    Attributes
    ----------
    source : SourceRef or None
        Row the fact was read from; evidence, not a clinical event.
    record_id : str or None
        Explicit patient-scoped record ID, stripped to text. None marks an
        unkeyed reported fact.
    """

    source: Optional[SourceRef]
    record_id: Optional[str]

    def __post_init__(self) -> None:
        self.source = optional_source(self.source)
        if self.record_id is not None:
            normalized = str(self.record_id).strip()
            if not normalized:
                raise ValueError("record_id must be a non-empty value when supplied")
            self.record_id = normalized

    def update(self, **values: Any) -> "PatientHistoryObservation":
        """Set fields in place, re-check them, and return this observation."""

        for name, value in values.items():
            setattr(self, name, value)
        self.__post_init__()
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible dictionary of the declared fields."""

        return {item.name: plain_value(getattr(self, item.name)) for item in fields(self)}  # type: ignore[arg-type]


@dataclass(eq=False)
class MedicationHistoryObservation(PatientHistoryObservation):
    """A reported hormone, therapy or contraceptive exposure.

    Attributes
    ----------
    category : Code
        Exposure category with its meaning (EMBED ``H`` hormone, ``T``
        therapy, ``O`` contraceptive).
    medication : Code
        Exposure code with its meaning; the same code means different things
        in different categories (``O`` is "Other hormone" under ``H``).
        Text is accepted for either as a code without meaning.
    context_accession : str or None, optional
        Exam whose record carried the report; not when the exposure happened.
    continuous, current : bool or None, optional
        Reported status; None means unknown, never "no".
    reported_duration : str or None, optional
        Raw duration text; no unit is inferred.
    started, stopped : HistoryTimeEstimate or None, optional
        Partial reported timing; an empty estimate becomes None.
    comment : str or None, optional
        Source comment; blank text becomes None.
    source : SourceRef or None, optional
        Row the fact was read from. Default None.
    record_id : str or None, optional
        Explicit patient-scoped record ID; None (default) for an unkeyed fact.

    Examples
    --------
    >>> from embed_data_graph import Code
    >>> MedicationHistoryObservation(Code("H", "Hormone"), Code("TAMOX", "Tamoxifen")).medication.meaning
    'Tamoxifen'
    """

    category: Code
    """Exposure category and its meaning."""
    medication: Code
    """Exposure code and its meaning within the category."""
    context_accession: Optional[str] = None
    """Exam whose record carried the report; not when the exposure happened."""
    continuous: Optional[bool] = None
    """Whether continuous exposure was reported; None means unknown."""
    current: Optional[bool] = None
    """Whether current exposure was reported; None means unknown."""
    reported_duration: Optional[str] = None
    """Raw duration text; no unit is inferred."""
    started: Optional[HistoryTimeEstimate] = None
    """Partial reported start timing."""
    stopped: Optional[HistoryTimeEstimate] = None
    """Partial reported stop timing."""
    comment: Optional[str] = None
    """Source comment."""
    source: Optional[SourceRef] = None
    """Row the fact was read from; evidence, not a clinical event."""
    record_id: Optional[str] = None
    """Explicit patient-scoped record ID; None for an unkeyed reported fact."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.category = _required_code(self.category, "category")
        self.medication = _required_code(self.medication, "medication")
        for name in ("continuous", "current"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool or None")
        self.context_accession = _optional_text(self.context_accession, "context_accession")
        self.reported_duration = _optional_text(self.reported_duration, "reported_duration")
        self.started = _optional_time(self.started, "started")
        self.stopped = _optional_time(self.stopped, "stopped")
        self.comment = _optional_text(self.comment, "comment")


@dataclass(eq=False)
class ProcedureHistoryObservation(PatientHistoryObservation):
    """A reported prior procedure; not a verified current-exam procedure.

    Attributes
    ----------
    category : Code
        Procedure category with its meaning (EMBED ``B`` breast, ``G``
        gynecological).
    procedure : Code
        Procedure code with its meaning within the category.
        Text is accepted for either as a code without meaning.
    context_accession : str or None, optional
        Exam whose record carried the report; not when the procedure happened.
    laterality : Laterality, optional
        Reported breast side. Default UNKNOWN.
    reported_result : Code or None, optional
        Reported historical result with its meaning; not a verified pathology
        diagnosis. EMBED ``NONE`` means no result was reported, which is not a
        negative result; None means the result is missing.
    source : SourceRef or None, optional
        Row the fact was read from. Default None.
    record_id : str or None, optional
        Explicit patient-scoped record ID; None (default) for an unkeyed fact.
    """

    category: Code
    """Procedure category and its meaning."""
    procedure: Code
    """Procedure code and its meaning within the category."""
    context_accession: Optional[str] = None
    """Exam whose record carried the report; not when the procedure happened."""
    laterality: Laterality = Laterality.UNKNOWN
    """Reported breast side."""
    reported_result: Optional[Code] = None
    """Reported historical result and its meaning; not a verified pathology diagnosis."""
    source: Optional[SourceRef] = None
    """Row the fact was read from; evidence, not a clinical event."""
    record_id: Optional[str] = None
    """Explicit patient-scoped record ID; None for an unkeyed reported fact."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.category = _required_code(self.category, "category")
        self.procedure = _required_code(self.procedure, "procedure")
        self.context_accession = _optional_text(self.context_accession, "context_accession")
        self.laterality = Laterality.coerce(self.laterality)
        self.reported_result = Code.coerce(self.reported_result)


def _required_code(value: Any, name: str) -> Code:
    if isinstance(value, Code):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a Code or non-empty string")
    return Code(value)


def _optional_text(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    return value.strip() or None


def _optional_time(value: Optional[HistoryTimeEstimate], name: str) -> Optional[HistoryTimeEstimate]:
    if value is not None and not isinstance(value, HistoryTimeEstimate):
        raise TypeError(f"{name} must be HistoryTimeEstimate or None")
    return None if value is None or value.is_empty else value
