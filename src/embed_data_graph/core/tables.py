"""Normalize supported table-like values without semantic identity leakage.

The table boundary deliberately keeps physical row information separate from
domain identity.  A requested ``key`` is useful for optional diagnostics and
source references, but it never decides whether a row is admitted.  In
particular, DataFrame indexes and row ordinals are never used as fallback
identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional, Tuple, Union, Literal, Protocol, cast

from embed_data_graph.core.source import CanonicalKey, canonicalize_source_key


KeyCallback = Callable[[Mapping[Any, Any]], Any]

class _DataFrameLike(Protocol):
    """Structural table input; no runtime pandas dependency is required."""

    @property
    def index(self) -> Any: ...

    @property
    def columns(self) -> Any: ...

    def to_dict(self, orient: Literal["records"]) -> list[dict[Any, Any]]: ...


_TableInput = Union[Iterable[Mapping[str, Any]], _DataFrameLike]

KeySelector = Optional[Union[str, KeyCallback]]


@dataclass(frozen=True)
class TableIssue:
    """A shape-level problem that a source loader can convert to an Issue.

    Attributes
    ----------
    code : str
        Non-empty machine-readable diagnostic code.
    message : str
        Non-empty human-readable diagnostic explanation.
    ordinal : int
        Zero-based physical row position for diagnostics only; never clinical
        identity.
    severity : str
        Diagnostic level: info, warning or error. Errors invalidate
        ValidationResult; warnings do not by default. Default: 'error'.
    key_name : Optional[str]
        Requested physical key column, or None for a callback/unspecified
        column. Default: None.
    raw_key : Any
        Original key value retained for diagnostics; excluded from
        equality/hash. Default: None.
    """

    code: str
    """Non-empty machine-readable diagnostic code."""
    message: str
    """Non-empty human-readable diagnostic explanation."""
    ordinal: int
    """Zero-based physical row position for diagnostics only; never clinical identity."""
    severity: str = "error"
    """Diagnostic level: info, warning or error. Errors invalidate
    ValidationResult; warnings do not by default. Default: 'error'.
    """
    key_name: Optional[str] = None
    """Requested physical key column, or None for a callback/unspecified column. Default: None."""
    raw_key: Any = field(default=None, compare=False, hash=False, repr=False)
    """Original key value retained for diagnostics; excluded from equality/hash. Default: None."""


@dataclass(frozen=True)
class TableRecord:
    """One normalized mapping and an optional physical diagnostic key.

    Attributes
    ----------
    source_key : Optional[CanonicalKey]
        Physical source row key; does not supply clinical identity.
    mapping : Mapping[Any, Any]
        Shallow-copied read-only row mapping; nested values are not deep-copied.
    ordinal : int
        Zero-based physical row position for diagnostics only; never clinical
        identity.
    issues : Tuple[TableIssue, ...]
        Ordered diagnostics supplied by this operation; empty means none.
        Default: ().
    """

    source_key: Optional[CanonicalKey]
    """Physical source row key; does not supply clinical identity."""
    mapping: Mapping[Any, Any]
    """Shallow-copied read-only row mapping; nested values are not deep-copied."""
    ordinal: int
    """Zero-based physical row position for diagnostics only; never clinical identity."""
    issues: Tuple[TableIssue, ...] = ()
    """Ordered diagnostics supplied by this operation; empty means none. Default: ()."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping", MappingProxyType(dict(self.mapping)))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def row(self) -> Mapping[Any, Any]:
        """Readable alias for the normalized row mapping."""

        return self.mapping

    def __iter__(self) -> Iterator[Any]:
        """Allow ``source_key, mapping = record`` on issue-free records."""

        yield self.source_key
        yield self.mapping


class TableNormalizationError(ValueError):
    """Table-level shape error raised by iter_records.

    Parameters
    ----------
    code : str
        Machine-readable diagnostic code, also exposed as .code.
    message : str
        Human-readable text returned by str(error).
    ordinal : int or None, optional
        Zero-based row position, exposed as .ordinal; None means table-wide.

    Notes
    -----
    This is a ValueError subclass. Per-row source-key failures are TableIssue
    values attached to records rather than exceptions."""

    def __init__(self, code: str, message: str, ordinal: Optional[int] = None) -> None:
        self.code = code
        self.ordinal = ordinal
        super().__init__(message)


def iter_records(table: Optional[_TableInput], key: KeySelector = None) -> Iterator[TableRecord]:
    """Normalize table rows without assigning clinical identities.

    Parameters
    ----------
    table : iterable of mappings, DataFrame-like, or None
        Rows in source order. DataFrames must expose index, columns and
        to_dict(orient="records"). None yields nothing. A single row must be
        wrapped in an iterable. All rows are materialized before yielding.
    key : str, callable or None, optional
        Physical key column or callback receiving a mapping. None (default)
        omits physical keys; DataFrame indexes/ordinals are never fallback keys.

    Yields
    ------
    TableRecord
        Shallow read-only row mapping, zero-based ordinal and optional canonical
        key. Missing, duplicate or callback-failed keys become row issues and
        source_key=None; the rows still yield in source order.

    Raises
    ------
    TableNormalizationError
        Unsupported input shape, non-mapping row or inconsistent DataFrame data.
    TypeError
        key is neither a string, callback nor None.

    Notes
    -----
    The iterable is consumed; no resources are opened or closed. Memory usage is
    proportional to the table. Nested row values are shared, not deep-copied.
    """

    if table is None:
        return
    if key is not None and not isinstance(key, str) and not callable(key):
        raise TypeError("key must be a column name, callback, or None")

    dataframe = _dataframe_rows(table)
    if dataframe is not None:
        rows, index_values, range_index, index_unique = dataframe
        yield from _records_from_rows(
            rows,
            key,
            index_values=index_values,
            range_index=range_index,
            index_unique=index_unique,
        )
        return

    try:
        iterator = iter(cast(Iterable[Mapping[str, Any]], table))
    except TypeError as exc:
        raise TableNormalizationError(
            "unsupported_table", "table must be an iterable of mappings"
        ) from exc
    rows = []
    for ordinal, row in enumerate(iterator):
        if not isinstance(row, Mapping):
            raise TableNormalizationError(
                "row_not_mapping", "table row must be a mapping", ordinal
            )
        rows.append(row)
    yield from _records_from_rows(rows, key)


def _dataframe_rows(
    table: Any,
) -> Optional[
    Tuple[list[Mapping[Any, Any]], list[Any], bool, Optional[bool]]
]:
    to_dict = getattr(table, "to_dict", None)
    if (
        not callable(to_dict)
        or not hasattr(table, "index")
        or not hasattr(table, "columns")
    ):
        return None
    try:
        rows = to_dict(orient="records")
    except TypeError:
        return None
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise TableNormalizationError(
            "invalid_dataframe_records",
            "DataFrame record conversion returned invalid rows",
        )
    index = table.index
    index_values = list(index)
    if len(index_values) != len(rows):
        raise TableNormalizationError(
            "invalid_dataframe_index", "DataFrame index length does not match its rows"
        )
    is_unique = getattr(index, "is_unique", None)
    if type(is_unique) is not bool:
        is_unique = None
    return (
        cast(list[Mapping[Any, Any]], rows),
        index_values,
        type(index).__name__ == "RangeIndex",
        is_unique,
    )


def _records_from_rows(
    rows: Iterable[Mapping[Any, Any]],
    key: KeySelector,
    *,
    index_values: Optional[list[Any]] = None,
    range_index: bool = False,
    index_unique: Optional[bool] = None,
) -> Iterator[TableRecord]:
    rows = list(rows)
    candidates: list[Optional[CanonicalKey]] = []
    issues: list[list[TableIssue]] = [[] for _ in rows]

    for ordinal, row in enumerate(rows):
        raw_key: Any = None
        if isinstance(key, str):
            if key not in row:
                candidates.append(None)
                issues[ordinal].append(
                    TableIssue(
                        "missing_source_key",
                        "requested source key column {!r} is absent".format(key),
                        ordinal,
                        severity="warning",
                        key_name=key,
                    )
                )
                continue
            raw_key = row[key]
        elif callable(key):
            try:
                raw_key = key(row)
            except Exception as exc:  # callback failures are row diagnostics
                candidates.append(None)
                issues[ordinal].append(
                    TableIssue(
                        "source_key_callback_failed",
                        "source key callback failed: {}".format(exc),
                        ordinal,
                        severity="warning",
                    )
                )
                continue
        else:
            # No physical source key was requested.  The DataFrame index and
            # row ordinal remain deliberately unavailable to this record.
            candidates.append(None)
            continue

        try:
            candidates.append(canonicalize_source_key(raw_key))
        except (TypeError, ValueError) as exc:
            candidates.append(None)
            issues[ordinal].append(
                TableIssue(
                    "unusable_source_key",
                    "requested source key is unusable: {}".format(exc),
                    ordinal,
                    severity="warning",
                    key_name=key if isinstance(key, str) else None,
                    raw_key=raw_key,
                )
            )

    _invalidate_duplicate_requested_keys(candidates, issues, key)

    for ordinal, row in enumerate(rows):
        yield TableRecord(candidates[ordinal], row, ordinal, tuple(issues[ordinal]))


def _invalidate_duplicate_requested_keys(
    candidates: list[Optional[CanonicalKey]],
    issues: list[list[TableIssue]],
    key: KeySelector,
) -> None:
    positions: dict[CanonicalKey, list[int]] = {}
    for ordinal, candidate in enumerate(candidates):
        if candidate is not None:
            positions.setdefault(candidate, []).append(ordinal)
    for candidate, ordinals in positions.items():
        if len(ordinals) < 2:
            continue
        for ordinal in ordinals:
            candidates[ordinal] = None
            issues[ordinal].append(
                TableIssue(
                    "duplicate_source_key",
                    "source key occurs more than once in this table",
                    ordinal,
                    severity="warning",
                    key_name=key if isinstance(key, str) else None,
                    raw_key=candidate,
                )
            )
