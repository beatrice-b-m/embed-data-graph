"""Breast-imaging exams and their per-breast views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping, Optional, Set, Tuple

from embed_data_graph.core.codes import Code
from embed_data_graph.core.entity import MutableEntity, Reference, readonly_mapping
from embed_data_graph.core.graph import ensure_graph
from embed_data_graph.core.primitives import Laterality

if TYPE_CHECKING:
    from embed_data_graph.clinical.findings import Finding
    from embed_data_graph.clinical.pathology import CancerRegistryEntry, Pathology
    from embed_data_graph.clinical.patients import Patient
    from embed_data_graph.clinical.procedures import Procedure
    from embed_data_graph.imaging.images import MammogramImage


@dataclass(frozen=True)
class BreastSide:
    """The findings and images of one breast within an exam.

    Computed from the exam on each access, so it always reflects current
    finding and image laterality. A bilateral finding appears on both sides;
    images of unknown laterality appear on neither.

    Attributes
    ----------
    accession_number : str
        The exam's accession.
    laterality : Laterality
        LEFT or RIGHT.
    findings : tuple of Finding
        Findings on this side in the exam's order.
    images : tuple of MammogramImage
        Images of this side in the exam's order.
    """

    accession_number: str
    """The exam's accession."""
    laterality: Laterality
    """LEFT or RIGHT."""
    findings: Tuple["Finding", ...] = ()
    """Findings on this side."""
    images: Tuple["MammogramImage", ...] = ()
    """Images of this side."""


class Exam(MutableEntity):
    """A breast-imaging exam, keyed by accession number.

    Parameters
    ----------
    accession_number : str
        Non-empty exam accession.
    patient_id : str or None, optional
        Owning patient. When given, it is also recorded as a source claim.
        Default None.
    exam_date : str or None, optional
        Exam date as supplied, conventionally ISO ``YYYY-MM-DD``. Default None.
    description : str or None, optional
        Source exam (procedure) description. Default None.
    density : Code or None, optional
        Breast tissue density with its meaning (EMBED ``1``-``4``, ``5``
        normal male); not an ordinal scale. Default None.
    exam_type : Code or None, optional
        Exam type derived from the description, such as ``screening``.
    visit_type : Code or None, optional
        Visit type with its meaning. Default None.
    modality : Code or None, optional
        Exam modality with its meaning. Default None.
        Text is accepted for these four as a code without meaning.
    patient_age : float or None, optional
        Patient age in years at the exam, top-coded to 89 in EMBED. Default None.
    asserted_patient_ids : iterable of str, optional
        Source patient claims. A single claim with no ``patient_id`` makes
        that patient the owner; conflicting claims leave the exam unowned.
    linked_accessions : iterable of str, optional
        Accessions of exams in the same imaging episode (never prior or
        follow-up exams). Targets may be missing.
    registry_references : iterable of (str, str), optional
        Assigned cancer-registry entries as ``(patient_id, registry_id)``.
    owner_explicit : bool, optional
        Whether ``patient_id`` was chosen explicitly and survives later source
        claims. Default False.
    metadata : mapping, optional
        Consumer metadata, copied into a dict.
    source : SourceRef or None, optional
        Row the exam was read from.

    Notes
    -----
    Collections such as ``findings`` are resolved by the owning graph from the
    keys that related entities store; an exam without a graph has none. Adding
    a child to an exam without a graph first registers the exam in a new one.

    Examples
    --------
    >>> from embed_data_graph import Exam, Finding
    >>> exam = Exam("A1")
    >>> finding = exam.add_finding(Finding("A1", "B", "1"))
    >>> sorted(side.value for side in exam.breast_sides)
    ['L', 'R']
    """

    kind = "exam"
    __key_fields__ = ("accession_number",)
    _references = (
        Reference("patient_id", "patient"),
        Reference("linked_accessions", "exam", "association", many=True),
        Reference("registry_references", "registry", "child", many=True),
    )

    accession_number: str
    """Exam accession; the registry key."""
    patient_id: Optional[str]
    """Owning patient, or None when unowned or claims conflict."""
    exam_date: Optional[str]
    """Exam date as supplied."""
    description: Optional[str]
    """Source exam description."""
    density: Optional[Code]
    """Breast tissue density and its meaning; not an ordinal scale."""
    exam_type: Optional[Code]
    """Exam type derived from the description, such as ``screening``."""
    visit_type: Optional[Code]
    """Visit type and its meaning."""
    modality: Optional[Code]
    """Exam modality and its meaning."""
    patient_age: Optional[float]
    """Patient age in years at the exam; EMBED top-codes ages of 90 or more to 89."""
    asserted_patient_ids: Set[str]
    """Source patient claims; not a choice of owner."""
    linked_accessions: Set[str]
    """Accessions of same-episode exams this exam lists."""
    registry_references: Set[Tuple[str, str]]
    """Assigned registry entries as ``(patient_id, registry_id)``."""
    metadata: Dict[str, Any]
    """Consumer metadata."""
    source: Optional[object]
    """Row the exam was read from."""

    def __init__(
        self,
        accession_number: str,
        patient_id: Optional[str] = None,
        exam_date: Optional[str] = None,
        description: Optional[str] = None,
        density: Optional[Code] = None,
        exam_type: Optional[Code] = None,
        visit_type: Optional[Code] = None,
        modality: Optional[Code] = None,
        patient_age: Optional[float] = None,
        asserted_patient_ids: Optional[Iterable[str]] = None,
        linked_accessions: Optional[Iterable[str]] = None,
        registry_references: Optional[Iterable[Tuple[str, str]]] = None,
        owner_explicit: bool = False,
        metadata: Optional[Mapping[str, Any]] = None,
        source: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.accession_number = accession_number
        claims = set(asserted_patient_ids or ())
        if patient_id is not None:
            claims.add(patient_id)
        elif len(claims) == 1:
            patient_id = next(iter(claims))
        self.patient_id = patient_id
        self.asserted_patient_ids = claims
        self.exam_date = exam_date
        self.description = description
        self.density = Code.coerce(density)
        self.exam_type = Code.coerce(exam_type)
        self.visit_type = Code.coerce(visit_type)
        self.modality = Code.coerce(modality)
        self.patient_age = patient_age
        self.linked_accessions = set(linked_accessions or ())
        self.registry_references = set(registry_references or ())
        self._owner_explicit = bool(owner_explicit)
        self.metadata = dict(metadata or {})
        self.source = source

    def _coerce(self, name: str, value: Any) -> Any:
        if name == "accession_number":
            return _required_text(value, "accession_number")
        if name == "patient_id":
            return None if value is None else _required_text(value, "patient_id")
        if name in {"asserted_patient_ids", "linked_accessions"}:
            return {_required_text(item, "identifier") for item in value or ()}
        if name == "registry_references":
            return {
                (_required_text(patient, "patient_id"), _required_text(registry, "registry_id"))
                for patient, registry in value or ()
            }
        if name == "metadata":
            return dict(value or {})
        if name in {"density", "exam_type", "visit_type", "modality"}:
            return Code.coerce(value)
        return value

    def _prepare_update(self, values: Dict[str, Any]) -> Dict[str, Any]:
        # A caller changing the owner chooses it explicitly; claim
        # reconciliation passes _owner_explicit itself.
        if "patient_id" in values and "_owner_explicit" not in values:
            values["_owner_explicit"] = True
        return values

    def _renamed_reference(self, field: str) -> Dict[str, Any]:
        # A rekeyed patient keeps its exams even though the source claims
        # still name the old ID.
        return {"_owner_explicit": True} if field == "patient_id" else {}

    @property
    def owner_explicit(self) -> bool:
        """Whether ``patient_id`` was chosen explicitly and survives source claims."""

        return bool(self.__dict__.get("_owner_explicit", False))

    # -- related entities --------------------------------------------------

    def _children(self, kind: str) -> Tuple[Any, ...]:
        graph = self.graph
        return graph.children(self, kind) if graph is not None else ()

    @property
    def patient(self) -> Optional["Patient"]:
        """The owning patient if registered, else None."""

        graph = self.graph
        return graph.patient(self.patient_id) if graph is not None and self.patient_id else None

    @property
    def findings(self) -> Tuple["Finding", ...]:
        """Findings of this exam."""

        return self._children("finding")

    @property
    def images(self) -> Tuple["MammogramImage", ...]:
        """Images of this exam."""

        return self._children("image")

    @property
    def procedures(self) -> Tuple["Procedure", ...]:
        """Procedures attached to this exam or to any of its findings, once each."""

        return _unique([*self._children("procedure"), *(p for f in self.findings for p in f.procedures)])

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        """Pathology attached to this exam, its procedures or its findings, once each."""

        return _unique(
            [
                *self._children("pathology"),
                *(item for procedure in self.procedures for item in procedure.pathology),
                *(item for finding in self.findings for item in finding.pathology),
            ]
        )

    @property
    def registry_entries(self) -> Tuple["CancerRegistryEntry", ...]:
        """Registered cancer-registry entries assigned to this exam."""

        return self._children("registry")

    @property
    def linked_exams(self) -> Tuple["Exam", ...]:
        """Registered exams linked to this one from either side."""

        graph = self.graph
        return graph.linked_exams(self) if graph is not None else ()

    @property
    def breast_sides(self) -> Mapping[Laterality, BreastSide]:
        """Left and right views that have at least one finding or image."""

        sides: Dict[Laterality, Dict[str, list]] = {}
        for finding in self.findings:
            for side in finding.laterality.expand():
                sides.setdefault(side, {"findings": [], "images": []})["findings"].append(finding)
        for image in self.images:
            if image.laterality.is_unilateral:
                sides.setdefault(image.laterality, {"findings": [], "images": []})["images"].append(image)
        return readonly_mapping(
            {
                side: BreastSide(self.accession_number, side, tuple(items["findings"]), tuple(items["images"]))
                for side, items in sorted(sides.items(), key=lambda item: item[0].value)
            }
        )

    # -- building ----------------------------------------------------------

    def add_finding(self, finding: "Finding") -> "Finding":
        """Attach a finding with this accession and return it.

        Raises
        ------
        ValueError
            The finding has another accession, or its key is already taken.
        """

        return ensure_graph(self).attach(self, finding)

    def add_image(self, image: "MammogramImage") -> "MammogramImage":
        """Attach an image to this exam and return it.

        Raises
        ------
        ValueError
            The image has another accession, or its key or SOP UID is taken.
        """

        return ensure_graph(self).attach(self, image)

    def add_procedure(self, procedure: "Procedure") -> "Procedure":
        """Attach a procedure directly to this exam and return it."""

        return ensure_graph(self).attach(self, procedure)

    def add_pathology(self, pathology: "Pathology") -> "Pathology":
        """Attach a pathology bundle directly to this exam and return it."""

        return ensure_graph(self).attach(self, pathology)

    def add_registry_entry(self, entry: "CancerRegistryEntry") -> "CancerRegistryEntry":
        """Assign a cancer-registry entry to this exam and return it."""

        return ensure_graph(self).attach(self, entry)

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "accession_number": self.accession_number,
            "patient_id": self.patient_id,
            "asserted_patient_ids": self.asserted_patient_ids,
            "owner_explicit": self.owner_explicit,
            "exam_date": self.exam_date,
            "description": self.description,
            "density": self.density,
            "exam_type": self.exam_type,
            "visit_type": self.visit_type,
            "modality": self.modality,
            "patient_age": self.patient_age,
            "linked_accessions": self.linked_accessions,
            "registry_references": self.registry_references,
            "metadata": self.metadata,
            "source": self.source,
        }


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _unique(items: Iterable[Any]) -> Tuple[Any, ...]:
    seen: Set[int] = set()
    result = []
    for item in items:
        if id(item) not in seen:
            seen.add(id(item))
            result.append(item)
    return tuple(result)
