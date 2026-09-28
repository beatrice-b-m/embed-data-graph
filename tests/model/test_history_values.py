"""Reported patient history stored on the patient."""

from copy import deepcopy

import pytest

from embed_data_graph import Code, Patient, validate
from embed_data_graph.clinical.histories import (
    HistoryTimeEstimate,
    MedicationHistoryObservation,
    ProcedureHistoryObservation,
)
from embed_data_graph.core.primitives import Laterality


def medication(code="ESTRO", **fields):
    return MedicationHistoryObservation(category="H", medication=code, **fields)


def test_time_estimate_keeps_raw_numbers_and_leaves_ranges_to_validation():
    estimate = HistoryTimeEstimate(age=-4, year=0, month=13)

    assert estimate.to_dict() == {"age": -4, "year": 0, "month": 13}
    assert not validate(estimate).valid
    assert HistoryTimeEstimate().is_empty


def test_empty_timing_is_stored_as_none():
    assert medication(started=HistoryTimeEstimate()).started is None


def test_patient_separates_medication_and_procedure_history():
    exposure = medication(current=True, started=HistoryTimeEstimate(age=52, year=2018))
    procedure = ProcedureHistoryObservation(category="B", procedure="1", laterality="L")
    patient = Patient("P1", history_observations=[exposure, procedure])

    assert patient.medication_history == (exposure,)
    assert patient.procedure_history == (procedure,)
    assert procedure.laterality is Laterality.LEFT
    assert patient.add_history_observation(exposure) is exposure


def test_unkeyed_reports_are_separate_facts_even_when_similar():
    patient = Patient("P1")
    first = patient.add_history_observation(medication())
    second = patient.add_history_observation(medication())

    assert patient.medication_history == (first, second)


def test_keyed_record_is_updated_in_place_by_a_snapshot():
    keyed = medication(record_id="m1")
    procedure = ProcedureHistoryObservation(category="B", procedure="1")
    patient = Patient("P1", history_observations=[keyed, procedure])

    patient.set_history_snapshot([medication("TAMOX", record_id="m1"), procedure])

    assert patient.medication_history == (keyed,)
    assert keyed.medication == Code("TAMOX")
    assert patient.update_history("m1", medication="RA") is keyed
    assert keyed.medication == Code("RA")


def test_replacing_one_history_kind_keeps_the_other():
    procedure = ProcedureHistoryObservation(category="B", procedure="1")
    patient = Patient("P1", history_observations=[medication(), procedure])
    replacement = medication("RA")

    patient.replace_history("medication", [replacement])

    assert patient.medication_history == (replacement,)
    assert patient.procedure_history == (procedure,)


def test_text_codes_become_codes_without_meaning():
    record = medication(record_id=" m1 ")

    assert record.category == Code("H") and record.medication == Code("ESTRO")
    assert record.medication.meaning is None
    assert record.record_id == "m1"
    assert record.to_dict()["medication"] == {"code": "ESTRO", "meaning": None}


def test_update_revalidates_fields():
    record = medication()

    with pytest.raises(ValueError):
        record.update(medication="  ")


def test_history_subclasses_copy_independently():
    class LocalMedication(MedicationHistoryObservation):
        pass

    original = LocalMedication(category="H", medication="ESTRO", started=HistoryTimeEstimate(age=52))
    copied = deepcopy(original)

    assert isinstance(copied, LocalMedication) and copied is not original
    copied.update(comment="changed")
    assert original.comment is None
