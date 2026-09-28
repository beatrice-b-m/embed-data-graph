"""Collections and views computed from the graph."""

import json

from embed_data_graph import (
    DatasetGraph,
    Exam,
    Finding,
    Laterality,
    MammogramImage,
    Pathology,
    Patient,
    Procedure,
    ProcedureIdentity,
)


def test_bilateral_finding_appears_on_both_breast_sides():
    exam = Exam("A")
    finding = exam.add_finding(Finding("A", Laterality.BILATERAL, "1"))

    assert set(exam.breast_sides) == {Laterality.LEFT, Laterality.RIGHT}
    assert all(side.findings == (finding,) for side in exam.breast_sides.values())


def test_images_of_unknown_laterality_are_on_no_side():
    exam = Exam("A")
    right = exam.add_image(MammogramImage("R", Laterality.RIGHT, accession_number="A"))
    exam.add_image(MammogramImage("U", accession_number="A"))

    assert set(exam.breast_sides) == {Laterality.RIGHT}
    assert exam.breast_sides[Laterality.RIGHT].images == (right,)


def test_breast_sides_follow_a_laterality_change():
    exam = Exam("A")
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))

    finding.update(laterality=Laterality.RIGHT)

    assert set(exam.breast_sides) == {Laterality.RIGHT}
    assert exam.breast_sides[Laterality.RIGHT].findings == (finding,)


def test_procedures_and_pathology_aggregate_up_to_the_patient_once_each():
    patient = Patient("P")
    exam = patient.add_exam(Exam("A"))
    first = exam.add_finding(Finding("A", Laterality.LEFT, "1"))
    second = exam.add_finding(Finding("A", Laterality.LEFT, "2"))
    procedure = first.add_procedure(Procedure(ProcedureIdentity("P", "2020-01-01", "B", "L")))
    second.add_procedure(procedure)
    pathology = procedure.add_pathology(Pathology(("P", "R1")))

    assert exam.procedures == (procedure,) and patient.procedures == (procedure,)
    assert first.pathology == second.pathology == (pathology,)
    assert patient.pathology == (pathology,)
    assert set(procedure.findings) == {first, second}


def test_entities_without_a_graph_have_no_relationships():
    exam = Exam("A")

    assert exam.findings == () and exam.images == () and exam.linked_exams == ()
    assert exam.breast_sides == {}


def test_to_dict_is_flat_and_json_serializable():
    graph = DatasetGraph()
    exam = graph.register(Exam("A", patient_id="P", linked_accessions=["B"]))
    exam.add_finding(Finding("A", Laterality.LEFT, "1"))

    exported = graph.to_dict()

    assert exported["exam"][0]["linked_accessions"] == ["B"]
    assert exported["finding"][0]["accession_number"] == "A"
    json.dumps(exported)
