"""Registering, moving and removing entities."""

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


def procedure(day="2020-01-01"):
    return Procedure(ProcedureIdentity("P", day, "B", Laterality.LEFT))


def test_registering_twice_returns_the_same_object():
    graph = DatasetGraph()
    patient = graph.register(Patient("P"))

    assert graph.register(patient) is patient
    assert graph.patients == (patient,)


@pytest.mark.parametrize("order", [("finding", "exam", "patient"), ("patient", "exam", "finding")])
def test_relationships_form_in_any_registration_order(order):
    graph = DatasetGraph()
    made = {
        "patient": lambda: graph.register(Patient("P")),
        "exam": lambda: graph.register(Exam("A", patient_id="P")),
        "finding": lambda: graph.register(Finding("A", Laterality.LEFT, "1")),
    }
    for name in order:
        made[name]()

    patient, exam, finding = graph.patient("P"), graph.exam("A"), graph.finding("A", "1")
    assert patient.exams == (exam,)
    assert exam.findings == (finding,)
    assert finding.exam is exam
    assert not graph.unresolved_references


def test_missing_targets_are_reported_until_they_arrive():
    graph = DatasetGraph()
    image = graph.register(MammogramImage("I", accession_number="A"))

    assert [(ref.source_kind, ref.target_kind, ref.target_id) for ref in graph.unresolved_references] == [
        ("image", "exam", "A")
    ]
    exam = graph.register(Exam("A"))
    assert exam.images == (image,)
    assert not graph.unresolved_references


def test_adding_children_without_a_graph_creates_one_that_can_be_moved():
    patient = Patient("P")
    exam = patient.add_exam(Exam("A"))
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))
    assert patient.graph is exam.graph is finding.graph is not None

    target = DatasetGraph()
    target.register(patient)

    assert target.finding("A", "1") is finding
    assert finding.graph is target and patient.exams == (exam,)


def test_distinct_object_at_an_occupied_key_is_rejected_before_anything_moves():
    source, target = DatasetGraph(), DatasetGraph()
    patient = source.register(Patient("P"))
    target.register(Patient("P"))

    with pytest.raises(ValueError):
        target.register(patient)
    assert patient.graph is source and source.patient("P") is patient


def test_adding_a_second_object_with_the_same_key_fails():
    exam = Exam("A")
    exam.add_image(MammogramImage("I", accession_number="A"))

    with pytest.raises(ValueError):
        exam.add_image(MammogramImage("I", accession_number="A"))
    assert len(exam.images) == 1


def test_attach_rejects_a_child_of_another_parent_and_unsupported_pairs():
    exam = Exam("A")

    with pytest.raises(ValueError):
        exam.add_image(MammogramImage("I", accession_number="B"))
    with pytest.raises(TypeError):
        DatasetGraph().attach(Patient("P"), Finding("A", Laterality.LEFT, "1"))


def test_pop_moves_the_subtree_into_a_new_graph_keeping_identity():
    graph = DatasetGraph()
    patient = graph.register(Patient("P"))
    exam = patient.add_exam(Exam("A"))
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))
    image = exam.add_image(MammogramImage("I", accession_number="A"))
    roi = image.add_roi(RegionOfInterest((0, 0, 10, 10), "I", "0"))

    popped = graph.pop(exam)

    assert popped is exam and graph.exam("A") is None and not patient.exams
    assert exam.graph is finding.graph is roi.graph and exam.graph is not graph
    assert exam.graph.roi("I", "0") is roi
    assert [ref.target_kind for ref in exam.graph.unresolved_references] == ["patient"]


def test_pop_copies_a_descendant_that_something_outside_also_contains():
    graph = DatasetGraph()
    first, second = graph.register(Exam("A")), graph.register(Exam("B"))
    shared = first.add_procedure(procedure())
    second.add_procedure(shared)
    shared.metadata["nested"] = {"values": [1]}

    graph.pop(first)

    copy = first.procedures[0]
    assert second.procedures == (shared,) and shared.graph is graph
    assert copy is not shared and copy.identity == shared.identity
    copy.metadata["nested"]["values"].append(2)
    assert shared.metadata["nested"]["values"] == [1]


def test_consumer_subclasses_and_attributes_survive_movement():
    class ResearchExam(Exam):
        pass

    exam = ResearchExam("A")
    exam.label = {"cohort": "x"}
    exam.add_finding(Finding("A", Laterality.LEFT, "1"))
    target = DatasetGraph()
    target.register(exam)

    assert isinstance(target.exam("A"), ResearchExam)
    assert target.exam("A").label == {"cohort": "x"}


def test_detach_removes_optional_and_many_valued_containment_only():
    graph = DatasetGraph()
    exam = graph.register(Exam("A"))
    image = exam.add_image(MammogramImage("I", accession_number="A"))
    entry = exam.add_registry_entry(CancerRegistryEntry("P", "1"))
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))

    graph.detach(exam, image)
    graph.detach(exam, entry)

    assert not exam.images and not exam.registry_entries
    assert image.graph is graph and entry.graph is graph
    with pytest.raises(ValueError):
        graph.detach(exam, finding)


def test_replace_rois_swaps_the_whole_collection():
    graph = DatasetGraph()
    image = graph.register(MammogramImage("I"))
    old = image.add_roi(RegionOfInterest((0, 0, 1, 1), "I", "manual"))
    new = RegionOfInterest((0, 0, 2, 2), "I", "0")

    graph.replace_rois(image, [new])

    assert image.rois == (new,) and old.graph is None
    with pytest.raises(ValueError):
        graph.replace_rois(image, [RegionOfInterest((0, 0, 1, 1), "J", "0")])


def test_a_popped_and_rekeyed_subtree_registers_back_coherently():
    graph = DatasetGraph()
    patient = graph.register(Patient("P"))
    exam = patient.add_exam(Exam("A"))
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))

    graph.pop(exam)
    exam.rekey(accession_number="B")
    graph.register(exam)

    assert graph.finding("B", "1") is finding and patient.exams == (exam,)
    assert not graph.unresolved_references


def test_an_unhashable_key_is_rejected():
    graph = DatasetGraph()
    exam = graph.register(Exam("A"))
    procedure = exam.add_procedure(Procedure(ProcedureIdentity("P", "2020-01-01", "B", "L")))

    with pytest.raises(TypeError):
        procedure.update(identity=["not", "hashable"])
