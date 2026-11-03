"""Which breasts an exam imaged: derived from description and images, never findings."""

import pytest

from embed_data_graph import DatasetGraph, Exam, Finding, ImagedLateralityBasis, Laterality, MammogramImage, load_embed


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("MG Screening Bilateral w/ Tomo", Laterality.BILATERAL),
        ("MG Screen Bilat", Laterality.BILATERAL),
        ("MG Diagnostic Left", Laterality.LEFT),
        ("US Breast Rt Limited", Laterality.RIGHT),
        ("MG Diag Left and Right", Laterality.BILATERAL),
    ],
)
def test_description_words_name_the_imaged_breasts(description, expected):
    imaged = Exam("A", description=description).imaged_laterality

    assert (imaged.laterality, imaged.basis) == (expected, ImagedLateralityBasis.EXAM_DESCRIPTION)


@pytest.mark.parametrize("description", [None, "", "MG Screening", "Clinical"])
def test_without_side_words_or_images_the_laterality_is_unknown(description):
    imaged = Exam("A", description=description).imaged_laterality

    assert (imaged.laterality, imaged.basis, imaged.sides) == (Laterality.UNKNOWN, ImagedLateralityBasis.NONE, ())


def test_a_contradictory_description_is_a_conflict_not_a_side():
    imaged = Exam("A", description="Bilat Screen Left").imaged_laterality

    assert (imaged.laterality, imaged.basis) == (Laterality.UNKNOWN, ImagedLateralityBasis.CONFLICT)


def exam_with(description, *sides):
    graph = DatasetGraph()
    exam = graph.register(Exam("A", description=description))
    for index, side in enumerate(sides):
        exam.add_image(MammogramImage(f"I{index}", laterality=side, accession_number="A"))
    return exam


def test_images_supply_the_laterality_when_the_description_does_not():
    assert exam_with("MG Screening", "L", "R").imaged_laterality.laterality is Laterality.BILATERAL
    imaged = exam_with(None, "R", "UNKNOWN").imaged_laterality
    assert (imaged.laterality, imaged.basis) == (Laterality.RIGHT, ImagedLateralityBasis.IMAGE_LATERALITY)


def test_agreeing_sources_are_reported_together():
    imaged = exam_with("MG Diagnostic Left", "L").imaged_laterality

    assert (imaged.laterality, imaged.basis) == (Laterality.LEFT, ImagedLateralityBasis.DESCRIPTION_AND_IMAGES)


def test_partial_images_of_a_bilateral_exam_do_not_narrow_it():
    imaged = exam_with("MG Screening Bilateral", "L").imaged_laterality

    assert (imaged.laterality, imaged.basis) == (Laterality.BILATERAL, ImagedLateralityBasis.EXAM_DESCRIPTION)
    assert (imaged.description_laterality, imaged.image_laterality) == (Laterality.BILATERAL, Laterality.LEFT)


@pytest.mark.parametrize("sides", [("R",), ("L", "R")])
def test_images_of_a_side_the_description_excludes_are_a_conflict(sides):
    imaged = exam_with("MG Diagnostic Left", *sides).imaged_laterality

    assert (imaged.laterality, imaged.basis) == (Laterality.UNKNOWN, ImagedLateralityBasis.CONFLICT)


def test_findings_never_make_a_breast_imaged():
    graph = DatasetGraph()
    exam = graph.register(Exam("A", description="MG Diagnostic Left"))
    exam.add_finding(Finding("A", "R", "1"))

    assert exam.imaged_laterality.sides == (Laterality.LEFT,)
    assert set(exam.breast_sides) == {Laterality.RIGHT}


def test_loaded_exams_derive_it_from_the_description_column():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "MG Diagnostic Right w/ Tomo"}]).graph

    assert graph.exam("A1").imaged_laterality.sides == (Laterality.RIGHT,)
