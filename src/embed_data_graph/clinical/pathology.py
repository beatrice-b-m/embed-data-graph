"""Mutable pathology bundles and cancer-registry entries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Hashable, Iterable, Mapping, Optional, Set, Tuple

from embed_data_graph.core.codes import Code
from embed_data_graph.core.entity import MutableEntity, Reference
from embed_data_graph.core.source import SourceRef, optional_source




class PathologySeverity(IntEnum):
    """EMBED ``path_severity`` groups; lower values are more severe.

    The scale is inverse: 0 is the most severe group. Never select the numeric
    maximum as the most severe result. Code 5 is non-breast cancer, which is
    not benign or cancer-free (older public documentation used 5 for normal
    tissue). Code 6 is invalid and has no member; it is kept only as
    ``raw_severity`` and flagged by ``validate``. A missing severity means no
    pathology is attached, not a benign or negative result.

    Members
    -------
    INVASIVE_BREAST_CANCER=0, IN_SITU_BREAST_CANCER=1, HIGH_RISK_LESION=2,
    BORDERLINE_LESION=3, BENIGN=4, NON_BREAST_CANCER=5.
    """

    INVASIVE_BREAST_CANCER = 0
    IN_SITU_BREAST_CANCER = 1
    HIGH_RISK_LESION = 2
    BORDERLINE_LESION = 3
    BENIGN = 4
    NON_BREAST_CANCER = 5


@dataclass(frozen=True)
class PathologyObservation:
    """One pathology descriptor code reported in a numbered source slot.

    Slot position and repeated values are kept as reported; neither implies
    weight or chronology.

    Attributes
    ----------
    descriptor : Code
        Reported descriptor code with its meaning. Text is accepted as a code
        without meaning.
    source_slot : str
        Non-empty source slot name, such as ``"path1"``.
    source_ordinal : int
        One-based slot number.
    source : SourceRef or None, optional
        Row the descriptor was read from. Default None.
    """

    descriptor: Code
    """Reported descriptor code and its meaning."""
    source_slot: str
    """Source slot name, such as ``path1``."""
    source_ordinal: int
    """One-based slot number."""
    source: Optional[SourceRef] = None
    """Row the descriptor was read from."""

    def __post_init__(self) -> None:
        descriptor = Code.coerce(self.descriptor)
        if descriptor is None:
            raise ValueError("descriptor must be a non-empty code")
        object.__setattr__(self, "descriptor", descriptor)
        object.__setattr__(self, "source_slot", _required_text(self.source_slot, "source_slot"))
        if (
            isinstance(self.source_ordinal, bool)
            or not isinstance(self.source_ordinal, int)
            or self.source_ordinal < 1
        ):
            raise ValueError("source_ordinal must be a positive integer")
        object.__setattr__(self, "source", optional_source(self.source))

    @property
    def identity(self) -> Tuple[str, int]:
        """Return ``(source_slot, source_ordinal)``."""

        return self.source_slot, self.source_ordinal


class Pathology(MutableEntity):
    """A pathology bundle: reported diagnosis fields and descriptor slots.

    MagView pathology belongs to the procedure it was reported for and is
    keyed ``("procedure", ProcedureIdentity)``; an explicitly keyed record is
    keyed ``(patient_id, record_id)``. The identity is never derived from a
    row position, report date or diagnosis text.

    Parameters
    ----------
    identity : hashable or None, optional
        Explicit key. When None, ``patient_id`` and ``record_id`` must both be
        supplied and form ``(patient_id, record_id)``.
    diagnosis, result_category : str or None, optional
        Reported diagnosis text and result category. No diagnosis is inferred.
    malignant : bool or None, optional
        Reported malignancy flag; None means unknown, not False.
    severity : PathologySeverity or None, optional
        EMBED severity group (inverse scale). None means no severity attached.
    raw_severity : Any, optional
        Severity as supplied, kept even when invalid (such as code 6).
    report_documented_date : str or None, optional
        Provisional pathology report date; never a diagnosis or event date.
    descriptors : iterable of PathologyObservation, optional
        Descriptor slots in source order, duplicates kept.
    procedure_references, finding_references, exam_references : iterable, optional
        Keys of the procedures, findings ``(accession, finding_number)`` and
        exams (accessions) the bundle is attached to. Targets may be missing.
    source : SourceRef or None, optional
        Row the bundle was read from.
    metadata, payload : mapping, optional
        Consumer metadata and uninterpreted source payload, copied into dicts.
    patient_id, record_id : optional, keyword-only
        Explicit record key used when ``identity`` is None.

    Raises
    ------
    TypeError
        No usable identity, or the identity is unhashable.

    Examples
    --------
    >>> Pathology(patient_id="P1", record_id="report1").identity
    ('P1', 'report1')
    """

    kind = "pathology"
    __key_fields__ = ("identity",)
    _references = (
        Reference("procedure_references", "procedure", many=True),
        Reference("finding_references", "finding", many=True),
        Reference("exam_references", "exam", many=True),
    )

    identity: Hashable
    """Key of the bundle."""
    diagnosis: Optional[str]
    """Reported diagnosis text; None means absent. No diagnosis is inferred."""
    result_category: Optional[str]
    """Reported result category."""
    malignant: Optional[bool]
    """Reported malignancy flag; None means unknown, not False."""
    severity: Optional[PathologySeverity]
    """EMBED severity group; None means no severity attached, not negative."""
    raw_severity: Any
    """Severity as supplied, kept even when invalid."""
    report_documented_date: Optional[str]
    """Provisional report date; never a diagnosis or event date."""
    descriptors: Tuple[PathologyObservation, ...]
    """Descriptor slots in source order."""
    procedure_references: Set[Hashable]
    """Keys of procedures the bundle is attached to."""
    finding_references: Set[Tuple[str, str]]
    """Keys of findings the bundle is attached to."""
    exam_references: Set[str]
    """Accessions of exams the bundle is attached to."""

    def __init__(
        self,
        identity: Optional[Hashable] = None,
        diagnosis: Optional[str] = None,
        result_category: Optional[str] = None,
        malignant: Optional[bool] = None,
        severity: Optional[PathologySeverity] = None,
        raw_severity: Any = None,
        report_documented_date: Optional[str] = None,
        descriptors: Iterable[PathologyObservation] = (),
        procedure_references: Optional[Iterable[Hashable]] = None,
        finding_references: Optional[Iterable[Tuple[str, str]]] = None,
        exam_references: Optional[Iterable[str]] = None,
        source: Optional[SourceRef] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        patient_id: Optional[str] = None,
        record_id: Optional[Hashable] = None,
    ) -> None:
        super().__init__()
        if identity is None:
            if patient_id is None or record_id is None:
                raise TypeError("Pathology requires an identity or both patient_id and record_id")
            identity = (patient_id, record_id)
        self.identity = identity
        self.diagnosis = diagnosis
        self.result_category = result_category
        self.malignant = malignant
        self.severity = severity
        self.raw_severity = raw_severity
        self.report_documented_date = report_documented_date
        self.descriptors = tuple(descriptors)
        self.procedure_references = set(procedure_references or ())
        self.finding_references = set(finding_references or ())
        self.exam_references = set(exam_references or ())
        self.source = source
        self.metadata = dict(metadata or {})
        self.payload = dict(payload or {})

    def _coerce(self, name: str, value: Any) -> Any:
        if name == "identity":
            try:
                hash(value)
            except TypeError as exc:
                raise TypeError("Pathology identity must be hashable") from exc
        elif name == "descriptors":
            return tuple(value or ())
        elif name == "procedure_references":
            return set(value or ())
        elif name == "finding_references":
            return {(str(accession), str(number)) for accession, number in value or ()}
        elif name == "exam_references":
            return {str(accession) for accession in value or ()}
        elif name == "source":
            return optional_source(value)
        elif name in {"metadata", "payload"}:
            return dict(value or {})
        return value

    def add_descriptor(self, descriptor: PathologyObservation) -> PathologyObservation:
        """Append a descriptor slot without deduplicating and return it."""

        self.descriptors = (*self.descriptors, descriptor)
        return descriptor

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "diagnosis": self.diagnosis,
            "result_category": self.result_category,
            "malignant": self.malignant,
            "severity": self.severity,
            "raw_severity": self.raw_severity,
            "report_documented_date": self.report_documented_date,
            "descriptors": self.descriptors,
            "procedure_references": self.procedure_references,
            "finding_references": self.finding_references,
            "exam_references": self.exam_references,
            "source": self.source,
            "metadata": self.metadata,
            "payload": self.payload,
        }


class CancerRegistryEntry(MutableEntity):
    """A patient-scoped cancer-registry record that exams can be assigned to.

    The registry ID is meaningful only together with the patient ID. It is a
    reference to a registry record, not itself a diagnosis or outcome.

    Parameters
    ----------
    patient_id : str
        Patient the registry record belongs to; part of the key.
    registry_id : str
        Registry record ID within that patient; part of the key.
    payload : mapping, optional
        Explicitly mapped registry fields, copied into a dict. None bound by
        default.
    metadata : mapping, optional
        Consumer metadata, copied into a dict.
    source : SourceRef or None, optional
        Row the entry was read from.
    """

    kind = "registry"
    __key_fields__ = ("patient_id", "registry_id")

    patient_id: str
    """Patient the record belongs to; part of the key."""
    registry_id: str
    """Registry record ID within the patient; part of the key."""
    payload: Dict[str, Any]
    """Explicitly mapped registry fields."""
    metadata: Dict[str, Any]
    """Consumer metadata."""

    def __init__(
        self,
        patient_id: str,
        registry_id: str,
        payload: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        source: Optional[SourceRef] = None,
    ) -> None:
        super().__init__()
        self.patient_id = patient_id
        self.registry_id = registry_id
        self.payload = dict(payload or {})
        self.metadata = dict(metadata or {})
        self.source = source

    def _coerce(self, name: str, value: Any) -> Any:
        if name in {"patient_id", "registry_id"}:
            return _required_text(value, name)
        if name in {"payload", "metadata"}:
            return dict(value or {})
        if name == "source":
            return optional_source(value)
        return value

    @property
    def identity(self) -> Tuple[str, str]:
        """Return ``(patient_id, registry_id)``."""

        return self.patient_id, self.registry_id

    @property
    def exams(self) -> Tuple[Any, ...]:
        """Registered exams assigned to this entry."""

        graph = self.graph
        return graph.parents(self, "exam") if graph is not None else ()

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "registry_id": self.registry_id,
            "payload": self.payload,
            "metadata": self.metadata,
            "source": self.source,
        }


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
