"""Independent copies of graph subsets."""

import pytest

from embed_data_graph import DatasetGraph, Exam, Finding, Laterality, Patient, Pathology, Procedure, ProcedureIdentity


def populated():
    graph = DatasetGraph()
    patient = graph.register(Patient("P"))
    a = patient.add_exam(Exam("A"))
    patient.add_exam(Exam("B"))
    finding = a.add_finding(Finding("A", Laterality.LEFT, "1"))
    a.add_finding(Finding("A", Laterality.RIGHT, "2"))
    proc = finding.add_procedure(Procedure(ProcedureIdentity("P", "2020-01-01", "biopsy", Laterality.LEFT)))
    path = proc.add_pathology(Pathology(("P", "report"), diagnosis="reported"))
    patient.metadata["nested"] = {"list": [1]}
    return graph, patient, a, finding, proc, path


@pytest.mark.parametrize("level,expected", [("patient", 2), ("exam", 2), ("finding", 1), ("procedure", 1), ("pathology", 1)])
def test_partition_levels_copy_descendants_with_minimal_context(level, expected):
    graph, patient, exam, finding, proc, path = populated()
    target = {"patient": patient, "exam": exam, "finding": finding, "procedure": proc, "pathology": path}[level]
    parts = graph.partition(level=level, key=lambda obj: ["one", "two"] if obj is target else [])
    first, second = parts["one"], parts["two"]
    assert first.patient("P") is not patient
    assert first.patient("P") is not second.patient("P")
    assert len(first.exam("A").findings) == expected
    assert first.is_context(first.patient("P")) is (level != "patient")
    first.patient("P").metadata["nested"]["list"].append(2)
    assert patient.metadata["nested"]["list"] == [1]
    assert second.patient("P").metadata["nested"]["list"] == [1]
    if level != "patient":
        assert first.exam("B") is None
    assert len(graph.exams) == 2


def test_selection_is_nonowning_and_empty_partition_has_no_outputs():
    graph, _, exam, *_ = populated()
    view = graph.select(level="exam", predicate=lambda obj: obj is exam)
    assert tuple(view) == (exam,)
    next(iter(view)).update(description="live")
    assert graph.exam("A").description == "live"
    assert graph.partition(level="exam", key=lambda obj: []) == {}


def test_shared_descendant_copy_once_and_links_do_not_expand_output():
    graph, _, exam, _, proc, path = populated()
    exam.findings[1].add_procedure(proc)
    graph.set_linked_accessions(exam, ["B"])
    output = graph.partition(level="exam", key=lambda obj: "A" if obj is exam else "B")["A"]
    first, second = output.exam("A").findings
    assert first.procedures[0] is second.procedures[0]
    assert first.pathology[0] is not path
    assert output.exam("B") is None
    assert not output.exam("A").linked_exams
    assert output.exam("A").linked_accessions == {"B"}


def test_consumer_copy_hook_and_uncopyable_state():
    graph, patient, *_ = populated()

    class Uncopyable:
        def __deepcopy__(self, memo):
            raise TypeError("not copyable")

    patient.extension = Uncopyable()
    with pytest.raises(ValueError, match="__deepcopy__"):
        graph.partition(level="patient", key=lambda obj: "all")

    class Copyable:
        def __deepcopy__(self, memo):
            return {"copied": True}

    patient.extension = Copyable()
    output = graph.partition(level="patient", key=lambda obj: "all")["all"]
    assert output.patient("P").extension == {"copied": True}


def test_partition_keeps_references_its_selected_entities_state():
    graph = DatasetGraph()
    a = graph.register(Exam("A"))
    graph.register(Exam("B"))
    graph.set_linked_accessions(a, ["B"])
    output = graph.partition(level="exam", key=lambda obj: ["target"] if obj is a else [])["target"]
    assert output.exam("B") is None
    assert output.unresolved_references
    output.register(Exam("B"))
    assert output.exam("B") in output.exam("A").linked_exams


def test_registry_shared_across_exams_copies_with_selected_exam():
    from embed_data_graph import CancerRegistryEntry
    graph = DatasetGraph()
    a, b = graph.register(Exam("A")), graph.register(Exam("B"))
    entry = graph.register(CancerRegistryEntry("P", "1"))
    graph.set_registry_assignments(a, [("P", "1")])
    graph.set_registry_assignments(b, [("P", "1")])
    output = graph.partition(level="exam", key=lambda obj: obj.accession_number)["A"]
    assert output.exam("B") is None
    assert output.exam("A").registry_entries[0] is not entry
