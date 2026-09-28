"""Exam, patient and finding features loaded from MagView rows."""

from embed_data_graph import load_embed, validate


def row(**fields):
    base = {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L"}
    base.update(fields)
    return base


def test_exam_level_features_load_as_source_values():
    exam = load_embed(
        magview=[row(tissueden=3.0, mg_exam_type="screening", vtype="SC", modality_desc="MG", age_at_study_anon=57.0)]
    ).graph.exam("A1")

    assert [code.code for code in (exam.density, exam.exam_type, exam.visit_type, exam.modality)] == [
        "3", "screening", "SC", "MG"
    ]
    assert exam.density.meaning == "Heterogeneously dense"
    assert exam.exam_type.meaning == "screening exam"
    assert exam.modality.meaning == "mammogram"
    assert exam.patient_age == 57


def test_conflicting_exam_values_across_finding_rows_are_reported():
    report = load_embed(magview=[row(tissueden=2), row(numfind=2, tissueden=3)])

    assert report.graph.exam("A1").density is None
    assert "conflicting_exam_density" in {issue.code for issue in report.issues}


def test_zero_age_loads_but_fails_validation():
    exam = load_embed(magview=[row(age_at_study_anon=0)]).graph.exam("A1")

    assert exam.patient_age == 0
    assert "plausible_patient_age" in {issue.code for issue in validate(exam, aggregate=False).issues}


def test_race_and_ethnicity_are_patient_attributes_over_time():
    patient = load_embed(magview=[row(race="White", ethnicity="Non-Hispanic", studydate_anon="2020-01-01")]).graph.patient("P1")

    assert (patient.race, patient.ethnicity) == ("White", "Non-Hispanic")
    assert [item.attribute for item in patient.attribute_observations] == ["race", "ethnicity"]


def test_finding_descriptors_keep_source_codes():
    finding = load_embed(
        magview=[row(mass=1, massshape="x", massmargin="S", calc=0, calcfind="A,B", calcnumber=-2.0)]
    ).graph.finding("A1", "1")

    codes = {name: value.code for name, value in finding.descriptors.items()}
    assert codes == {
        "mass": "1",
        "mass_shape": "X",
        "mass_margin": "S",
        "calcification": "0",
        "calcification_morphology": "A,B",
        "calcification_number": "-2",
    }
    assert finding.descriptors["mass"].meaning == "Represented"
    assert finding.descriptors["mass_shape"].meaning == "Irregular"
    assert finding.descriptors["mass_margin"].meaning == "Spiculated"
    assert finding.descriptors["calcification_morphology"].tokens == ("A", "B")
    assert finding.descriptors["calcification_number"].meaning is None


def test_descriptor_refresh_is_per_column():
    graph = load_embed(magview=[row(massshape="O", calcfind="A")]).graph
    load_embed(magview=[row(massshape=None)], into=graph)

    assert list(graph.finding("A1", "1").descriptors) == ["calcification_morphology"]
