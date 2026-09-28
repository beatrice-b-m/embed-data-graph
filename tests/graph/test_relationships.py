"""Ownership, linked exams, registry assignments and source aliases."""

import pytest

from embed_data_graph import CancerRegistryEntry, DatasetGraph, Exam, MammogramImage, Patient, RegionOfInterest


@pytest.mark.parametrize("claims", [("P", "Q"), ("Q", "P")])
def test_conflicting_claims_leave_the_exam_unowned_in_any_order(claims):
    graph = DatasetGraph()
    graph.register(Patient("P")), graph.register(Patient("Q"))
    exam = graph.register(Exam("A"))
    for claim in claims:
        graph.claim_patient(exam, [claim])

    assert exam.patient_id is None
    assert not graph.patient("P").exams and not graph.patient("Q").exams


def test_explicit_owner_persists_through_later_claims():
    graph = DatasetGraph()
    exam = graph.register(Exam("A", asserted_patient_ids=["P", "Q"]))

    graph.assign_patient(exam, "P")
    graph.claim_patient(exam, ["R"])

    assert exam.patient_id == "P" and exam.owner_explicit
    assert exam.asserted_patient_ids == {"P", "Q", "R"}


def test_setting_the_owner_to_none_clears_it_explicitly():
    graph = DatasetGraph()
    patient = graph.register(Patient("P"))
    exam = patient.add_exam(Exam("A"))

    exam.update(patient_id=None)

    assert exam.patient_id is None and exam.owner_explicit and not patient.exams


def test_assigning_an_exam_of_another_graph_is_rejected():
    exam = DatasetGraph().register(Exam("A"))

    with pytest.raises(ValueError):
        DatasetGraph().assign_patient(exam, "P")


def test_image_patient_id_is_a_source_claim_not_ownership():
    graph = DatasetGraph()
    exam = graph.register(Exam("A", patient_id="P"))
    image = exam.add_image(MammogramImage("I", accession_number="A", patient_id="Q"))

    assert image.patient_id == "Q" and exam.patient_id == "P"


def test_linked_exams_are_symmetric_and_resolve_when_the_target_arrives():
    graph = DatasetGraph()
    a = graph.register(Exam("A"))
    graph.set_linked_accessions(a, ["B"])
    assert not a.linked_exams and graph.unresolved_references

    b = graph.register(Exam("B"))

    assert a.linked_exams == (b,) and b.linked_exams == (a,)


def test_a_link_stated_by_either_side_survives_clearing_the_other():
    graph = DatasetGraph()
    a, b = graph.register(Exam("A")), graph.register(Exam("B"))
    graph.set_linked_accessions(a, ["B"])
    graph.set_linked_accessions(b, ["A"])

    graph.set_linked_accessions(a, [])

    assert a.linked_exams == (b,) and b.linked_exams == (a,)


def test_merge_extends_links_and_refresh_replaces_them():
    graph = DatasetGraph()
    a = graph.register(Exam("A", linked_accessions=["B"]))

    graph.set_linked_accessions(a, ["C"], merge=True)
    assert a.linked_accessions == {"B", "C"}
    graph.set_linked_accessions(a, ["D"])
    assert a.linked_accessions == {"D"}


def test_a_registry_entry_is_shared_by_exams_and_never_deleted_by_clearing():
    graph = DatasetGraph()
    a, b = graph.register(Exam("A")), graph.register(Exam("B"))
    entry = graph.register(CancerRegistryEntry("P", "1"))
    graph.set_registry_assignments(a, [("P", "1")])
    graph.set_registry_assignments(b, [("P", "1")])

    assert a.registry_entries == b.registry_entries == (entry,)
    assert set(entry.exams) == {a, b}
    graph.set_registry_assignments(a, [])
    assert not a.registry_entries and entry.graph is graph


def test_source_aliases_follow_updates_and_leave_with_pop():
    graph = DatasetGraph()
    image = graph.register(MammogramImage("I", source_sop_instance_uid="S1", source_paths={"/old"}))
    roi = image.add_roi(RegionOfInterest((0, 0, 1, 1), "I", "0", collection_position=0))

    image.update(source_sop_instance_uid="S2", source_paths={"/new"})

    assert graph.source_image("S1") is None and graph.image_at_path("/old") is None
    assert graph.source_image("S2") is image and graph.roi_at_source("/new", 0) is roi
    graph.pop(image)
    assert graph.source_image("S2") is None and graph.roi_at_source("/new", 0) is None


def test_two_original_images_cannot_share_a_source_sop_uid():
    graph = DatasetGraph()
    first = graph.register(MammogramImage("I", source_sop_instance_uid="S1"))
    graph.register(MammogramImage("J", source_sop_instance_uid="S2"))

    with pytest.raises(ValueError):
        first.update(source_sop_instance_uid="S2", height=5)
    assert first.source_sop_instance_uid == "S1" and first.height is None
    derived = graph.register(MammogramImage("K", source_sop_instance_uid="S1", derived_from="I"))
    assert graph.source_image("S1") is first and derived.graph is graph


def test_a_derivative_cannot_become_an_original_with_a_taken_source_uid():
    graph = DatasetGraph()
    original = graph.register(MammogramImage("I", source_sop_instance_uid="S"))
    derivative = graph.register(MammogramImage("D", source_sop_instance_uid="S", derived_from="I"))

    with pytest.raises(ValueError):
        derivative.update(derived_from=None)
    assert derivative.derived_from == "I" and graph.source_image("S") is original
