"""Quality inspection is optional, read-only, and composes with owning partitions."""
from embed_data_graph import DatasetGraph, Exam, MammogramImage, Patient, RegionOfInterest
from embed_data_graph.core.source import Issue, IssueSeverity
from embed_data_graph.core.validation import validate


def test_invalid_raw_pathology_severity_remains_available_to_validation():
    from embed_data_graph import Pathology
    record = Pathology("P", "record", raw_severity=9)
    assert record.raw_severity == 9
    assert "pathology_raw_severity" in {issue.code for issue in validate(record).issues}


def test_geometry_and_confidence_are_representable_before_inspection():
    image = MammogramImage("I", height=10, width=10)
    roi = image.add_roi(RegionOfInterest((3, -1, 2, 20), "I", "0", confidence=2))
    graph = DatasetGraph()
    graph.register(image)
    before = roi.to_dict()
    result = validate(image)
    assert not result.valid
    assert {issue.code for issue in result.issues} >= {"roi_order", "roi_bounds", "confidence_range"}
    assert roi.to_dict() == before


def test_missing_optional_data_is_valid_and_custom_rules_are_explicit():
    patient = Patient("P")
    patient.reviewed = False
    assert validate(patient).valid

    def reviewer(obj):
        if getattr(obj, "reviewed", True) is False:
            yield Issue("unreviewed", "Review is pending", IssueSeverity.WARNING)

    assert validate(patient, validators=[reviewer]).valid
    assert not validate(patient, validators=[reviewer], warnings_invalid=True).valid
    assert patient.reviewed is False


def test_validation_partition_copies_selected_descendants():
    graph = DatasetGraph()
    patient = graph.register(Patient("P"))
    good = patient.add_exam(Exam("good"))
    bad = patient.add_exam(Exam("bad"))
    image = bad.add_image(MammogramImage("I", accession_number="bad", height=-2))
    valid, invalid = graph.partition_by_validation(level="exam")

    assert [exam.accession_number for exam in valid.exams] == ["good"]
    assert [exam.accession_number for exam in invalid.exams] == ["bad"]
    assert invalid.image("I") is not None and invalid.image("I") is not image
    assert valid.exam("good") is not good
    assert graph.exam("good") is good and graph.exam("bad") is bad


def test_shared_descendant_is_validated_once():
    from embed_data_graph import Finding, Laterality, Procedure, ProcedureIdentity
    exam = Exam("A")
    proc = Procedure(ProcedureIdentity("P", "2020-01-01", "biopsy", Laterality.LEFT))
    for number in ("1", "2"):
        exam.add_finding(Finding("A", Laterality.LEFT, number)).add_procedure(proc)
    seen = []

    def inspect(obj):
        seen.append(id(obj))
        return ()

    validate(exam, validators=[inspect])
    assert seen.count(id(proc)) == 1
