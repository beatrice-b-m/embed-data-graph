"""Which breasts an exam imaged: derived from the description, never findings or images."""

import pytest

from embed_data_graph import DatasetGraph, Exam, Finding, Laterality, MammogramImage, load_embed


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("MG Screening Bilateral w/ Tomo", Laterality.BILATERAL),
        ("mg screen bilat", Laterality.BILATERAL),
        ("MG Diagnostic Left", Laterality.LEFT),
        ("US BREAST RIGHT LIMITED", Laterality.RIGHT),
    ],
)
def test_description_substrings_name_the_imaged_breasts(description, expected):
    assert Exam("A", description=description).imaged_laterality is expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("MG Diag Bilat, Left Focused", Laterality.BILATERAL),
        ("MG Diag Left and Right", Laterality.LEFT),
    ],
)
def test_several_sides_resolve_in_fixed_order_bilateral_left_right(description, expected):
    assert Exam("A", description=description).imaged_laterality is expected


@pytest.mark.parametrize("description", [None, "", "MG Screening", "US Breast Rt Limited"])
def test_a_description_naming_no_side_is_unknown_with_no_sides(description):
    imaged = Exam("A", description=description).imaged_laterality

    assert (imaged, imaged.expand()) == (Laterality.UNKNOWN, ())


def test_images_and_findings_never_set_the_imaged_breasts():
    graph = DatasetGraph()
    exam = graph.register(Exam("A", description="MG Diagnostic Left"))
    exam.add_finding(Finding("A", "R", "1"))
    exam.add_image(MammogramImage("I1", laterality="R", accession_number="A"))
    unnamed = graph.register(Exam("B", description="MG Screening"))
    unnamed.add_image(MammogramImage("I2", laterality="L", accession_number="B"))

    assert exam.imaged_laterality.expand() == (Laterality.LEFT,)
    assert set(exam.breast_sides) == {Laterality.RIGHT}
    assert unnamed.imaged_laterality is Laterality.UNKNOWN


def test_loaded_exams_derive_it_from_the_description_column():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "MG Diagnostic Right w/ Tomo"}]).graph

    assert graph.exam("A1").imaged_laterality is Laterality.RIGHT
