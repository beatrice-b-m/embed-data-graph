"""Patient attribute values reported in one exam context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Optional, Tuple


@dataclass(frozen=True)
class PatientAttributeObservation:
    """One reported value of a patient attribute in one exam context.

    Patient attributes such as sex repeat on every exam row and may change over
    time or disagree because of data quality. Each observation keeps the value
    reported in one context so a consumer can choose a value as of an explicit
    date, without leaking later information into an earlier analysis.

    Attributes
    ----------
    attribute : str
        Attribute name, such as ``"sex"``.
    value : Any
        Reported value; None records an explicitly supplied null.
    accession_number : str or None, optional
        Exam accession whose row reported the value. Default None.
    context_date : datetime.date or None, optional
        Date of that exam context (the exam date), not necessarily when the
        attribute became true. Default None means undated.

    Examples
    --------
    >>> from datetime import date
    >>> PatientAttributeObservation("sex", "F", "A1", date(2020, 1, 2)).context
    ('sex', 'A1', datetime.date(2020, 1, 2))
    """

    attribute: str
    """Attribute name, such as ``"sex"``."""
    value: Any
    """Reported value; None records an explicitly supplied null."""
    accession_number: Optional[str] = None
    """Exam accession whose row reported the value."""
    context_date: Optional[date] = None
    """Date of the exam context; None means undated."""

    def __post_init__(self) -> None:
        if not isinstance(self.attribute, str) or not self.attribute.strip():
            raise ValueError("attribute must be a non-empty string")
        if self.context_date is not None and type(self.context_date) is not date:
            raise TypeError("context_date must be a datetime.date or None")

    @property
    def context(self) -> Tuple[str, Optional[str], Optional[date]]:
        """Return ``(attribute, accession_number, context_date)``.

        A patient keeps at most one observation per context; adding another
        with the same context replaces it.
        """

        return self.attribute, self.accession_number, self.context_date


class AttributeStatus(str, Enum):
    """Why ``Patient.attribute_resolution`` has or lacks a value.

    Members
    -------
    REPORTED='reported'
        Observations on the latest qualifying date agree on one value.
    NOT_REPORTED='not_reported'
        No dated observation on or before the cutoff reports a value.
    CONFLICT='conflict'
        Observations on the latest qualifying date report different values.
    """

    REPORTED = "reported"
    NOT_REPORTED = "not_reported"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class AttributeResolution:
    """A patient attribute as of a date, with the reason for its value.

    Attributes
    ----------
    attribute : str
        Attribute name.
    as_of : datetime.date
        Inclusive cutoff that was applied.
    status : AttributeStatus
        Whether a value was reported, not reported, or in conflict.
    value : Any
        The agreed value when ``status`` is REPORTED, else None.
    context_date : datetime.date or None
        The latest qualifying observation date; None when not reported.
    candidates : tuple
        The distinct values reported on ``context_date``, in observation
        order; more than one means a conflict. Empty when not reported.

    Notes
    -----
    No reduction rule is applied: a conflict on the latest date does not fall
    back to an earlier agreeing value. Use ``Patient.attribute_history`` to
    apply one.
    """

    attribute: str
    """Attribute name."""
    as_of: date
    """Inclusive cutoff that was applied."""
    status: AttributeStatus
    """Whether a value was reported, not reported, or in conflict."""
    value: Any = None
    """The agreed value when reported, else None."""
    context_date: Optional[date] = None
    """The latest qualifying observation date."""
    candidates: Tuple[Any, ...] = ()
    """Distinct values reported on ``context_date``."""
