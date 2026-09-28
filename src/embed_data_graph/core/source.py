"""Small, source-neutral identities and issues for table ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
import math
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple


class IssueSeverity(str, Enum):
    """Severity of an ingestion issue.

    Members
    -------
    INFO='info', WARNING='warning', ERROR='error'.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class CanonicalKey:
    """An immutable, explicitly typed physical-row key.

    The tag is part of equality and hashing, avoiding Python's otherwise loose
    equality between values such as ``True``, ``1``, and ``1.0``.

    Attributes
    ----------
    tag : str
        Canonical encoding tag: bool, int, float, string, date, datetime, or
        tuple. Participates in equality/hash.
    value : Any
        Tag-matching scalar: ISO text for dates, finite float for float, or a
        tuple of CanonicalKey values. Wrong type raises TypeError.
    """

    tag: str
    """Canonical encoding tag: bool, int, float, string, date, datetime, or tuple.
    Participates in equality/hash.
    """
    value: Any
    """Tag-matching scalar: ISO text for dates, finite float for float, or a tuple
    of CanonicalKey values. Wrong type raises TypeError.
    """

    def __post_init__(self) -> None:
        valid = {"bool", "int", "float", "string", "date", "datetime", "tuple"}
        if self.tag not in valid:
            raise ValueError("unsupported canonical key tag: {!r}".format(self.tag))
        if self.tag == "bool" and type(self.value) is not bool:
            raise TypeError("bool key values must be bool")
        if self.tag == "int" and type(self.value) is not int:
            raise TypeError("int key values must be int")
        if self.tag == "float":
            if type(self.value) is not float or not math.isfinite(self.value):
                raise TypeError("float key values must be finite floats")
        if self.tag in {"string", "date", "datetime"} and not isinstance(
            self.value, str
        ):
            raise TypeError(
                "{} key values must use their string encoding".format(self.tag)
            )
        if self.tag == "tuple" and (
            not isinstance(self.value, tuple)
            or not all(isinstance(item, CanonicalKey) for item in self.value)
        ):
            raise TypeError("tuple key values must contain canonical keys")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible tagged representation."""

        value: Any = self.value
        if self.tag == "tuple":
            value = [item.to_dict() for item in self.value]
        return {"tag": self.tag, "value": value}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CanonicalKey":
        """Reconstruct a key from :meth:`to_dict` output."""

        tag = value.get("tag")
        encoded = value.get("value")
        if not isinstance(tag, str):
            raise TypeError("serialized canonical key tag must be a string")
        if tag == "tuple":
            if not isinstance(encoded, (list, tuple)):
                raise TypeError("serialized tuple key value must be a sequence")
            encoded = tuple(cls.from_dict(item) for item in encoded)
        return cls(tag=tag, value=encoded)


def is_null_scalar(value: Any) -> bool:
    """Safely classify generic scalar nulls without importing pandas or NumPy."""

    if value is None:
        return True
    if type(value).__name__ in {"NAType", "NaTType"}:
        return True
    try:
        if isinstance(value, float) and math.isnan(value):
            return True
        unequal = value != value
        if type(unequal) is bool:
            return unequal
        item = getattr(unequal, "item", None)
        if callable(item):
            scalar = item()
            if type(scalar) is bool:
                return scalar
    except (TypeError, ValueError):
        # pd.NA deliberately raises when coerced to bool. Its type-name check
        # above handles it without making truthiness part of this boundary.
        return False
    return False


def canonicalize_source_key(value: Any) -> CanonicalKey:
    """Convert a physical row key to an immutable type-tagged value.

    Parameters
    ----------
    value : object
        CanonicalKey, bool, int, finite float, nonblank str, date, datetime, or
        tuple of supported values. NumPy-like scalars exposing item() are unboxed.

    Returns
    -------
    CanonicalKey
        Existing keys are returned unchanged. Strings retain whitespace; date
        and datetime use ISO text. Tags distinguish True, 1 and 1.0.

    Raises
    ------
    ValueError
        Null/NaN, nonfinite float or blank string.
    TypeError
        Unsupported key type. Callback errors from item() propagate.
    """

    if isinstance(value, CanonicalKey):
        return value
    if is_null_scalar(value):
        raise ValueError("source keys cannot be null or NaN")

    if type(value) is bool:
        return CanonicalKey("bool", value)
    if type(value) is int:
        return CanonicalKey("int", value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("source float keys must be finite")
        return CanonicalKey("float", value)
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("source string keys must not be blank")
        return CanonicalKey("string", value)
    if isinstance(value, datetime):
        return CanonicalKey("datetime", value.isoformat())
    if isinstance(value, date):
        return CanonicalKey("date", value.isoformat())
    if isinstance(value, tuple):
        return CanonicalKey(
            "tuple", tuple(canonicalize_source_key(item) for item in value)
        )

    # NumPy scalar types expose ``item``. This deliberately uses their scalar
    # protocol instead of importing NumPy into the runtime package.
    item = getattr(value, "item", None)
    if callable(item):
        normalized = item()
        if normalized is not value:
            return canonicalize_source_key(normalized)

    raise TypeError(
        "source keys must be bool, int, float, string, date, datetime, or tuple"
    )


@dataclass(frozen=True)
class SourceRef:
    """Identity of one physical row within a source materialization.

    Attributes
    ----------
    source_scope : str
        Non-empty physical materialization label.
    source_table : str
        Non-empty physical source table label.
    source_key : Any
        Physical key accepted by canonicalize_source_key, converted to
        CanonicalKey at construction. Use key for typed access.
    """

    source_scope: str
    """Non-empty physical materialization label."""
    source_table: str
    """Non-empty physical source table label."""
    source_key: Any
    """Physical key accepted by canonicalize_source_key, converted to CanonicalKey
    at construction. Use key for typed access.
    """

    def __post_init__(self) -> None:
        for attribute in ("source_scope", "source_table"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("{} must be a non-empty string".format(attribute))
        object.__setattr__(self, "source_key", canonicalize_source_key(self.source_key))

    @property
    def scope(self) -> str:
        """Concise alias for ``source_scope``."""

        return self.source_scope

    @property
    def table(self) -> str:
        """Concise alias for ``source_table``."""

        return self.source_table

    @property
    def key(self) -> CanonicalKey:
        """Concise alias for the canonical ``source_key``."""

        return self.source_key

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible identity representation."""

        return {
            "source_scope": self.source_scope,
            "source_table": self.source_table,
            "source_key": self.source_key.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceRef":
        """Reconstruct a source reference from :meth:`to_dict` output."""

        return cls(
            source_scope=value["source_scope"],
            source_table=value["source_table"],
            source_key=CanonicalKey.from_dict(value["source_key"]),
        )


def optional_source(value: Optional[object]) -> Optional[SourceRef]:
    """Return ``value`` if it is a SourceRef or None, else raise TypeError.

    A SourceRef locates the physical source row. It is evidence, never a
    clinical identity.
    """

    if value is not None and not isinstance(value, SourceRef):
        raise TypeError("source must be a SourceRef or None")
    return value


@dataclass(frozen=True)
class Issue:
    """A compact, immutable problem report for the new loading surface.

    Attributes
    ----------
    code : str
        Non-empty machine-readable diagnostic code.
    message : str
        Non-empty human-readable diagnostic explanation.
    severity : IssueSeverity
        Diagnostic level: info, warning or error. Errors invalidate
        ValidationResult; warnings do not by default. Default:
        IssueSeverity.ERROR.
    source : Optional[SourceRef]
        Optional SourceRef locating the source row; evidence, not a clinical
        event. Default: None.
    context : Mapping[str, Any]
        Shallow-copied read-only diagnostic mapping. Nested mutable values are
        not frozen. Default: a fresh empty mapping.
    """

    code: str
    """Non-empty machine-readable diagnostic code."""
    message: str
    """Non-empty human-readable diagnostic explanation."""
    severity: IssueSeverity = IssueSeverity.ERROR
    """Diagnostic level: info, warning or error. Errors invalidate
    ValidationResult; warnings do not by default. Default: IssueSeverity.ERROR.
    """
    source: Optional[SourceRef] = None
    """Optional SourceRef locating the source row; evidence, not a clinical event."""
    context: Mapping[str, Any] = field(default_factory=dict)
    """Shallow-copied read-only diagnostic mapping. Nested mutable values are not
    frozen. Default: a fresh empty mapping.
    """
    _fingerprint: Tuple[Any, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for attribute in ("code", "message"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("{} must be a non-empty string".format(attribute))
        object.__setattr__(self, "severity", IssueSeverity(self.severity))
        context = dict(self.context)
        if not all(isinstance(key, str) for key in context):
            raise TypeError("issue context keys must be strings")
        object.__setattr__(self, "context", MappingProxyType(context))
        object.__setattr__(
            self,
            "_fingerprint",
            (
                self.code,
                self.message,
                self.severity.value,
                self.source,
                _freeze_value(context),
            ),
        )

    @property
    def fingerprint(self) -> Tuple[Any, ...]:
        """Return the deterministic tuple used for cumulative deduplication."""

        return self._fingerprint

    def __hash__(self) -> int:
        return hash(self._fingerprint)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible issue representation."""

        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "source": None if self.source is None else self.source.to_dict(),
            "context": _json_value(self.context),
        }


@dataclass(frozen=True)
class UnresolvedReference:
    """A relationship whose target is absent or conflicts with canonical state.

    Attributes
    ----------
    source_kind : str
        Registry kind of the source endpoint.
    source_id : str
        Display string for the source identity; not necessarily a reversible key
        encoding.
    target_kind : str
        Registry kind of the target endpoint.
    target_id : str
        Display string for the target identity; not necessarily a reversible key
        encoding.
    reason : str
        Machine-readable resolution reason or explanatory text, depending on
        producer.
    """

    source_kind: str
    """Registry kind of the source endpoint."""
    source_id: str
    """Display string for the source identity; not necessarily a reversible key encoding."""
    target_kind: str
    """Registry kind of the target endpoint."""
    target_id: str
    """Display string for the target identity; not necessarily a reversible key encoding."""
    reason: str
    """Machine-readable resolution reason or explanatory text, depending on producer."""

    def __post_init__(self) -> None:
        for attribute in (
            "source_kind",
            "source_id",
            "target_kind",
            "target_id",
            "reason",
        ):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")

    def to_dict(self) -> Dict[str, str]:
        """Return a new string-valued diagnostic dictionary. Identity display strings
        are not a graph reconstruction format.
        """

        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "reason": self.reason,
        }


def _freeze_value(value: Any) -> Tuple[Any, ...]:
    if isinstance(value, Mapping):
        return (
            "mapping",
            tuple(sorted((key, _freeze_value(item)) for key, item in value.items())),
        )
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_freeze_value(item) for item in value))
    if isinstance(value, (set, frozenset)):
        return ("set", tuple(sorted((_freeze_value(item) for item in value), key=repr)))
    if isinstance(value, Enum):
        return ("enum", type(value).__qualname__, _freeze_value(value.value))
    if isinstance(value, (datetime, date)):
        return (type(value).__name__, value.isoformat())
    if value is None or type(value) in {bool, int, float, str}:
        return (type(value).__name__, value)
    return ("repr", type(value).__qualname__, repr(value))


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or type(value) in {bool, int, float, str}:
        return value
    return repr(value)
