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
