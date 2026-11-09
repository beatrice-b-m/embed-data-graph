"""Static consumer journey: checked by mypy, not executed by pytest."""
from datetime import date
from typing import Optional, Tuple
from typing_extensions import assert_type

from embed_data_graph import (
    DbtForm, ViewModification, ViewPosition,
    DatasetGraph, Exam, Finding, Laterality, LoadReport,
    CancerRegistryEntry, MammogramImage, Patient, Pathology, RegionOfInterest,
    UnkeyedRegistryEntry, UnresolvedClinicalRecord, load_embed,
)
from embed_data_graph.core.selection import Selection
from embed_data_graph.clinical.attributes import AttributeResolution
from embed_data_graph.clinical.histories import CancerHistoryObservation, PatientHistoryObservation


class ResearchPatient(Patient):
    pass


graph = DatasetGraph()
assert_type(graph.patient("P"), Optional[Patient])
assert_type(graph.exam("A"), Optional[Exam])
assert_type(graph.finding("A", "1"), Optional[Finding])
assert_type(graph.source_image("SOP"), Optional[MammogramImage])
assert_type(graph.roi("I", "0"), Optional[RegionOfInterest])
assert_type(graph.get("exam", "A"), Optional[Exam])
assert_type(graph.exams, Tuple[Exam, ...])
patient = graph.register(ResearchPatient("P"))
assert_type(patient, ResearchPatient)
assert_type(patient.update(sex="F"), ResearchPatient)
assert_type(patient.rekey(patient_id="Q"), ResearchPatient)
assert_type(graph.update(patient, sex="F"), ResearchPatient)
assert_type(graph.pop(patient), ResearchPatient)
assert_type(graph.attach(patient, Exam("A")), Exam)
assert_type(Exam("B").findings, Tuple[Finding, ...])
selected = graph.select(level="exam", predicate=lambda exam: exam.description == "screening")
assert_type(selected, Selection[Exam])
assert_type(next(iter(selected)), Exam)
assert_type(graph.select(level="image", predicate=lambda image: image.is_dbt), Selection[MammogramImage])
parts = graph.partition(level="finding", key=lambda finding: finding.laterality)
assert_type(parts[Laterality.LEFT], DatasetGraph)
assert_type(graph.partition_by_validation(level="exam"), Tuple[DatasetGraph, DatasetGraph])
assert_type(load_embed(patients=[{"empi_anon": "P"}], mode="merge"), LoadReport)
assert_type(load_embed(exams=({"acc_anon": str(i)} for i in range(2))), LoadReport)
assert_type(load_embed(images=[{"acc_anon": "A"}], into=DatasetGraph(), parents="existing"), LoadReport)
assert_type(Pathology(patient_id="P", record_id="R"), Pathology)
assert_type(RegionOfInterest.from_embed_coordinates((0, 0, 9, 9), image_id="I", roi_key="0"), RegionOfInterest)


class ResearchROI(RegionOfInterest):
    pass


research_roi = ResearchROI.from_embed_coordinates((0, 0, 9, 9), image_id="I", roi_key="0")
assert_type(research_roi, ResearchROI)
assert_type(research_roi.resize(scale_y=2, scale_x=2), ResearchROI)
assert_type(research_roi.update(confidence=0.5), ResearchROI)
assert_type(Patient("P").attribute_resolution("sex", date(2020, 1, 1)), AttributeResolution)
assert_type(Patient("P").history_as_of(date(2020, 1, 1), kind="procedure"), Tuple[PatientHistoryObservation, ...])
assert_type(Patient("P").cancer_history, Tuple[CancerHistoryObservation, ...])
assert_type(load_embed(cancer_history=[{"empi_anon": "P", "patient": 0}]), LoadReport)
assert_type(MammogramImage("I").dbt_form, Optional[DbtForm])
assert_type(MammogramImage("I").view_modification, ViewModification)
assert_type(MammogramImage("I").recovered_view_position, ViewPosition)
assert_type(MammogramImage("I", spot_magnification=True).spot_magnification, Optional[bool])
assert_type(Exam("C").imaged_laterality, Laterality)
assert_type(Patient("P").registry_entries, Tuple[CancerRegistryEntry, ...])
assert_type(Patient("P").unkeyed_registry_entries, Tuple[UnkeyedRegistryEntry, ...])
assert_type(
    Patient("P").set_unkeyed_registry_entries([UnkeyedRegistryEntry({"site": "C50"})]),
    Tuple[UnkeyedRegistryEntry, ...],
)
assert_type(Patient("P").unresolved_clinical_records, Tuple[UnresolvedClinicalRecord, ...])
assert_type(Patient("P").procedures[0].identity.laterality, Laterality)
