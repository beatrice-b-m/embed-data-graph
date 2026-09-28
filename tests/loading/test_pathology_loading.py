"""Pathology from MagView rows attaches to its procedure."""

from embed_data_graph import load_embed


def procedure_row(**fields):
    row = {
        "empi_anon": "P1",
        "acc_anon": "A1",
        "numfind": 1,
        "side": "L",
        "bside": "L",
        "type": "B",
        "procdate_anon": "2020-01-02",
        "path1": "IDC",
        "path_severity": 0,
    }
    row.update(fields)
    return row


def test_pathology_without_a_report_date_attaches_to_its_procedure():
    report = load_embed(magview=[procedure_row()])
    graph = report.graph

    (procedure,) = graph.procedures
    (pathology,) = graph.pathology
    assert procedure.pathology == (pathology,)
    assert [d.descriptor.code for d in pathology.descriptors] == ["IDC"]
    assert pathology.report_documented_date is None
    assert not graph.unresolved_records
    assert graph.finding("A1", "1").pathology == (pathology,)


def test_report_date_is_an_attribute_not_part_of_pathology_identity():
    graph = load_embed(magview=[procedure_row(pdate_anon="2020-01-05")]).graph
    (pathology,) = graph.pathology

    load_embed(magview=[procedure_row(pdate_anon="2020-01-06")], into=graph)

    assert graph.pathology == (pathology,)
    assert pathology.report_documented_date == "2020-01-06"


def test_one_procedure_on_several_findings_has_one_pathology_bundle():
    graph = load_embed(magview=[procedure_row(), procedure_row(numfind=2)]).graph

    (procedure,) = graph.procedures
    (pathology,) = graph.pathology
    assert {f.finding_number for f in graph.findings if pathology in f.pathology} == {"1", "2"}


def test_pathology_without_a_complete_procedure_stays_unresolved():
    report = load_embed(magview=[procedure_row(bside=None, pdate_anon="2020-01-05")])

    assert not report.graph.pathology
    assert report.graph.unresolved_records
    assert "incomplete_pathology_identity" in {issue.code for issue in report.issues}
