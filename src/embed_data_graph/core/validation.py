"""Explicit, read-only quality inspection of represented domain facts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from numbers import Real
from typing import Any, Callable, Iterable, Tuple

from embed_data_graph.core.entity import MutableEntity
from embed_data_graph.core.primitives import ImageModality
from embed_data_graph.core.source import Issue, IssueSeverity


@dataclass(frozen=True)
class ValidationResult:
    """Immutable quality report returned by validate.

    Attributes
    ----------
    issues : tuple of Issue, optional
        Findings in emission order, default empty. Warnings alone remain valid;
        use validate(warnings_invalid=True) to promote warnings to errors.
    """

    issues: Tuple[Issue, ...] = ()
    """Findings in emission order, default empty. Warnings alone remain valid; use
    validate(warnings_invalid=True) to promote warnings to errors.
    """

    @property
    def valid(self) -> bool:
        """Return True if issues contains no error; an empty report is valid."""

        return not any(issue.severity == IssueSeverity.ERROR for issue in self.issues)


Validator = Callable[[Any], Iterable[Issue]]


def validate(entity: Any, *, validators: Iterable[Validator] = (),
             aggregate: bool = True, warnings_invalid: bool = False) -> ValidationResult:
    """Inspect supplied facts without mutating the object.

    Parameters
    ----------
    entity : object
        Object to inspect. Missing optional facts do not produce issues. Passing
        a DatasetGraph does not traverse its registries; validate its entities.
    validators : iterable of callable, optional
        Additional callbacks accepting one visited object and returning an
        iterable of Issue values. Default empty; each runs once per object.
    aggregate : bool, optional
        Default True also checks everything the entity contains in its graph
        and its embedded values: observations, interpretation, history timing,
        anatomy and landmarks. False checks only ``entity``. Each object is
        checked once; linked exams are not traversed.
    warnings_invalid : bool, optional
        Default False preserves severity. True copies warning issues as errors
        in this result, leaving the originals unchanged.

    Returns
    -------
    ValidationResult
        Built-in and custom issues in traversal/emission order; valid is False
        when at least one error exists. The result is not a diagnosis.

    Raises
    ------
    Exception
        Exceptions raised by custom validators propagate to the caller.

    Examples
    --------
    >>> from embed_data_graph import Patient, validate
    >>> validate(Patient("P1")).valid
    True
    """
    custom = tuple(validators)
    issues: list[Issue] = []
    pending = [entity]
    seen = set()
    while pending:
        obj = pending.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        issues.extend(_quality(obj))
        for validator in custom:
            issues.extend(validator(obj))
        if aggregate:
            graph = getattr(obj, "graph", None)
            if isinstance(obj, MutableEntity) and graph is not None:
                pending.extend(graph.children(obj))
            for collection in ("history_observations", "attribute_observations", "landmarks"):
                pending.extend(getattr(obj, collection, ()))
            for field in ("interpretation", "started", "stopped", "anatomical_position", "quadrant", "clock_position"):
                nested = getattr(obj, field, None)
                if nested is not None:
                    pending.append(nested)
    if warnings_invalid:
        issues = [Issue(issue.code, issue.message, IssueSeverity.ERROR, issue.source, issue.context)
                  if issue.severity == IssueSeverity.WARNING else issue for issue in issues]
    return ValidationResult(tuple(issues))


def _quality(obj: Any) -> Iterable[Issue]:
    def issue(code: str, message: str, **context: Any) -> Issue:
        return Issue(code, message, context={"object_type": type(obj).__name__, **context})

    claims = getattr(obj, "asserted_patient_ids", ())
    if len(claims) > 1:
        yield issue("patient_identity_conflict", "Exam has contradictory source patient claims", claims=sorted(claims))
    confidence = getattr(obj, "confidence", None)
    if confidence is not None and (not isinstance(confidence, Real) or not isfinite(float(confidence)) or not 0 <= float(confidence) <= 1):
        yield issue("confidence_range", "Confidence must be finite and between zero and one", value=confidence)
    distance = getattr(obj, "distance_from_nipple_cm", None)
    if distance is not None and (not isinstance(distance, Real) or not isfinite(float(distance)) or float(distance) < 0):
        yield issue("distance_range", "Distance from nipple must be a finite non-negative measurement", value=distance)
    for field in ("height", "width", "frame_count"):
        value = getattr(obj, field, None)
        if value is not None and (not isinstance(value, Real) or not isfinite(float(value)) or float(value) <= 0):
            yield issue("positive_" + field, field + " should be positive", value=value)
    frame_count = getattr(obj, "frame_count", None)
    modality = getattr(obj, "modality", None)
    if (
        frame_count is not None
        and isinstance(modality, ImageModality)
        and modality not in {ImageModality.DBT, ImageModality.UNKNOWN}
        and frame_count != 1
    ):
        yield Issue(
            "frame_modality",
            "Multiple frames are supplied for a non-DBT image",
            IssueSeverity.WARNING,
            context={"object_type": type(obj).__name__, "value": frame_count},
        )
    coordinates = getattr(obj, "coordinates", None)
    if coordinates is not None:
        values = coordinates.as_tuple() if hasattr(coordinates, "as_tuple") else coordinates
        if len(values) == 4:
            y0, x0, y1, x1 = values
            if not all(isfinite(float(v)) for v in values):
                yield issue("roi_finite", "ROI coordinates are not finite")
            if y1 <= y0 or x1 <= x0:
                yield issue("roi_order", "ROI stops should exceed minima")
            if y0 < 0 or x0 < 0:
                yield issue("roi_bounds", "ROI begins outside the image")
            graph = getattr(obj, "graph", None)
            image = graph.image(obj.image_id) if graph is not None else None
            if image is not None:
                if (image.height is not None and y1 > image.height) or (image.width is not None and x1 > image.width):
                    yield issue("roi_bounds", "ROI stops exceed supplied image dimensions")
                for frame in getattr(obj, "source_frame_indices", ()):
                    if frame < 0 or (image.frame_count is not None and frame >= image.frame_count):
                        yield issue("roi_frame_bounds", "ROI frame is outside supplied frame count", frame=frame)
        frames = getattr(obj, "source_frame_indices", ())
        if any(frame < 0 for frame in frames) or len(set(frames)) != len(frames):
            yield issue("roi_frame_indices", "ROI frame indices should be distinct and non-negative")
    for field in ("age", "patient_age", "birth_year", "year", "month", "hour"):
        value = getattr(obj, field, None)
        # EMBED exam ages are top-coded to 89, and zero is a data-quality error.
        limits = {"age": (0, 130), "patient_age": (1, 89), "birth_year": (1800, date.today().year),
                  "year": (1, 9999), "month": (1, 12), "hour": (1, 12)}
        if value is not None:
            lower, upper = limits[field]
            if not isinstance(value, Real) or not isfinite(float(value)) or not lower <= float(value) <= upper:
                yield issue("plausible_" + field, field + " is outside the documented plausibility range", value=value)
    for field in ("exam_date", "report_documented_date", "performed_date"):
        value = getattr(obj, field, None)
        if value is None and field == "performed_date":
            value = getattr(getattr(obj, "identity", None), field, None)
        if value is not None:
            try:
                parsed = date.fromisoformat(str(value)[:10])
            except (TypeError, ValueError):
                yield issue("date_format", "Supplied date is not a calendar date", field=field, value=value)
            else:
                if parsed.year < 1800 or parsed > date.today():
                    yield issue("date_plausibility", "Supplied date is outside the plausibility range", field=field, value=value)
    severity = getattr(obj, "severity", None)
    raw = getattr(obj, "raw_severity", None)
    if raw is not None:
        try:
            raw_valid = float(raw) in range(6)
        except (TypeError, ValueError):
            raw_valid = False
        if not raw_valid:
            yield issue("pathology_raw_severity", "Supplied raw severity is outside the represented 0–5 scale", value=raw)
    if severity is not None and (not isinstance(severity, Real) or severity not in range(6)):
        yield issue("pathology_severity", "Pathology severity is outside the represented 0–5 scale", value=severity)
    if severity is not None and raw is not None:
        try:
            agrees = float(raw) == float(severity)
        except (ValueError, TypeError):
            agrees = False
        if not agrees:
            yield issue("pathology_severity_conflict", "Raw and normalized severity disagree")
    started, stopped = getattr(obj, "started", None), getattr(obj, "stopped", None)
    for field in ("age", "year"):
        start, stop = getattr(started, field, None), getattr(stopped, field, None)
        if isinstance(start, Real) and isinstance(stop, Real) and stop < start:
            yield issue("history_time_order", "Reported history stops before it starts", field=field)


__all__ = ["ValidationResult", "Validator", "validate"]
