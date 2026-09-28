"""Performed procedures and their identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from embed_data_graph.core.codes import Code
from embed_data_graph.core.entity import MutableEntity, Reference
from embed_data_graph.core.graph import ensure_graph
from embed_data_graph.core.primitives import Laterality
from embed_data_graph.core.source import SourceRef, optional_source

if TYPE_CHECKING:
    from embed_data_graph.clinical.findings import Finding
    from embed_data_graph.clinical.pathology import Pathology


@dataclass(frozen=True)
class ProcedureIdentity:
    """Complete immutable identity for one resolved procedure.

    Attributes
    ----------
    patient_id : str
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts.
    performed_date : str
        Non-empty reported procedure date, conventionally ISO YYYY-MM-DD.
        Construction checks text, validate checks dates.
    procedure_type : Code
        Reported procedure type (EMBED ``B`` needle biopsy, ``S`` surgical)
        with its meaning; part of the identity, compared by code. Text is
        accepted as a code without meaning.
    laterality : Laterality
        Known LEFT, RIGHT or BILATERAL side. UNKNOWN raises ValueError.
    """

    patient_id: str
    """Patient identifier. Non-empty text; source patient claims and assigned exam
    ownership are separate facts.
    """
    performed_date: str
    """Non-empty reported procedure date, conventionally ISO YYYY-MM-DD.
    Construction checks text, validate checks dates.
    """
    procedure_type: Code
    """Reported procedure type and its meaning; compared by code."""
    laterality: Laterality
    """Known LEFT, RIGHT or BILATERAL side. UNKNOWN raises ValueError."""

    def __post_init__(self) -> None:
        for attribute in ("patient_id", "performed_date"):
            value = getattr(self, attribute)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{attribute} must be a non-empty string")
            object.__setattr__(self, attribute, value.strip())
        if not isinstance(self.procedure_type, (str, Code)) or not str(getattr(self.procedure_type, "code", self.procedure_type)).strip():
            raise ValueError("procedure_type must be a non-empty code")
        object.__setattr__(self, "procedure_type", Code.coerce(self.procedure_type))
        side = Laterality.coerce(self.laterality)
        if side is Laterality.UNKNOWN:
            raise ValueError("Resolved procedure identity requires known laterality")
        object.__setattr__(self, "laterality", side)

    def to_dict(self) -> Dict[str, Any]:
        """Return the identity as JSON-compatible values."""

        return {
            "patient_id": self.patient_id,
            "performed_date": self.performed_date,
            "procedure_type": self.procedure_type.to_dict(),
            "laterality": self.laterality.value,
        }


class Procedure(MutableEntity):
    """One performed breast procedure, keyed by its ProcedureIdentity.

    A procedure can be attached to several findings and exams, and pathology
    attaches to it. Within a patient, the procedure date, type and biopsy side
    identify one procedure.

    Parameters
    ----------
    identity : ProcedureIdentity
        Patient, performed date, procedure type and known side; the key.
    finding_references : iterable of (str, str), optional
        Keys ``(accession, finding_number)`` of findings the procedure
        addresses. Targets may be missing.
    exam_references : iterable of str, optional
        Accessions of exams the procedure is attached to directly.
    sources : iterable of SourceRef, optional
        Rows the procedure was read from, deduplicated in order.
    metadata : mapping, optional
        Consumer metadata, copied into a dict.
    """

    kind = "procedure"
    __key_fields__ = ("identity",)
    _references = (
        Reference("finding_references", "finding", many=True),
        Reference("exam_references", "exam", many=True),
    )

    identity: ProcedureIdentity
    """Patient, performed date, procedure type and side; the key."""
    finding_references: Set[Tuple[str, str]]
    """Keys of findings the procedure addresses."""
    exam_references: Set[str]
    """Accessions of exams the procedure is attached to directly."""
    sources: Tuple[SourceRef, ...]
    """Rows the procedure was read from."""
    metadata: Dict[str, Any]
    """Consumer metadata."""

    def __init__(
        self,
        identity: ProcedureIdentity,
        finding_references: Optional[Iterable[Tuple[str, str]]] = None,
        exam_references: Optional[Iterable[str]] = None,
        sources: Optional[Iterable[SourceRef]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.identity = identity
        self.finding_references = set(finding_references or ())
        self.exam_references = set(exam_references or ())
        self.sources = tuple(sources or ())
        self.metadata = dict(metadata or {})

    def _coerce(self, name: str, value: Any) -> Any:
        if name == "identity" and not isinstance(value, ProcedureIdentity):
            raise TypeError("identity must be a ProcedureIdentity")
        if name == "finding_references":
            return {(str(accession), str(number)) for accession, number in value or ()}
        if name == "exam_references":
            return {str(accession) for accession in value or ()}
        if name == "sources":
            unique: List[SourceRef] = []
            for item in value or ():
                source = optional_source(item)
                if source is not None and source not in unique:
                    unique.append(source)
            return tuple(unique)
        if name == "metadata":
            return dict(value or {})
        return value

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        """Pathology bundles attached to this procedure."""

        graph = self.graph
        return graph.children(self, "pathology") if graph is not None else ()

    @property
    def findings(self) -> Tuple["Finding", ...]:
        """Registered findings this procedure addresses."""

        graph = self.graph
        return graph.parents(self, "finding") if graph is not None else ()

    def add_source(self, source: SourceRef) -> SourceRef:
        """Record another source row, ignoring duplicates, and return it."""

        self.sources = (*self.sources, source)
        return source

    def add_pathology(self, pathology: "Pathology") -> "Pathology":
        """Attach a pathology bundle to this procedure and return it."""

        return ensure_graph(self).attach(self, pathology)

    def _scope_patient_id(self) -> Optional[str]:
        return self.identity.patient_id

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "identity": self.identity,
            "finding_references": self.finding_references,
            "exam_references": self.exam_references,
            "sources": self.sources,
            "metadata": self.metadata,
        }
