"""Imaging findings and the evidence behind their normalized anatomy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Tuple

from embed_data_graph.clinical.interpretations import ImagingInterpretation
from embed_data_graph.core.anatomy import AnatomicalPosition
from embed_data_graph.core.primitives import Laterality
from embed_data_graph.core.entity import MutableEntity, Reference, plain_value
from embed_data_graph.core.graph import ensure_graph
from embed_data_graph.core.source import SourceRef

if TYPE_CHECKING:
    from embed_data_graph.clinical.exams import Exam
    from embed_data_graph.clinical.pathology import Pathology
    from embed_data_graph.clinical.procedures import Procedure


class FindingRecordType(str, Enum):
    """Explicit semantic kind of a finding record.

    Members
    -------
    FINDING='finding',
    SYNTHETIC_CONTRALATERAL_NEGATIVE='synthetic_contralateral_negative'.
    """

    FINDING = "finding"
    SYNTHETIC_CONTRALATERAL_NEGATIVE = "synthetic_contralateral_negative"


@dataclass(frozen=True)
class FindingNormalizationEvidence:
    """Source-scoped evidence supporting one normalized finding attribute.

    Attributes
    ----------
    source : SourceRef or None
        Physical row provenance when the load supplied source keys, else None.
        It identifies evidence, not a clinical event.
    source_field : str
        Source column/slot that supplied the normalized evidence.
    raw_value : Any
        Original unnormalized value retained as source evidence; not a semantic
        identity.
    normalized_kind : str
        Non-empty label describing the normalized concept.
    normalized_value : Any
        Normalized value retained alongside source evidence. Default: None.
    """

    source: Optional[SourceRef]
    """Physical row provenance when the load supplied source keys, else None."""
    source_field: str
    """Source column/slot that supplied the normalized evidence."""
    raw_value: Any
    """Original unnormalized value retained as source evidence; not a semantic identity."""
    normalized_kind: str
    """Non-empty label describing the normalized concept."""
    normalized_value: Any = None
    """Normalized value retained alongside source evidence. Default: None."""

    def __post_init__(self) -> None:
        if self.source is not None and not isinstance(self.source, SourceRef):
            raise TypeError("source must be a SourceRef or None")
        for attribute in ("source_field", "normalized_kind"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "source": None if self.source is None else self.source.to_dict(),
            "source_field": self.source_field,
            "raw_value": plain_value(self.raw_value),
            "normalized_kind": self.normalized_kind,
            "normalized_value": plain_value(self.normalized_value),
        }


@dataclass(frozen=True)
class FindingNormalizationWarning:
    """Source-scoped warning emitted while normalizing finding anatomy.

    Attributes
    ----------
    source : SourceRef or None
        Physical row provenance when the load supplied source keys, else None.
        It identifies evidence, not a clinical event.
    code : str
        Non-empty machine-readable diagnostic code.
    message : str
        Non-empty human-readable diagnostic explanation.
    source_field : Optional[str]
        Source column/slot that supplied the normalized evidence. Default: None.
    raw_value : Any
        Original unnormalized value retained as source evidence; not a semantic
        identity. Default: None.
    """

    source: Optional[SourceRef]
    """Physical row provenance when the load supplied source keys, else None."""
    code: str
    """Non-empty machine-readable diagnostic code."""
    message: str
    """Non-empty human-readable diagnostic explanation."""
    source_field: Optional[str] = None
    """Source column/slot that supplied the normalized evidence. Default: None."""
    raw_value: Any = None
    """Original unnormalized value retained as source evidence; not a semantic
    identity. Default: None.
    """

    def __post_init__(self) -> None:
        if self.source is not None and not isinstance(self.source, SourceRef):
            raise TypeError("source must be a SourceRef or None")
        for attribute in ("code", "message"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
        if self.source_field is not None and (
            not isinstance(self.source_field, str) or not self.source_field.strip()
        ):
            raise ValueError("source_field must be a non-empty string when supplied")

    def to_dict(self) -> Dict[str, Any]:
        """Return a new non-recursive dictionary of represented fields, encoding enum
        values and nested evidence through their serializers. Graph ownership is not
        included.
        """

        return {
            "source": None if self.source is None else self.source.to_dict(),
            "source_field": self.source_field,
            "raw_value": plain_value(self.raw_value),
            "code": self.code,
            "message": self.message,
        }


class Finding(MutableEntity):
    """A radiologist-recorded imaging finding, keyed by accession and finding number.

    Parameters
    ----------
    accession_number : str
        Accession of the exam the finding belongs to; part of the key.
    laterality : Laterality
        Breast side, coerced; an attribute, not part of the key.
    finding_number : str
        Finding number within the accession, stored as text; part of the key.
        EMBED uses ``-9`` for a synthetic contralateral negative finding.
    finding_type : str or None, optional
        Reported finding category. Default None.
    interpretation : ImagingInterpretation or None, optional
        Assessment and recommendation. Default None.
    anatomical_position : AnatomicalPosition or None, optional
        Reported anatomy, independent of image coordinates. Default None.
    source_location_codes, source_depth_codes, source_distance_codes : mapping, optional
        Raw source anatomy codes, copied into dicts.
    normalization_evidence : iterable of FindingNormalizationEvidence, optional
        How the anatomy was normalized from source codes.
    descriptors : mapping, optional
        Reported descriptors, copied into a dict. No diagnosis is inferred.
    normalization_warnings : iterable of FindingNormalizationWarning, optional
        Unknown or conflicting anatomy codes.
    metadata : mapping, optional
        Consumer metadata, copied into a dict.
    record_type : FindingRecordType, optional
        FINDING or SYNTHETIC_CONTRALATERAL_NEGATIVE. Default FINDING.
    source : SourceRef or None, optional
        Row the finding was read from.

    Notes
    -----
    ``procedures`` and ``pathology`` are resolved by the graph from the keys
    those entities store; a finding without a graph has none.
    """

    kind = "finding"
    __key_fields__ = ("accession_number", "finding_number")
    _references = (Reference("accession_number", "exam"),)

    accession_number: str
    """Exam accession; part of the key."""
    finding_number: str
    """Finding number within the accession; part of the key."""
    laterality: Laterality
    """Breast side; an attribute, not part of the key."""
    finding_type: Optional[str]
    """Reported finding category."""
    interpretation: Optional[ImagingInterpretation]
    """Assessment and recommendation."""
    anatomical_position: Optional[AnatomicalPosition]
    """Reported anatomy, independent of image coordinates."""
    source_location_codes: Dict[str, Any]
    """Raw source location codes."""
    source_depth_codes: Dict[str, Any]
    """Raw source depth codes."""
    source_distance_codes: Dict[str, Any]
    """Raw source distance codes, including exceptional negative values."""
    normalization_evidence: Tuple[FindingNormalizationEvidence, ...]
    """How the anatomy was normalized from source codes."""
    normalization_warnings: Tuple[FindingNormalizationWarning, ...]
    """Unknown or conflicting anatomy codes."""
    descriptors: Dict[str, Any]
    """Reported descriptors."""
    metadata: Dict[str, Any]
    """Consumer metadata."""
    record_type: FindingRecordType
    """FINDING or SYNTHETIC_CONTRALATERAL_NEGATIVE."""
    source: Optional[object]
    """Row the finding was read from."""

    def __init__(
        self,
        accession_number: str,
        laterality: Laterality,
        finding_number: str,
        finding_type: Optional[str] = None,
        interpretation: Optional[ImagingInterpretation] = None,
        anatomical_position: Optional[AnatomicalPosition] = None,
        source_location_codes: Optional[Mapping[str, Any]] = None,
        source_depth_codes: Optional[Mapping[str, Any]] = None,
        source_distance_codes: Optional[Mapping[str, Any]] = None,
        normalization_evidence: Optional[Iterable[FindingNormalizationEvidence]] = None,
        descriptors: Optional[Mapping[str, Any]] = None,
        normalization_warnings: Optional[Iterable[FindingNormalizationWarning]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        record_type: FindingRecordType = FindingRecordType.FINDING,
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.accession_number = accession_number
        self.finding_number = finding_number
        self.laterality = laterality
        self.finding_type = finding_type
        self.interpretation = interpretation
        self.anatomical_position = anatomical_position
        self.source_location_codes = dict(source_location_codes or {})
        self.source_depth_codes = dict(source_depth_codes or {})
        self.source_distance_codes = dict(source_distance_codes or {})
        self.normalization_evidence = tuple(normalization_evidence or ())
        self.descriptors = dict(descriptors or {})
        self.normalization_warnings = tuple(normalization_warnings or ())
        self.metadata = dict(metadata or {})
        self.record_type = record_type
        self.source = source

    def _coerce(self, name: str, value: Any) -> Any:
        if name == "accession_number":
            return _required_text(value, "accession_number")
        if name == "finding_number":
            return _identifier_text(value, "finding_number")
        if name == "laterality":
            return Laterality.coerce(value)
        if name == "record_type":
            return FindingRecordType(value)
        if name in {"source_location_codes", "source_depth_codes", "source_distance_codes", "descriptors", "metadata"}:
            return dict(value or {})
        if name in {"normalization_evidence", "normalization_warnings"}:
            return tuple(value or ())
        if name == "interpretation" and value is not None and not isinstance(value, ImagingInterpretation):
            raise TypeError("interpretation must be an ImagingInterpretation or None")
        return value

    @property
    def identity(self) -> Tuple[str, str]:
        """Return ``(accession_number, finding_number)``."""

        return self.accession_number, self.finding_number

    def _children(self, kind: str) -> Tuple[Any, ...]:
        graph = self.graph
        return graph.children(self, kind) if graph is not None else ()

    @property
    def exam(self) -> Optional["Exam"]:
        """The exam with this accession if registered, else None."""

        graph = self.graph
        return graph.exam(self.accession_number) if graph is not None else None

    @property
    def procedures(self) -> Tuple["Procedure", ...]:
        """Procedures attached to this finding."""

        return self._children("procedure")

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        """Pathology attached to this finding or to its procedures, once each."""

        found: List["Pathology"] = []
        for item in (*self._children("pathology"), *(p for proc in self.procedures for p in proc.pathology)):
            if all(item is not existing for existing in found):
                found.append(item)
        return tuple(found)

    def add_procedure(self, procedure: "Procedure") -> "Procedure":
        """Attach a procedure to this finding and return it."""

        return ensure_graph(self).attach(self, procedure)

    def add_pathology(self, pathology: "Pathology") -> "Pathology":
        """Attach a pathology bundle directly to this finding and return it."""

        return ensure_graph(self).attach(self, pathology)

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "accession_number": self.accession_number,
            "finding_number": self.finding_number,
            "laterality": self.laterality,
            "finding_type": self.finding_type,
            "record_type": self.record_type,
            "interpretation": self.interpretation,
            "anatomical_position": self.anatomical_position,
            "source_location_codes": self.source_location_codes,
            "source_depth_codes": self.source_depth_codes,
            "source_distance_codes": self.source_distance_codes,
            "normalization_evidence": self.normalization_evidence,
            "normalization_warnings": self.normalization_warnings,
            "descriptors": self.descriptors,
            "metadata": self.metadata,
            "source": self.source,
        }


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _identifier_text(value: Any, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must be populated")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be populated")
    return normalized
