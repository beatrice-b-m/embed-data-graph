"""Patients, their reported attributes over time and their reported history."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Tuple, Type, Union

from embed_data_graph.clinical.attributes import AttributeResolution, AttributeStatus, PatientAttributeObservation
from embed_data_graph.clinical.histories import (
    CancerHistoryObservation,
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_graph.clinical.incomplete import InvalidAccessionRecord
from embed_data_graph.clinical.pathology import UnkeyedRegistryEntry, UnresolvedClinicalRecord
from embed_data_graph.core.entity import MutableEntity
from embed_data_graph.core.graph import ensure_graph

if TYPE_CHECKING:
    from embed_data_graph.clinical.exams import Exam
    from embed_data_graph.clinical.findings import Finding
    from embed_data_graph.clinical.pathology import CancerRegistryEntry, Pathology
    from embed_data_graph.clinical.procedures import Procedure


class Patient(MutableEntity):
    """A patient, keyed by patient ID, with reported attributes and history.

    Parameters
    ----------
    patient_id : str
        Non-empty patient identifier; the key.
    sex : str or None, optional
        Reported sex when every attribute observation agrees; None when absent
        or varying over time (see ``attribute_as_of``). Default None.
    race, ethnicity : str or None, optional
        Reported race and ethnicity when every observation agrees; None when
        absent or varying. Default None.
    birth_year : int or None, optional
        Reported birth year; validate checks plausibility. Default None.
    attribute_observations : iterable of PatientAttributeObservation, optional
        Reported attribute values, one per exam context.
    history_observations : iterable of PatientHistoryObservation, optional
        Reported medication and procedure history.
    metadata : mapping, optional
        Consumer metadata, copied into a dict.
    source : SourceRef or None, optional
        Row the patient was read from.
    unkeyed_registry_entries : iterable of UnkeyedRegistryEntry, optional
        Registry records of this patient that have no registry ID.

    cohort_number : str or None, optional
        Opaque source cohort number; default None.

    Notes
    -----
    ``exams`` are the registered exams whose owner is this patient; a patient
    without a graph has none. The patient's complete registry record is
    ``registry_entries`` together with ``unkeyed_registry_entries``.
    """

    kind = "patient"
    __key_fields__ = ("patient_id",)

    patient_id: str
    """Patient identifier; the key."""
    cohort_number: Optional[str]
    """Opaque source cohort number; None when absent or varying."""
    sex: Optional[str]
    """Reported sex when all observations agree; None if absent or varying."""
    race: Optional[str]
    """Reported race when all observations agree; None if absent or varying."""
    ethnicity: Optional[str]
    """Reported ethnicity when all observations agree; None if absent or varying."""
    birth_year: Optional[int]
    """Reported birth year; validate checks plausibility."""
    metadata: Dict[str, Any]
    """Consumer metadata."""
    source: Optional[object]
    """Row the patient was read from."""

    def __init__(
        self,
        patient_id: str,
        sex: Optional[str] = None,
        birth_year: Optional[int] = None,
        race: Optional[str] = None,
        ethnicity: Optional[str] = None,
        attribute_observations: Optional[Iterable[PatientAttributeObservation]] = None,
        history_observations: Optional[Iterable[PatientHistoryObservation]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        source: Optional[object] = None,
        unkeyed_registry_entries: Optional[Iterable[UnkeyedRegistryEntry]] = None,
        cohort_number: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.patient_id = patient_id
        self.cohort_number = cohort_number
        self.sex = sex
        self.birth_year = birth_year
        self.race = race
        self.ethnicity = ethnicity
        self.metadata = dict(metadata or {})
        self.source = source
        self._invalid_accessions: Dict[str, Tuple[InvalidAccessionRecord, ...]] = {}
        self._attribute_observations: List[PatientAttributeObservation] = []
        self._history_observations: List[PatientHistoryObservation] = []
        for observation in attribute_observations or ():
            self.add_attribute_observation(observation)
        for history in history_observations or ():
            self.add_history_observation(history)
        self._unkeyed_registry_entries: List[UnkeyedRegistryEntry] = []
        self._unresolved_clinical: Dict[Any, List[UnresolvedClinicalRecord]] = {}
        self.set_unkeyed_registry_entries(unkeyed_registry_entries or ())

    def _coerce(self, name: str, value: Any) -> Any:
        if name == "patient_id":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("patient_id must be a non-empty string")
            return value.strip()
        if name == "metadata":
            return dict(value or {})
        return value

    # -- exams and aggregates ------------------------------------------------

    @property
    def exams(self) -> Tuple["Exam", ...]:
        """Registered exams owned by this patient."""

        graph = self.graph
        return graph.children(self, "exam") if graph is not None else ()

    @property
    def invalid_accession_records(self) -> Tuple[InvalidAccessionRecord, ...]:
        """Patient-scoped rows excluded from exams by invalid accession policy.

        Snapshot records are grouped by source table; no row is an exam or a
        synthetic clinical identity. Detached/copied patients retain the data.
        """

        return tuple(item for table in sorted(self._invalid_accessions)
                     for item in self._invalid_accessions[table])

    @property
    def claimed_exams(self) -> Tuple["Exam", ...]:
        """Owned exams first, then remaining source-claimed exams, once each.

        Each group follows registration order. Includes contested exams without
        assigning ownership. Inspect
        ``exam.contested`` and ``exam.patient_id`` before attributing results.
        Returns an empty tuple when detached; objects remain live graph members.
        """

        graph = self.graph
        if graph is None:
            return ()
        return _unique([*self.exams, *graph._claimants.get(self.patient_id, {}).values()])

    @property
    def findings(self) -> Tuple["Finding", ...]:
        """Findings of this patient's exams."""

        return tuple(finding for exam in self.exams for finding in exam.findings)

    @property
    def procedures(self) -> Tuple["Procedure", ...]:
        """Procedures of this patient, once each.

        Procedures whose identity names this patient come first, in
        registration order, whether or not they are attached to an exam; then
        those reached through the patient's exams. Rows that could not resolve
        a procedure identity are in ``unresolved_clinical_records``.
        """

        graph = self.graph
        if graph is None:
            return ()
        named = graph._scoped_to(self.patient_id, "procedure")
        return _unique([*named, *(procedure for exam in self.exams for procedure in exam.procedures)])

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        """Pathology of this patient, once each.

        Bundles whose identity names this patient come first, in registration
        order, whether or not an exam reaches them; then those reached through
        the patient's exams.
        """

        graph = self.graph
        if graph is None:
            return ()
        named = graph._scoped_to(self.patient_id, "pathology")
        return _unique([*named, *(item for exam in self.exams for item in exam.pathology)])

    @property
    def registry_entries(self) -> Tuple["CancerRegistryEntry", ...]:
        """Keyed registry entries of this patient, once each.

        Entries whose key names this patient come first, in registration
        order, whether or not any exam is assigned to them. Entries of another
        patient that are assigned to this patient's exams follow. A patient
        without a graph has none. Registry rows without a registry ID are in
        ``unkeyed_registry_entries``.
        """

        graph = self.graph
        if graph is None:
            return ()
        named = graph._scoped_to(self.patient_id, "registry")
        return _unique([*named, *(entry for exam in self.exams for entry in exam.registry_entries)])

    @property
    def unresolved_clinical_records(self) -> Tuple[UnresolvedClinicalRecord, ...]:
        """Procedure and pathology rows naming this patient whose identity is unresolved.

        Records are grouped by the attachment they were loaded under (this
        patient for a row without an accession, else its exam, finding or
        procedure), in the order those attachments were first loaded. A record
        whose side was not reported has UNKNOWN laterality. Each load replaces
        the records of the attachments it addresses, as it does in
        ``graph.unresolved_records``; this is the same data, typed and
        selected by the patient each row names.

        Examples
        --------
        >>> from embed_data_graph import load_embed
        >>> graph = load_embed(pathology=[{"empi_anon": "P1", "acc_anon": "A1", "numfind": 1,
        ...     "procdate_anon": "2020-01-02", "type": "B", "path_severity": 0}]).graph
        >>> (record,) = graph.patient("P1").unresolved_clinical_records
        >>> record.severity.name, record.laterality.value
        ('INVASIVE_BREAST_CANCER', 'UNKNOWN')
        """

        return tuple(record for records in self._unresolved_clinical.values() for record in records)

    def _set_unresolved_clinical(self, address: Any, records: Iterable[UnresolvedClinicalRecord]) -> None:
        """Replace this patient's records at one unresolved-record address; used by loaders."""

        stored = list(records)
        if stored:
            self._unresolved_clinical[address] = stored
        else:
            self._unresolved_clinical.pop(address, None)

    @property
    def unkeyed_registry_entries(self) -> Tuple[UnkeyedRegistryEntry, ...]:
        """Registry records of this patient without a registry ID, in stored order.

        They are the latest snapshot loaded for this patient. No exam is
        assigned to them and none is the same record as a keyed entry.
        """

        return tuple(self._unkeyed_registry_entries)

    def set_unkeyed_registry_entries(
        self, entries: Iterable[UnkeyedRegistryEntry]
    ) -> Tuple[UnkeyedRegistryEntry, ...]:
        """Replace the unkeyed registry snapshot and return the stored records.

        Parameters
        ----------
        entries : iterable of UnkeyedRegistryEntry
            The complete replacement, stored in the given order; empty clears it.

        Returns
        -------
        tuple of UnkeyedRegistryEntry
            The stored records, the same objects that were passed.

        Raises
        ------
        TypeError
            A value is not an UnkeyedRegistryEntry. Nothing changes then.
        """

        replacement = list(entries)
        if any(not isinstance(item, UnkeyedRegistryEntry) for item in replacement):
            raise TypeError("unkeyed registry entries must be UnkeyedRegistryEntry values")
        self._unkeyed_registry_entries = replacement
        return tuple(replacement)

    def add_exam(self, exam: "Exam") -> "Exam":
        """Make this patient the exam's owner and source claim; return the exam.

        Raises
        ------
        ValueError
            The exam already names another owner, or its key is taken.
        """

        if exam.patient_id is not None and exam.patient_id != self.patient_id:
            raise ValueError("Exam patient_id must match Patient patient_id")
        graph = ensure_graph(self)
        graph.register(exam)
        graph.update(
            exam,
            patient_id=self.patient_id,
            asserted_patient_ids={*exam.asserted_patient_ids, self.patient_id},
            _owner_explicit=exam.owner_explicit,
        )
        return exam

    # -- attributes over time ------------------------------------------------

    @property
    def attribute_observations(self) -> Tuple[PatientAttributeObservation, ...]:
        """Reported attribute values, one per exam context, in insertion order."""

        return tuple(self._attribute_observations)

    def add_attribute_observation(self, observation: PatientAttributeObservation) -> PatientAttributeObservation:
        """Record an attribute observation, replacing one with the same context.

        Raises
        ------
        TypeError
            ``observation`` is not a PatientAttributeObservation.
        """

        if not isinstance(observation, PatientAttributeObservation):
            raise TypeError("observation must be a PatientAttributeObservation")
        for index, existing in enumerate(self._attribute_observations):
            if existing.context == observation.context:
                self._attribute_observations[index] = observation
                return observation
        self._attribute_observations.append(observation)
        return observation

    def replace_attribute_history(
        self, attribute: str, observations: Iterable[PatientAttributeObservation]
    ) -> Tuple[PatientAttributeObservation, ...]:
        """Replace every observation of one attribute and keep the others.

        Parameters
        ----------
        attribute : str
            Attribute whose observations are replaced.
        observations : iterable of PatientAttributeObservation
            The complete replacement; empty clears the attribute. Observations
            sharing a context replace one another, last wins.

        Returns
        -------
        tuple of PatientAttributeObservation
            The stored observations of ``attribute`` in insertion order.

        Raises
        ------
        TypeError
            A value is not a PatientAttributeObservation.
        ValueError
            A value is an observation of another attribute. Nothing changes
            in either case.
        """

        replacement = list(observations)
        if any(not isinstance(item, PatientAttributeObservation) for item in replacement):
            raise TypeError("observations must be PatientAttributeObservation values")
        if any(item.attribute != attribute for item in replacement):
            raise ValueError("every observation must be of the replaced attribute")
        self._attribute_observations = [item for item in self._attribute_observations if item.attribute != attribute]
        for item in replacement:
            self.add_attribute_observation(item)
        return tuple(item for item in self._attribute_observations if item.attribute == attribute)

    def attribute_history(self, attribute: str) -> Tuple[PatientAttributeObservation, ...]:
        """Return the observations of one attribute, dated ones first by date.

        Undated observations follow in insertion order. Values are as reported,
        including explicit nulls.
        """

        matching = [item for item in self._attribute_observations if item.attribute == attribute]
        dated = sorted((item for item in matching if item.context_date is not None), key=_context_date)
        return (*dated, *(item for item in matching if item.context_date is None))

    def attribute_as_of(self, attribute: str, as_of: date) -> Any:
        """Return the latest reported value of ``attribute`` on or before ``as_of``.

        Parameters
        ----------
        attribute : str
            Attribute name, such as ``"sex"``.
        as_of : datetime.date
            Inclusive cutoff compared with each observation's ``context_date``.

        Returns
        -------
        Any
            The value from the latest dated observation that reports a value.
            None when no dated observation qualifies or when observations on
            that latest date disagree; ``attribute_resolution`` tells the two
            apart. Undated observations and explicit nulls are ignored, so
            later information never leaks into an earlier date.

        Examples
        --------
        >>> patient = Patient("P1", attribute_observations=[
        ...     PatientAttributeObservation("sex", "F", "A1", date(2020, 1, 1)),
        ...     PatientAttributeObservation("sex", "U", "A2", date(2022, 1, 1)),
        ... ])
        >>> patient.attribute_as_of("sex", date(2021, 6, 1))
        'F'
        """

        return self.attribute_resolution(attribute, as_of).value

    def attribute_resolution(self, attribute: str, as_of: date) -> AttributeResolution:
        """Return ``attribute`` as of ``as_of`` with the reason for its value.

        Applies the same rule as ``attribute_as_of``, and tells absence from
        conflict: the status is NOT_REPORTED when no dated observation on or
        before ``as_of`` reports a value, and CONFLICT when the observations
        on the latest qualifying date disagree.

        Parameters
        ----------
        attribute : str
            Attribute name, such as ``"menarche_age"``.
        as_of : datetime.date
            Inclusive cutoff compared with each observation's ``context_date``.

        Returns
        -------
        AttributeResolution
            Status, agreed value, latest qualifying date and its candidates.

        Examples
        --------
        >>> patient = Patient("P1", attribute_observations=[
        ...     PatientAttributeObservation("menarche_age", 12, "A1", date(2018, 1, 1)),
        ...     PatientAttributeObservation("menarche_age", 12, "A2", date(2020, 1, 1)),
        ...     PatientAttributeObservation("menarche_age", 13, "A3", date(2020, 1, 1)),
        ... ])
        >>> resolution = patient.attribute_resolution("menarche_age", date(2021, 1, 1))
        >>> resolution.status.value, resolution.candidates
        ('conflict', (12, 13))
        """

        eligible = [
            item
            for item in self._attribute_observations
            if item.attribute == attribute
            and item.value is not None
            and item.context_date is not None
            and item.context_date <= as_of
        ]
        if not eligible:
            return AttributeResolution(attribute, as_of, AttributeStatus.NOT_REPORTED)
        latest = max(_context_date(item) for item in eligible)
        values: List[Any] = []
        for item in eligible:
            if item.context_date == latest and item.value not in values:
                values.append(item.value)
        if len(values) == 1:
            return AttributeResolution(attribute, as_of, AttributeStatus.REPORTED, values[0], latest, tuple(values))
        return AttributeResolution(attribute, as_of, AttributeStatus.CONFLICT, None, latest, tuple(values))

    # -- reported history ------------------------------------------------------

    @property
    def history_observations(self) -> Tuple[PatientHistoryObservation, ...]:
        """Reported history in stored order."""

        return tuple(self._history_observations)

    @property
    def medication_history(self) -> Tuple[MedicationHistoryObservation, ...]:
        """Reported hormone, medication and treatment exposures."""

        return tuple(item for item in self._history_observations if isinstance(item, MedicationHistoryObservation))

    @property
    def procedure_history(self) -> Tuple[ProcedureHistoryObservation, ...]:
        """Reported prior procedures; not verified current-exam procedures."""

        return tuple(item for item in self._history_observations if isinstance(item, ProcedureHistoryObservation))

    @property
    def cancer_history(self) -> Tuple[CancerHistoryObservation, ...]:
        """Reported cancer history about the patient or a relative; see ``about_relative``."""

        return tuple(item for item in self._history_observations if isinstance(item, CancerHistoryObservation))

    def history_known_on(self, observation: PatientHistoryObservation) -> Optional[date]:
        """Return the date a reported history fact was known, or None.

        Reported history is captured at the intake of the exam it came with,
        so a fact was known on its context exam's date. That exam is looked up
        on each call, so it may be loaded before or after the history. The
        result is None when the observation has no context accession, the
        exam is not in the graph, it belongs to or is claimed by another
        patient, or it has no ISO exam date. It is not when the reported event
        happened.

        Examples
        --------
        >>> from embed_data_graph import load_embed
        >>> graph = load_embed(
        ...     exams=[{"acc_anon": "A1", "empi_anon": "P1", "studydate_anon": "2020-03-04"}],
        ...     hormone_history=[{"empi_anon": "P1", "acc_anon": "A1", "type": "H", "code": "TAMOX"}],
        ... ).graph
        >>> patient = graph.patient("P1")
        >>> patient.history_known_on(patient.medication_history[0])
        datetime.date(2020, 3, 4)
        """

        return self._history_anchor(observation)[0]

    def history_as_of(
        self,
        as_of: date,
        kind: Union[Type[PatientHistoryObservation], str, None] = None,
    ) -> Tuple[PatientHistoryObservation, ...]:
        """Return the reported history known on or before ``as_of``, in stored order.

        Parameters
        ----------
        as_of : datetime.date
            Inclusive cutoff compared with ``history_known_on``.
        kind : type, {"medication", "procedure", "cancer"} or None, optional
            Only this kind of history; None (default) returns every kind.

        Returns
        -------
        tuple of PatientHistoryObservation
            Facts whose context exam date is on or before ``as_of``. Facts
            without a resolvable date are excluded, so later information never
            leaks into an earlier date.
        """

        selected = PatientHistoryObservation if kind is None else _history_type(kind)
        result = []
        for item in self._history_observations:
            known = self.history_known_on(item) if isinstance(item, selected) else None
            if known is not None and known <= as_of:
                result.append(item)
        return tuple(result)

    def _history_anchor(self, observation: PatientHistoryObservation) -> Tuple[Optional[date], Optional[str]]:
        """Return the known-on date of a history fact, or None and why not."""

        accession = getattr(observation, "context_accession", None)
        if accession is None:
            return None, "missing_context_accession"
        graph = self.graph
        exam = graph.exam(accession) if graph is not None else None
        if exam is None:
            return None, "context_exam_not_loaded"
        owned = exam.patient_id == self.patient_id or (
            exam.patient_id is None and exam.asserted_patient_ids <= {self.patient_id}
        )
        if not owned:
            return None, "context_exam_ownership_ambiguous"
        day = _iso_day(exam.exam_date)
        if day is None:
            return None, "context_exam_without_date"
        return day, None

    def add_history_observation(self, observation: PatientHistoryObservation) -> PatientHistoryObservation:
        """Add a reported fact, or update the stored record with the same record ID.

        A keyed observation whose type and ``record_id`` match a stored one
        updates that stored object in place and returns it. Unkeyed facts are
        appended; the same object is stored once.

        Raises
        ------
        TypeError
            ``observation`` is not a PatientHistoryObservation.
        """

        if not isinstance(observation, PatientHistoryObservation):
            raise TypeError("observation must be a PatientHistoryObservation")
        for existing in self._history_observations:
            if existing is observation:
                return existing
            if existing.record_id is not None and _same_record(existing, observation):
                _copy_fields(existing, observation)
                return existing
        self._history_observations.append(observation)
        return observation

    def set_history_snapshot(self, values: Iterable[PatientHistoryObservation]) -> Tuple[PatientHistoryObservation, ...]:
        """Replace the whole history, keeping stored objects for matching record IDs.

        Returns the stored history. An empty iterable clears it.

        Raises
        ------
        TypeError
            A value is not a history observation.
        ValueError
            Two values share a type and record ID.
        """

        replacement = tuple(values)
        if any(not isinstance(item, PatientHistoryObservation) for item in replacement):
            raise TypeError("history snapshot must contain history observations")
        stored = {(type(item), item.record_id): item for item in self._history_observations if item.record_id is not None}
        result: List[PatientHistoryObservation] = []
        seen = set()
        for item in replacement:
            if item.record_id is None:
                result.append(item)
                continue
            key = (type(item), item.record_id)
            if key in seen:
                raise ValueError(f"Duplicate history record_id: {item.record_id}")
            seen.add(key)
            existing = stored.get(key)
            if existing is not None and existing is not item:
                _copy_fields(existing, item)
                result.append(existing)
            else:
                result.append(item)
        self._history_observations = result
        return tuple(result)

    def update_history(self, record_id: object, **values: Any) -> PatientHistoryObservation:
        """Update the history record with ``record_id`` in place and return it.

        Raises
        ------
        KeyError
            No record has this ID.
        ValueError
            The ID is blank or matches several records.
        """

        normalized = str(record_id).strip()
        if not normalized:
            raise ValueError("record_id must be a non-empty value")
        matches = [item for item in self._history_observations if item.record_id == normalized]
        if not matches:
            raise KeyError(f"Unknown history record_id: {normalized}")
        if len(matches) > 1:
            raise ValueError(f"Duplicate history record_id: {normalized}")
        matches[0].update(**values)
        return matches[0]

    def replace_history(
        self,
        kind: Union[Type[PatientHistoryObservation], str],
        items: Iterable[PatientHistoryObservation],
    ) -> Tuple[PatientHistoryObservation, ...]:
        """Replace one kind of history and keep the other.

        Parameters
        ----------
        kind : type or {"medication", "procedure", "cancer"}
            History class, or its short name.
        items : iterable of PatientHistoryObservation
            Replacement observations of that kind; empty clears it.

        Returns
        -------
        tuple
            The stored history of that kind after replacement.
        """

        selected = _history_type(kind)
        replacement = tuple(items)
        if any(not isinstance(item, selected) for item in replacement):
            raise ValueError("history item kind does not match replacement kind")
        kept = [item for item in self._history_observations if not isinstance(item, selected)]
        stored = self.set_history_snapshot([*kept, *replacement])
        return tuple(item for item in stored if isinstance(item, selected))

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "sex": self.sex,
            "cohort_number": self.cohort_number,
            "invalid_accession_records": self.invalid_accession_records,
            "birth_year": self.birth_year,
            "race": self.race,
            "ethnicity": self.ethnicity,
            "attribute_observations": self.attribute_observations,
            "history_observations": self.history_observations,
            "unkeyed_registry_entries": self.unkeyed_registry_entries,
            "unresolved_clinical_records": self.unresolved_clinical_records,
            "metadata": self.metadata,
            "source": self.source,
        }


def _iso_day(value: Optional[str]) -> Optional[date]:
    """Return the date of an ISO ``YYYY-MM-DD`` text, ignoring any time part."""

    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _context_date(item: PatientAttributeObservation) -> date:
    assert item.context_date is not None
    return item.context_date


def _history_type(kind: Union[Type[PatientHistoryObservation], str]) -> Type[PatientHistoryObservation]:
    if isinstance(kind, str):
        names = {
            "medication": MedicationHistoryObservation,
            "procedure": ProcedureHistoryObservation,
            "cancer": CancerHistoryObservation,
        }
        if kind.lower() not in names:
            raise TypeError("history kind must be 'medication', 'procedure', 'cancer' or a history class")
        return names[kind.lower()]
    if isinstance(kind, type) and issubclass(kind, PatientHistoryObservation):
        return kind
    raise TypeError("history kind must be 'medication', 'procedure', 'cancer' or a history class")


def _same_record(left: PatientHistoryObservation, right: PatientHistoryObservation) -> bool:
    return type(left) is type(right) and left.record_id == right.record_id


def _copy_fields(target: PatientHistoryObservation, source: PatientHistoryObservation) -> None:
    target.update(**{name: value for name, value in vars(source).items() if not name.startswith("_")})


def _unique(items: Iterable[Any]) -> Tuple[Any, ...]:
    result: List[Any] = []
    for item in items:
        if all(item is not existing for existing in result):
            result.append(item)
    return tuple(result)
