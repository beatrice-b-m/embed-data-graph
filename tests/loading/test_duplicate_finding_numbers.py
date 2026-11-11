"""Repeated source numbers must not pool facts across populated finding sides."""

from itertools import permutations

import pytest

from embed_data_graph import DatasetGraph, Finding, Laterality, load_embed
from embed_data_graph.clinical.findings import FindingRecordType


def row(side="L", **fields):
    return {"empi_anon": "P", "acc_anon": "A", "numfind": 1, "side": side, **fields}


def by_side(graph):
    return {finding.laterality: finding for finding in graph.exam("A").findings}


def test_duplicate_number_separates_assessment_descriptors_recommendation_and_anatomy():
    rows = [row("L", asses="B", recc="F", massshape="O", location="UOQ"),
            row("R", asses="S", recc="B", calcfind="A", location="LIQ")]
    keys = []
    for ordered in permutations(rows):
        report = load_embed(magview=ordered)
        graph = report.graph
        left, right = (by_side(graph)[side] for side in (Laterality.LEFT, Laterality.RIGHT))
        assert graph.finding("A", "1") is None
        assert left.key != right.key
        assert left.source_finding_number == right.source_finding_number == "1"
        assert left.interpretation.assessment.code == "B"
        assert right.interpretation.assessment.code == "S"
        assert left.interpretation.recommendation.code == "F"
        assert right.interpretation.recommendation.code == "B"
        assert set(left.descriptors) == {"mass_shape"}
        assert set(right.descriptors) == {"calcification_morphology"}
        assert left.source_location_codes != right.source_location_codes
        assert graph.exam("A").breast_sides[Laterality.LEFT].findings == (left,)
        assert graph.exam("A").breast_sides[Laterality.RIGHT].findings == (right,)
        duplicate = next(issue for issue in report.issues if issue.code == "duplicate_finding_number")
        assert duplicate.context["finding_number"] == "1"
        assert duplicate.context["accession"] == "A"
        assert duplicate.context["sides"] == ["L", "R"]
        assert "conflicting_finding_laterality" not in {issue.code for issue in report.issues}
        keys.append((left.key, right.key))
    assert keys[0] == keys[1]


@pytest.mark.parametrize("second", [{"side": "L"}, {}, {"side": None}])
def test_one_populated_side_keeps_ordinary_grouping_and_conflicts(second):
    report = load_embed(findings=[row(asses="B"), {"acc_anon": "A", "numfind": 1, "asses": "S", **second}])
    (finding,) = report.graph.findings
    assert finding.key == ("A", "1")
    assert finding.source_finding_number is None
    assert finding.laterality is Laterality.LEFT
    assert finding.interpretation is None
    assert "conflicting_finding_assessment" in {issue.code for issue in report.issues}
    assert "duplicate_finding_number" not in {issue.code for issue in report.issues}


@pytest.mark.parametrize("mode", ["refresh", "merge"])
def test_split_refresh_and_partial_load_preserve_objects_and_side_local_conflicts(mode):
    graph = load_embed(findings=[row("L", asses="B"), row("R", asses="S")]).graph
    before = by_side(graph)
    left = before[Laterality.LEFT]
    left.metadata["reviewed"] = True
    interpretation = left.interpretation
    report = load_embed(findings=[row("L", asses="S"), row("L", asses="B")], into=graph, mode=mode)
    assert by_side(graph) == before
    assert left.interpretation is interpretation
    assert left.metadata == {"reviewed": True}
    assert left.interpretation.assessment is None
    assert before[Laterality.RIGHT].interpretation.assessment.code == "S"
    assert "conflicting_finding_assessment" in {issue.code for issue in report.issues}
    assert len(graph.findings) == 2


def test_missing_or_invalid_sides_are_not_pooled_into_either_populated_side():
    rows = [row("L", massshape="O"), row("R", calcfind="A"), row(None, asses="B"),
            {"acc_anon": "A", "numfind": 1, "recc": "F"}, row("bad", recc="F")]
    graph = load_embed(findings=rows).graph
    findings = by_side(graph)
    assert set(findings) == set(Laterality)
    assert findings[Laterality.UNKNOWN].interpretation.recommendation.code == "F"
    assert findings[Laterality.BILATERAL].interpretation.assessment.code == "B"
    assert findings[Laterality.LEFT].interpretation is None
    assert findings[Laterality.RIGHT].interpretation is None


def test_explicit_bilateral_side_participates_in_split():
    graph = load_embed(findings=[row("L", asses="B"), row("B", asses="S")]).graph
    assert set(by_side(graph)) == {Laterality.LEFT, Laterality.BILATERAL}


def test_existing_finding_is_reused_without_retargeting_number_only_links():
    graph = load_embed(magview=[row("L", bside="L", type="B", procdate_anon="2020-01-01")]).graph
    original = graph.finding("A", "1")
    original.metadata["reviewed"] = True
    (procedure,) = graph.procedures
    report = load_embed(findings=[row("L"), row("R")], into=graph)
    assert by_side(graph)[Laterality.LEFT] is original
    assert original.metadata == {"reviewed": True}
    assert procedure.finding_references == {("A", "1")}
    assert procedure.findings == ()
    assert original.procedures == ()
    assert "ambiguous_finding_reference" in {issue.code for issue in report.issues}


def test_unknown_aggregate_is_replaced_without_contaminating_new_sides():
    graph = DatasetGraph()
    original = graph.register(Finding("A", Laterality.UNKNOWN, "1", descriptors={"mass_shape": "old"}))
    load_embed(findings=[row("L", asses="B"), row("R", calcfind="A")], into=graph)
    assert original.graph is None
    assert all("mass_shape" not in finding.descriptors for finding in graph.findings)
    assert len(graph.findings) == 2


def test_number_only_clinical_links_remain_unresolved_for_wide_and_narrow_rows():
    report = load_embed(
        magview=[row("L", bside="L", type="B", procdate_anon="2020-01-01", path1="IDC"), row("R")],
        pathology=[{"empi_anon": "P", "acc_anon": "A", "numfind": 1, "report": "REPORT", "path1": "IDC"}],
        columns={"pathology": {"record_id": "report"}},
    )
    graph = report.graph
    assert len(graph.procedures) == 1 and len(graph.pathology) == 2
    assert all(not finding.procedures and not finding.pathology for finding in graph.findings)
    assert graph.procedures[0].finding_references == {("A", "1")}
    direct = next(item for item in graph.pathology if item.identity == ("P", "REPORT"))
    assert direct.finding_references == {("A", "1")}
    assert "ambiguous_finding_reference" in {issue.code for issue in report.issues}


def test_generated_numbers_do_not_collide_with_source_numbers_now_or_on_later_loads():
    first = load_embed(findings=[row("L"), row("R")]).graph
    generated = by_side(first)[Laterality.LEFT].finding_number
    graph = load_embed(findings=[row("L"), row("R"), row("L", numfind=generated)]).graph
    assert len(graph.findings) == 3
    assert graph.finding("A", generated).source_finding_number is None
    old_left = by_side(first)[Laterality.LEFT]
    load_embed(findings=[row("L", numfind=generated, asses="B")], into=first)
    assert len(first.findings) == 3
    assert old_left.finding_number != generated
    assert first.finding("A", generated).source_finding_number is None
    load_embed(findings=[row("L", asses="S")], into=first)
    assert old_left.interpretation.assessment.code == "S"
    assert first.finding("A", generated).interpretation.assessment.code == "B"


def test_mapped_columns_wide_narrow_and_synthetic_findings():
    report = load_embed(
        magview=[{"accession": "A", "number": -9, "breast": "L", "asses": "B"}],
        findings=[{"accession": "A", "number": -9, "breast": "R", "asses": "S"}],
        columns={"findings": {"accession": "accession", "finding_number": "number", "laterality": "breast"}},
    )
    assert len(report.graph.findings) == 2
    assert all(finding.record_type is FindingRecordType.SYNTHETIC_CONTRALATERAL_NEGATIVE
               for finding in report.graph.findings)


def test_source_numbers_survive_serialization_projection_and_partition_copy():
    graph = load_embed(findings=[row("L"), row("R")]).graph
    assert all(finding.to_dict()["source_finding_number"] == "1" for finding in graph.findings)
    assert all(record["source_finding_number"] == "1" for record in graph.records("findings"))
    for part in graph.partition(level="finding", key=lambda finding: finding.laterality).values():
        (finding,) = part.findings
        assert finding.source_finding_number == "1"
        load_embed(findings=[row(finding.laterality.value, asses="B")], into=part)
        assert part.findings == (finding,)
        assert finding.interpretation.assessment.code == "B"


@pytest.mark.parametrize("timing", ["before", "together", "after"])
def test_generated_numbers_never_resolve_unrelated_source_clinical_references(timing):
    rows = [row("L"), row("R")]
    probe = load_embed(findings=rows).graph
    generated = by_side(probe)[Laterality.LEFT].finding_number
    clinical = [row("L", numfind=generated, bside="L", type="B", procdate_anon="2020-01-01")]
    graph = DatasetGraph()
    if timing == "before":
        load_embed(procedures=clinical, into=graph)
    load_embed(findings=rows, procedures=clinical if timing == "together" else None, into=graph)
    if timing == "after":
        load_embed(procedures=clinical, into=graph)
    assert len(graph.findings) == 2
    assert graph.procedures[0].finding_references == {("A", generated)}
    assert graph.procedures[0].findings == ()


@pytest.mark.parametrize("mode", ["refresh", "merge"])
def test_first_split_retains_an_existing_known_side_not_addressed_by_new_rows(mode):
    graph = load_embed(findings=[row("B", asses="B")]).graph
    original = graph.finding("A", "1")
    load_embed(findings=[row("L"), row("R")], into=graph, mode=mode)
    assert len(graph.findings) == 3
    assert by_side(graph)[Laterality.BILATERAL] is original
    assert original.source_finding_number == "1"
    assert original.interpretation.assessment.code == "B"
