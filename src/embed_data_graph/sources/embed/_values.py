"""Source-value helpers shared by every EMBED adapter.

One rule decides what counts as missing: None, pandas ``NA``/``NaT``, NaN and
blank or whitespace-only strings. NumPy-like scalars are unboxed first, so the
adapters never need a runtime dependency on NumPy or pandas.
"""

from __future__ import annotations

from enum import Enum
from math import isfinite
from numbers import Integral, Real
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Set

from embed_data_graph.core.source import Issue, IssueSeverity, is_null_scalar


def scalar(value: Any) -> Any:
    """Unbox a NumPy-like scalar through ``item()``; return other values unchanged."""

    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        try:
            return item()
        except (TypeError, ValueError, OverflowError):
            return value
    return value


def is_missing(value: Any) -> bool:
    """Return whether a source value carries no fact."""

    if isinstance(value, str):
        return not value.strip()
    return is_null_scalar(value)


def cell(row: Mapping[str, Any], column: Optional[str]) -> Any:
    """Return the row's unboxed value for a bound column, or None when missing."""

    if column is None:
        return None
    value = scalar(row.get(column))
    return None if is_missing(value) else value


def text(value: Any) -> Optional[str]:
    """Return stripped text, or None when missing."""

    value = scalar(value)
    return None if is_missing(value) else str(value).strip()


def code(value: Any) -> Optional[str]:
    """Return a MagView code trimmed and uppercased for comparison, or None.

    EMBED supports comparing alphabetic codes after this normalization; it does
    not assign a meaning to unexplained tokens.
    """

    normalized = text(value)
    return None if normalized is None else normalized.upper()


def identifier(value: Any) -> Optional[str]:
    """Return an identifier as stable text: ``1.0`` and ``1`` both become ``"1"``.

    Missing values, booleans and non-finite numbers return None.
    """

    value = scalar(value)
    if is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        number = float(value)
        if not isfinite(number):
            return None
        return str(int(number)) if number.is_integer() else str(value)
    return str(value).strip()


def whole_number(value: Any) -> Optional[int]:
    """Return a whole number as int, or None when missing, fractional or not numeric."""

    value = scalar(value)
    if is_missing(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if isfinite(number) and number.is_integer() else None


def same(left: Any, right: Any) -> bool:
    """Compare source values, tolerating array-like and unorderable scalars."""

    try:
        equal = left == right
        if type(equal) is bool:
            return equal
        item = getattr(equal, "item", None)
        return bool(item()) if callable(item) else False
    except (TypeError, ValueError):
        return repr(left) == repr(right)


def is_unknown(value: Any) -> bool:
    """Return whether a stored value carries no populated fact."""

    return value is None or (isinstance(value, Enum) and value.name == "UNKNOWN")


def reconcile_merge(
    current: Mapping[str, Any],
    updates: MutableMapping[str, Any],
    *,
    grain: str,
    key: Any,
    issues: list[Issue],
) -> None:
    """Turn merged values that contradict populated current values into unknowns.

    Merge fills gaps; it must not silently overwrite one populated fact with
    another. For each populated update whose field already holds a different
    populated value, the update becomes unknown (None, or the enum's UNKNOWN
    member) and a warning is recorded.
    ``updates`` is modified in place.
    """

    for name, value in list(updates.items()):
        existing = current.get(name)
        if is_unknown(value) or is_unknown(existing) or same(existing, value):
            continue
        # An enum field becomes its UNKNOWN member rather than None.
        updates[name] = getattr(type(existing), "UNKNOWN", None) if isinstance(existing, Enum) else None
        issues.append(
            Issue(
                code=f"conflicting_{grain}_{name}",
                message="Merged value conflicts with the current value and became unknown",
                severity=IssueSeverity.WARNING,
                context={"identity": key, "field": name, "values": [existing, value]},
            )
        )


Claims = Dict[str, Dict[str, Set[str]]]
"""Source patient claims one invocation supplied: accession to table to IDs."""


def record_claims(claims: Claims, accession: str, table: str, patient_ids: Iterable[str]) -> None:
    """Record the patient IDs that ``table``'s rows claim for an exam."""

    claims.setdefault(accession, {}).setdefault(table, set()).update(patient_ids)


def outside_graph_issue(table: str, rows: int) -> Issue:
    """Report rows that ``parents="existing"`` did not load, one issue per table.

    The rows address a patient, exam or image that is absent from the target
    graph. Skipping them is requested behavior, so the severity is INFO.
    """

    return Issue(
        code="rows_outside_graph",
        message="Rows addressing entities absent from the target graph were not loaded",
        severity=IssueSeverity.INFO,
        context={"table": table, "rows": rows},
    )
