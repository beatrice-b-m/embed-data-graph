from itertools import permutations

import pandas as pd
import pytest

from embed_data_graph import DatasetGraph, Exam, Finding, Laterality, load_embed


@pytest.mark.parametrize("index", [None, [0,0], ["x","x"], pd.MultiIndex.from_tuples([("a",1),("a",1)])])
def test_dataframe_indexes_and_bad_diagnostic_keys_do_not_gate_identity(index):
    frame = pd.DataFrame([{"empi_anon":1.0}, {"empi_anon":2.0}], index=index)
    report = load_embed(patients=frame, source_keys={"patients":"missing"})
    assert {p.patient_id for p in report.graph.patients} == {"1","2"}
    load_embed(patients=pd.DataFrame([{"empi_anon":3}]), into=report.graph)
    assert len(report.graph.patients) == 3


def test_refresh_preserves_subclass_reference_extensions_and_children():
    class ResearchExam(Exam):
        pass
    graph = DatasetGraph()
    exam = graph.register(ResearchExam("A", description="old", exam_date="2020-01-01"))
    exam.project = {"values":[1]}
    exam.metadata["consumer"] = "keep"
    finding = exam.add_finding(Finding("A", Laterality.LEFT, "1"))
    load_embed(exams=[{"acc_anon":"A", "desc":"new"}], into=graph)
    assert graph.exam("A") is exam and isinstance(exam, ResearchExam)
    assert exam.description == "new" and exam.exam_date == "2020-01-01"
    assert exam.findings == (finding,) and exam.project == {"values":[1]}
    assert exam.metadata["consumer"] == "keep"


def test_unbound_scalar_is_outside_refresh_and_merge_ignores_null():
    graph = load_embed(exams=[{"acc_anon":"A", "desc":"old"}]).graph
    load_embed(exams=[{"acc_anon":"A"}], into=graph, columns={"exams":{"exam_description":None}})
    assert graph.exam("A").description == "old"
    load_embed(exams=[{"acc_anon":"A", "desc":None}], into=graph, mode="merge")
    assert graph.exam("A").description == "old"
    load_embed(exams=[{"acc_anon":"A", "desc":None}], into=graph)
    assert graph.exam("A").description is None


def test_wide_and_narrow_complementary_rows_group_without_precedence():
    for rows in permutations([{"acc_anon":"A", "desc":"one"}, {"acc_anon":"A", "studydate_anon":"2020-01-01"}]):
        graph = load_embed(magview=[rows[0]], exams=[rows[1]]).graph
        assert graph.exam("A").description == "one"
        assert graph.exam("A").exam_date == "2020-01-01"
    graph = load_embed(exams=[{"acc_anon":"A", "desc":"old"}]).graph
    report = load_embed(exams=[{"acc_anon":"A", "desc":"x"},{"acc_anon":"A", "desc":"y"}], into=graph, mode="merge")
    assert graph.exam("A").description is None
    assert any("conflicting_exam" in issue.code for issue in report.issues)


def test_child_only_rows_preserve_parent_fields_and_establish_ownership():
    graph = load_embed(patients=[{"empi_anon":"P", "GENDER_DESC":"F"}], exams=[{"acc_anon":"A", "desc":"keep"}]).graph
    load_embed(findings=[{"acc_anon":"A", "numfind":1, "empi_anon":"P", "side":"L"}], into=graph)
    assert graph.exam("A").description == "keep"
    assert graph.patient("P").sex == "F"
    assert graph.patient("P").exams == (graph.exam("A"),)


def test_grouped_repeated_findings_keep_all_procedure_and_pathology_children():
    rows = [{"empi_anon":"P", "acc_anon":"A", "numfind":1, "side":"L", "bside":"L", "type":"biopsy", "procdate_anon":f"2020-01-0{i}", "pdate_anon":f"2020-02-0{i}", "path1":"descriptor"} for i in (1,2)]
    graph = load_embed(magview=rows).graph
    finding = graph.finding("A","1")
    assert len(finding.procedures) == 2 and len(finding.pathology) == 2
    load_embed(magview=list(reversed(rows)), into=graph)
    assert graph.finding("A","1") is finding
    assert len(finding.procedures) == 2


def test_finding_refresh_respects_unbound_fields_and_conflicting_merge_values():
    graph = load_embed(findings=[{"acc_anon":"A", "numfind":1, "side":"L", "location":"UOQ"}]).graph
    finding = graph.finding("A","1")
    finding.finding_type = "consumer"
    load_embed(findings=[{"acc_anon":"A", "numfind":1}], into=graph)
    assert finding.finding_type == "consumer"  # default finding_type is unbound
    assert finding.laterality is Laterality.LEFT  # an absent side column is not supplied
    load_embed(findings=[{"acc_anon":"A", "numfind":1,"side":"L"},{"acc_anon":"A", "numfind":1,"side":"R"}], mode="merge", into=graph)
    assert finding.laterality is Laterality.UNKNOWN
    assert Laterality.LEFT not in graph.exam("A").breast_sides


def test_supplied_generators_are_consumed_once():
    class Once:
        def __init__(self):
            self.used = False
        def __iter__(self):
            assert not self.used
            self.used = True
            yield {"empi_anon":"P"}
    assert load_embed(patients=Once()).graph.patient("P") is not None
def test_interpretation_without_diagnostics_refreshes_in_place_and_respects_unbinding():
    from embed_data_graph import load_embed
    graph = load_embed(findings=[{"acc_anon": "A", "numfind": 1, "asses": "S", "recc": "B"}]).graph
    interpretation = graph.findings[0].interpretation
    assert interpretation.assessment.code == "S" and interpretation.sources == ()
    interpretation.consumer_note = {"reviewed": True}
    load_embed(findings=[{"acc_anon": "A", "numfind": 1, "asses": "B"}],
               columns={"findings": {"recommendation": None}}, into=graph)
    assert graph.findings[0].interpretation is interpretation
    assert interpretation.assessment.code == "B" and interpretation.recommendation.code == "B"
    assert interpretation.consumer_note == {"reviewed": True}
    load_embed(findings=[{"acc_anon": "A", "numfind": 1, "recc": "F"}], into=graph)
    assert interpretation.assessment.code == "B" and interpretation.recommendation.code == "F"
    load_embed(findings=[{"acc_anon": "A", "numfind": 1}], into=graph)
    assert interpretation.assessment.code == "B" and interpretation.recommendation.code == "F"
    load_embed(findings=[{"acc_anon": "A", "numfind": 1, "asses": None, "recc": None}], into=graph)
    assert graph.findings[0].interpretation is interpretation
    assert interpretation.assessment is None and interpretation.recommendation is None
