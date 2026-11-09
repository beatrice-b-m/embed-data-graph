"""Image view modification, DBT form and recovered side and view rules."""

import pytest

from embed_data_graph import DbtForm, Laterality, MammogramImage, ViewModification, ViewPosition


def dbt(**fields):
    return MammogramImage("I", modality="3D", **fields)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"series_description": "L CC Tomosynthesis Projection"}, DbtForm.PROJECTION),
        ({"dicom_image_type": "ORIGINAL\\PRIMARY\\TOMO_PROJ"}, DbtForm.PROJECTION),
        ({"series_description": "R MLO Tomosynthesis Reconstruction"}, DbtForm.RECONSTRUCTION),
        ({"series_description": "Breast Tomo Slices"}, DbtForm.RECONSTRUCTION),
        ({"series_description": "LCC"}, DbtForm.UNKNOWN),
        ({"series_description": "Projection and Reconstruction"}, DbtForm.UNKNOWN),
        ({"series_description": "Projection", "dicom_image_type": "DERIVED\\PRIMARY\\RECON"}, DbtForm.UNKNOWN),
    ],
)
def test_dbt_form_comes_only_from_explicit_wording(fields, expected):
    assert dbt(**fields).dbt_form is expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"manufacturer": "HOLOGIC, Inc.", "series_description": "L MLO Breast Tomosynthesis Image"}, DbtForm.RECONSTRUCTION),
        ({"manufacturer": "hologic", "series_description": "R CC Tomo"}, DbtForm.RECONSTRUCTION),
        ({"manufacturer": "HOLOGIC, Inc.", "series_description": "L CC Tomosynthesis Projection"}, DbtForm.PROJECTION),
        ({"manufacturer": "HOLOGIC, Inc.", "series_description": "Projection and Reconstruction"}, DbtForm.UNKNOWN),
        ({"manufacturer": "HOLOGIC, Inc.", "dicom_image_type": "ORIGINAL\\PRIMARY"}, DbtForm.UNKNOWN),
        ({"manufacturer": "GE MEDICAL SYSTEMS", "series_description": "L MLO Breast Tomosynthesis Image"}, DbtForm.UNKNOWN),
        ({"series_description": "L MLO Breast Tomosynthesis Image"}, DbtForm.UNKNOWN),
    ],
)
def test_hologic_series_naming_no_form_are_reconstructions(fields, expected):
    assert dbt(**fields).dbt_form is expected


def test_dbt_form_is_none_for_images_that_are_not_dbt():
    assert MammogramImage("I", modality="2D", series_description="Projection").dbt_form is None


@pytest.mark.parametrize("text", ["XCCL", "L CC", "R MLO"])
def test_side_words_do_not_make_a_view_modified(text):
    image = MammogramImage("I", view_position=text, source_view_position=text)

    assert image.view_modification is ViewModification.STANDARD


def test_a_joined_side_and_view_is_not_a_modifier():
    image = MammogramImage("I", view_position="RMLO", source_view_position="RMLO")

    assert image.view_position is ViewPosition.UNKNOWN
    assert image.view_modification is ViewModification.UNKNOWN


@pytest.mark.parametrize("text", ["SPOT CC", "CC MAG", "MCC", "CC ROLLED"])
def test_extra_words_in_the_view_text_mark_a_modified_view(text):
    assert MammogramImage("I", view_position=text, source_view_position=text).view_modification is ViewModification.MODIFIED


def test_an_unknown_view_without_modification_is_unknown():
    assert MammogramImage("I").view_modification is ViewModification.UNKNOWN


def test_spot_flag_must_be_a_bool():
    with pytest.raises(TypeError):
        MammogramImage("I", spot_magnification=1)


def test_recovered_side_and_view_need_exactly_one_named_value():
    both_sides = MammogramImage("I", series_description="L CC R CC")

    assert both_sides.recovered_laterality is Laterality.UNKNOWN
    assert both_sides.recovered_view_position is ViewPosition.CC


def test_a_populated_but_unrecognized_view_tag_is_not_overridden():
    image = MammogramImage("I", source_view_position="FB", series_description="L CC")

    assert image.recovered_view_position is ViewPosition.UNKNOWN
    assert image.recovered_laterality is Laterality.LEFT
