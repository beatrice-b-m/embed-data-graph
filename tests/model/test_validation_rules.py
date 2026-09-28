"""Built-in validation rules on individual objects."""

import pytest

from embed_data_graph import ImageModality, MammogramImage, validate


def issue_codes(entity):
    return {issue.code for issue in validate(entity).issues}


@pytest.mark.parametrize("modality", [ImageModality.DBT, ImageModality.UNKNOWN])
def test_frame_count_is_expected_on_dbt_or_unknown_modality(modality):
    image = MammogramImage("I1", modality=modality, frame_count=60, height=10, width=10)

    assert validate(image).valid
    assert "frame_modality" not in issue_codes(image)


def test_multiple_frames_on_a_2d_image_is_a_warning_not_an_error():
    image = MammogramImage("I1", modality=ImageModality.FFDM, frame_count=60)

    result = validate(image)
    assert "frame_modality" in issue_codes(image)
    assert result.valid
    assert not validate(image, warnings_invalid=True).valid


def test_single_frame_2d_image_is_consistent():
    image = MammogramImage("I1", modality=ImageModality.FFDM, frame_count=1)

    assert "frame_modality" not in issue_codes(image)
