"""EMBED source semantics that the loader must honour.

Each test encodes one reviewed meaning of an EMBED column or code, using
synthetic rows only.
"""

import pytest

from embed_data_graph import Laterality, load_embed


def magview_row(**fields):
    row = {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1}
    row.update(fields)
    return row


@pytest.mark.parametrize("side", [None, "B"])
def test_null_or_b_finding_side_is_bilateral_and_projects_to_both_sides(side):
    graph = load_embed(magview=[magview_row(side=side)]).graph

    finding = graph.finding("A1", "1")
    exam = graph.exam("A1")
    assert finding.laterality is Laterality.BILATERAL
    assert exam.breast_sides[Laterality.LEFT].findings == (finding,)
    assert exam.breast_sides[Laterality.RIGHT].findings == (finding,)


def test_finding_side_absent_from_every_row_stays_unknown():
    graph = load_embed(magview=[magview_row()]).graph

    finding = graph.finding("A1", "1")
    assert finding.laterality is Laterality.UNKNOWN
    assert not graph.exam("A1").breast_sides


def test_merge_applies_a_null_finding_side_as_bilateral():
    graph = load_embed(magview=[magview_row()]).graph
    load_embed(magview=[magview_row(side=None)], into=graph, mode="merge")

    assert graph.finding("A1", "1").laterality is Laterality.BILATERAL


def test_codes_compare_after_trimming_and_uppercasing():
    report = load_embed(
        magview=[
            magview_row(side="L", asses="b", recc="ra"),
            magview_row(side="L", asses="B ", recc=" RA"),
        ]
    )

    interpretation = report.graph.finding("A1", "1").interpretation
    assert (interpretation.assessment.code, interpretation.recommendation.code) == ("B", "RA")
    assert not report.issues


def test_procedure_type_and_pathology_codes_are_normalized():
    procedure_row = magview_row(
        side="L", bside="L", procdate_anon="2020-01-02", type="b", path1=" idc"
    )
    graph = load_embed(
        magview=[procedure_row, dict(procedure_row, numfind=2, type="B ")]
    ).graph

    (procedure,) = graph.procedures
    assert procedure.identity.procedure_type.code == "B"
    assert {finding.finding_number for finding in graph.findings if procedure in finding.procedures} == {"1", "2"}


@pytest.mark.parametrize("sentinel", [-2, -99, "-2"])
def test_negative_distance_is_an_exceptional_code_not_a_measurement(sentinel):
    report = load_embed(magview=[magview_row(side="L", location="UO", distance=sentinel)])

    finding = report.graph.finding("A1", "1")
    assert finding.anatomical_position.distance_from_nipple_cm is None
    assert finding.source_distance_codes == {"distance": sentinel}
    assert "exceptional_finding_distance" in {issue.code for issue in report.issues}


def test_validation_rejects_a_negative_distance_supplied_directly():
    from embed_data_graph import Finding, validate
    from embed_data_graph.core.anatomy import AnatomicalPosition, Quadrant

    position = AnatomicalPosition(
        laterality=Laterality.LEFT,
        quadrant=Quadrant(laterality=Laterality.LEFT),
        distance_from_nipple_cm=-2.0,
    )
    finding = Finding("A1", Laterality.LEFT, "1", anatomical_position=position)

    assert "distance_range" in {issue.code for issue in validate(finding).issues}


@pytest.mark.parametrize("source_keys", [None, {"magview": "row_id"}])
def test_unknown_location_codes_are_reported_with_or_without_source_keys(source_keys):
    report = load_embed(
        magview=[magview_row(side="L", location="ZZZ", depth="Q", row_id="r1")],
        source_keys=source_keys,
    )

    finding = report.graph.finding("A1", "1")
    warning_codes = {warning.code for warning in finding.normalization_warnings}
    assert {"unknown_location_code", "unknown_depth_code"} <= warning_codes
    assert warning_codes <= {issue.code for issue in report.issues}
