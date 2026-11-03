"""EMBED image-metadata semantics honoured by the loader."""

from embed_data_graph import ImageModality, load_embed


def image_row(**fields):
    row = {
        "anon_dicom_path": "cohort1/P1/S1/SE1/U1.dcm",
        "acc_anon": "A1",
        "empi_anon": "P1",
        "ImageLateralityFinal": "L",
        "ImagesInAcquisition": 60,
    }
    row.update(fields)
    return row


def test_images_in_acquisition_is_the_frame_count_of_a_dbt_image():
    graph = load_embed(images=[image_row(FinalImageType="3D")]).graph

    (image,) = graph.images
    assert image.modality is ImageModality.DBT
    assert image.frame_count == 60


def test_images_in_acquisition_is_not_a_frame_count_for_2d_images():
    graph = load_embed(images=[image_row(FinalImageType="2D")]).graph

    (image,) = graph.images
    assert image.modality is ImageModality.FFDM
    assert image.frame_count is None


def test_pixel_dimensions_and_frames_load_as_integers():
    graph = load_embed(
        images=[image_row(FinalImageType="3D", Rows="3328", Columns=2560.0, ImagesInAcquisition="60")]
    ).graph

    (image,) = graph.images
    assert (image.height, image.width, image.frame_count) == (3328, 2560, 60)
    assert all(type(value) is int for value in (image.height, image.width, image.frame_count))


def test_fractional_dimension_is_reported_not_truncated():
    report = load_embed(images=[image_row(Rows=10.5)])

    assert report.graph.images[0].height is None
    assert "image_numeric_parse" in {issue.code for issue in report.issues}


def loaded(**fields):
    (image,) = load_embed(images=[image_row(**fields)]).graph.images
    return image


def test_manufacturer_series_description_and_image_type_load_as_recorded():
    image = loaded(Manufacturer=" HOLOGIC, Inc. ", SeriesDescription="L CC Tomosynthesis Projection",
                   ImageType="ORIGINAL\\PRIMARY\\TOMO_PROJ", FinalImageType="3D")

    assert image.manufacturer == "HOLOGIC, Inc."
    assert image.series_description == "L CC Tomosynthesis Projection"
    assert image.dicom_image_type == "ORIGINAL\\PRIMARY\\TOMO_PROJ"


def test_dbt_projections_and_reconstructions_can_be_told_apart():
    projection = loaded(FinalImageType="3D", Manufacturer="HOLOGIC", SeriesDescription="R MLO Tomosynthesis Projection")
    reconstruction = loaded(FinalImageType="3D", Manufacturer="HOLOGIC", SeriesDescription="R MLO Tomosynthesis Reconstruction")
    unknown = loaded(FinalImageType="3D", Manufacturer="GE MEDICAL SYSTEMS", SeriesDescription="RMLO", ImageType="ORIGINAL\\PRIMARY")
    flat = loaded(FinalImageType="2D", SeriesDescription="L CC")

    assert [image.dbt_form.value for image in (projection, reconstruction, unknown)] == ["PROJECTION", "RECONSTRUCTION", "UNKNOWN"]
    assert unknown.manufacturer == "GE MEDICAL SYSTEMS"
    assert flat.dbt_form is None


def test_spot_and_magnification_views_are_not_standard_views():
    standard = loaded(ViewPosition=" cc ")
    spot = loaded(ViewPosition="CC", spot_mag=1.0)
    modifier = loaded(ViewPosition="MLO", **{"0_ViewCodeSequence_0_ViewModifierCodeSequence_CodeMeaning": "magnification"})
    worded = loaded(ViewPosition="SPOT CC")

    assert standard.view_position.value == "CC" and standard.source_view_position == "CC"
    assert standard.view_modification.value == "STANDARD"
    assert [image.view_modification.value for image in (spot, modifier, worded)] == ["MODIFIED"] * 3
    assert worded.view_position.value == "CC" and spot.spot_magnification is True


def test_a_missing_spot_flag_is_not_a_negative_determination():
    image = loaded(ViewPosition="CC", spot_mag=None)

    assert image.spot_magnification is None


def test_an_unparseable_spot_flag_is_reported():
    report = load_embed(images=[image_row(spot_mag="yes")])

    assert report.graph.images[0].spot_magnification is None
    assert "image_flag_parse" in {issue.code for issue in report.issues}


def test_series_description_recovers_missing_side_and_view_without_overriding_tags():
    missing = loaded(ImageLateralityFinal=None, ViewPosition=None, SeriesDescription="R MLO")
    populated = loaded(ImageLateralityFinal="L", ViewPosition="CC", SeriesDescription="R MLO")
    unparseable = loaded(ImageLateralityFinal=None, ViewPosition=None, SeriesDescription="Tomosynthesis")

    assert (missing.laterality.value, missing.view_position.value) == ("UNKNOWN", "UNKNOWN")
    assert (missing.recovered_laterality.value, missing.recovered_view_position.value) == ("R", "MLO")
    assert (populated.recovered_laterality.value, populated.recovered_view_position.value) == ("L", "CC")
    assert (unparseable.recovered_laterality.value, unparseable.recovered_view_position.value) == ("UNKNOWN", "UNKNOWN")
