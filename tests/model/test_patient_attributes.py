"""Patient attributes reported per exam and chosen as of a date."""

from datetime import date

import pytest

from embed_data_graph import Patient
from embed_data_graph.clinical.attributes import PatientAttributeObservation


def observation(value, accession, day):
    return PatientAttributeObservation("sex", value, accession, day)


@pytest.fixture
def patient():
    return Patient(
        "P1",
        attribute_observations=[
            observation("F", "A1", date(2020, 1, 1)),
            observation("U", "A2", date(2022, 1, 1)),
        ],
    )


def test_as_of_returns_the_latest_value_on_or_before_the_date(patient):
    assert patient.attribute_as_of("sex", date(2019, 12, 31)) is None
    assert patient.attribute_as_of("sex", date(2020, 1, 1)) == "F"
    assert patient.attribute_as_of("sex", date(2021, 6, 1)) == "F"
    assert patient.attribute_as_of("sex", date(2023, 1, 1)) == "U"


def test_as_of_is_unknown_when_values_disagree_on_the_latest_date(patient):
    patient.add_attribute_observation(observation("M", "A3", date(2022, 1, 1)))

    assert patient.attribute_as_of("sex", date(2023, 1, 1)) is None


def test_as_of_ignores_undated_observations_and_explicit_nulls(patient):
    patient.add_attribute_observation(observation("X", "A9", None))
    patient.add_attribute_observation(observation(None, "A4", date(2022, 6, 1)))

    assert patient.attribute_as_of("sex", date(2023, 1, 1)) == "U"


def test_an_observation_with_the_same_context_replaces_the_earlier_one(patient):
    patient.add_attribute_observation(observation("M", "A1", date(2020, 1, 1)))

    assert [item.value for item in patient.attribute_history("sex")] == ["M", "U"]
