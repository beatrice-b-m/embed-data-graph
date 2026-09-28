"""Mutable clinical and mammography objects with explicit loading and validation.

Start with ``load_embed`` to consume in-memory table rows, or construct Patient,
Exam, Finding and imaging objects directly. DatasetGraph owns membership;
lookups return live objects, while partition makes independent graph copies.
``validate`` is an explicit read-only quality check, never an ingestion gate.

Common entry points are listed in __all__. Specialist anatomy, source,
attribute-selection and geometry types live in their defining submodules;
undocumented adapter internals are not supported extension points. This package
has no mandatory pandas dependency, opens no pixel files and infers no diagnosis.

Examples
--------
>>> report = load_embed(patients=[{"empi_anon": "P1"}])
>>> report.graph.patient("P1").patient_id
'P1'
"""

from importlib.metadata import version

from embed_data_graph.clinical.exams import BreastSide, Exam
from embed_data_graph.clinical.findings import Finding
from embed_data_graph.clinical.patients import Patient
from embed_data_graph.clinical.procedures import Procedure, ProcedureIdentity
from embed_data_graph.clinical.pathology import Pathology, CancerRegistryEntry
from embed_data_graph.core.codes import Code
from embed_data_graph.core.primitives import Laterality, ImageModality, ViewPosition
from embed_data_graph.core.validation import ValidationResult, validate
from embed_data_graph.core.graph import DatasetGraph
from embed_data_graph.core.source import Issue, SourceRef
from embed_data_graph.imaging.images import MammogramImage
from embed_data_graph.imaging.rois import Box, RegionOfInterest
from embed_data_graph.sources.embed import LoadReport, load_embed

__all__ = [
    "BreastSide",
    "Code",
    "Box",
    "DatasetGraph",
    "Exam",
    "Finding",
    "Issue",
    "LoadReport",
    "MammogramImage",
    "Patient",
    "Procedure",
    "ProcedureIdentity",
    "Pathology",
    "CancerRegistryEntry",
    "Laterality",
    "ImageModality",
    "ViewPosition",
    "ValidationResult",
    "validate",
    "RegionOfInterest",
    "SourceRef",
    "load_embed",
]

__version__ = version("embed-data-graph")
