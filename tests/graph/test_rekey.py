"""Changing keys keeps every stored reference coherent."""

import pytest

from embed_data_graph import (
    CancerRegistryEntry,
    DatasetGraph,
    Exam,
    Finding,
    Laterality,
    MammogramImage,
    Patient,
    Procedure,
    ProcedureIdentity,
    RegionOfInterest,
)
from embed_data_graph.clinical.interpretations import ImagingInterpretation


@pytest.fixture
def tree():
    graph = DatasetGraph()
    patient = graph.register(Patient("P"))
    exam = patient.add_exam(Exam("A"))
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1", interpretation=ImagingInterpretation("N")))
    procedure = finding.add_procedure(Procedure(ProcedureIdentity("P", "2020-01-01", "B", "L")))
    image = exam.add_image(MammogramImage("I", accession_number="A"))
    roi = image.add_roi(RegionOfInterest((0, 0, 1, 1), "I", "0"))
    return graph, patient, exam, finding, procedure, image, roi


def test_exam_rekey_carries_findings_images_and_procedure_references(tree):
    graph, patient, exam, finding, procedure, image, _ = tree
    interpretation = finding.interpretation

    exam.rekey(accession_number="B")

    assert graph.exam("A") is None and graph.exam("B") is exam
    assert graph.finding("B", "1") is finding and graph.finding("A", "1") is None
    assert finding.interpretation is interpretation
    assert image.accession_number == "B" and exam.images == (image,)
    assert procedure.finding_references == {("B", "1")} and finding.procedures == (procedure,)
    assert patient.exams == (exam,)
    assert not graph.unresolved_references


def test_assigning_a_key_field_directly_is_a_rekey(tree):
    graph, _, exam, finding, *_ = tree

    finding.finding_number = "2"

    assert graph.finding("A", "2") is finding and exam.findings == (finding,)


def test_patient_rekey_keeps_exams_and_source_claims(tree):
    graph, patient, exam, *_ = tree

    patient.rekey(patient_id="Q")

    assert graph.patient("Q") is patient and patient.exams == (exam,)
    assert exam.patient_id == "Q" and exam.owner_explicit
    assert exam.asserted_patient_ids == {"P"}


def test_image_rekey_carries_its_rois(tree):
    graph, _, _, _, _, image, roi = tree

    image.rekey(image_id="processed")

    assert graph.roi("processed", "0") is roi and image.rois == (roi,)
    assert graph.image("I") is None


def test_registry_rekey_rewrites_exam_assignments():
    graph = DatasetGraph()
    exam = graph.register(Exam("A"))
    entry = exam.add_registry_entry(CancerRegistryEntry("P", "1"))

    entry.rekey(registry_id="2")

    assert exam.registry_references == {("P", "2")} and exam.registry_entries == (entry,)


def test_linked_accessions_follow_a_rekeyed_exam():
    graph = DatasetGraph()
    a, b = graph.register(Exam("A")), graph.register(Exam("B"))
    graph.set_linked_accessions(b, ["A"])

    a.rekey(accession_number="C")

    assert b.linked_accessions == {"C"} and b.linked_exams == (a,)


def test_collision_anywhere_in_the_cascade_changes_nothing(tree):
    graph, _, exam, finding, *_ = tree
    graph.register(Finding("B", Laterality.RIGHT, "1"))

    with pytest.raises(ValueError):
        exam.rekey(accession_number="B")
    assert exam.accession_number == "A" and graph.finding("A", "1") is finding


def test_rekey_accepts_only_key_fields(tree):
    _, _, exam, *_ = tree

    with pytest.raises(TypeError):
        exam.rekey(description="x")


def test_an_entity_without_a_graph_rekeys_locally():
    finding = Finding("A", Laterality.LEFT, "1")

    finding.rekey(finding_number="2")

    assert finding.key == ("A", "2") and finding.graph is None
