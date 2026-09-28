"""Patients, their reported attributes over time and their reported history."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Tuple, Type, Union

from embed_data_graph.clinical.attributes import PatientAttributeObservation
from embed_data_graph.clinical.histories import (
    MedicationHistoryObservation,
    PatientHistoryObservation,
    ProcedureHistoryObservation,
)
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

    Notes
    -----
    ``exams`` are the registered exams whose owner is this patient; a patient
    without a graph has none.
    """

    kind = "patient"
    __key_fields__ = ("patient_id",)

    patient_id: str
    """Patient identifier; the key."""
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
    ) -> None:
        super().__init__()
        self.patient_id = patient_id
        self.sex = sex
        self.birth_year = birth_year
        self.race = race
        self.ethnicity = ethnicity
        self.metadata = dict(metadata or {})
        self.source = source
        self._attribute_observations: List[PatientAttributeObservation] = []
        self._history_observations: List[PatientHistoryObservation] = []
        for observation in attribute_observations or ():
            self.add_attribute_observation(observation)
        for history in history_observations or ():
            self.add_history_observation(history)

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
    def findings(self) -> Tuple["Finding", ...]:
        """Findings of this patient's exams."""

        return tuple(finding for exam in self.exams for finding in exam.findings)

    @property
    def procedures(self) -> Tuple["Procedure", ...]:
        """Procedures of this patient's exams, once each."""

        return _unique(procedure for exam in self.exams for procedure in exam.procedures)

    @property
    def pathology(self) -> Tuple["Pathology", ...]:
        """Pathology of this patient's exams, once each."""

        return _unique(item for exam in self.exams for item in exam.pathology)

    @property
    def registry_entries(self) -> Tuple["CancerRegistryEntry", ...]:
        """Registry entries assigned to this patient's exams, once each."""

        return _unique(entry for exam in self.exams for entry in exam.registry_entries)

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
            that latest date disagree. Undated observations and explicit nulls
            are ignored, so later information never leaks into an earlier date.

        Examples
        --------
        >>> patient = Patient("P1", attribute_observations=[
        ...     PatientAttributeObservation("sex", "F", "A1", date(2020, 1, 1)),
        ...     PatientAttributeObservation("sex", "U", "A2", date(2022, 1, 1)),
        ... ])
        >>> patient.attribute_as_of("sex", date(2021, 6, 1))
        'F'
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
            return None
        latest = max(_context_date(item) for item in eligible)
        values: List[Any] = []
        for item in eligible:
            if item.context_date == latest and item.value not in values:
                values.append(item.value)
        return values[0] if len(values) == 1 else None

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
        kind : type or {"medication", "procedure"}
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
            "birth_year": self.birth_year,
            "race": self.race,
            "ethnicity": self.ethnicity,
            "attribute_observations": self.attribute_observations,
            "history_observations": self.history_observations,
            "metadata": self.metadata,
            "source": self.source,
        }


def _context_date(item: PatientAttributeObservation) -> date:
    assert item.context_date is not None
    return item.context_date


def _history_type(kind: Union[Type[PatientHistoryObservation], str]) -> Type[PatientHistoryObservation]:
    if isinstance(kind, str):
        names = {"medication": MedicationHistoryObservation, "procedure": ProcedureHistoryObservation}
        if kind.lower() not in names:
            raise TypeError("history kind must be 'medication', 'procedure' or a history class")
        return names[kind.lower()]
    if isinstance(kind, type) and issubclass(kind, PatientHistoryObservation):
        return kind
    raise TypeError("history kind must be 'medication', 'procedure' or a history class")


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
