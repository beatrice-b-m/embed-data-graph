"""Source records retained without inventing clinical identities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from embed_data_graph.clinical.interpretations import ImagingInterpretation
from embed_data_graph.core.primitives import Laterality
from embed_data_graph.core.source import SourceRef


@dataclass
class UnkeyedFinding:
    """An assessment row on a known exam without a finding number.

    Attributes
    ----------
    accession_number : str
        Known parent exam; no finding identity is invented.
    interpretation : ImagingInterpretation or None
        Assessment and recommendation as reported.
    descriptors : dict
        Semantic descriptor names to codes; owned copy supplied by the loader.
    source : SourceRef or None
        Optional physical evidence, never clinical identity.
    laterality : Laterality
        Always UNKNOWN: a missing number cannot establish a side-level finding.
    reported_laterality : Laterality, optional
        Side reported by this row, independent of finding identity. Default
        UNKNOWN; missing or unrecognized values remain UNKNOWN, never bilateral.
        This source fact may be used for side-level assessment review.
    finding_number : None
        Explicitly missing.
    reason : str
        Machine-readable issue code. Records are snapshot values, not entities;
        repeated identical rows remain separate. Refresh replaces the addressed
        exam/table snapshot; merge appends every incoming row with a diagnostic
        because no clinical identity can deduplicate repeated loads.
    """

    accession_number: str
    interpretation: Optional[ImagingInterpretation] = None
    descriptors: Dict[str, Any] = field(default_factory=dict)
    source: Optional[SourceRef] = None
    reported_laterality: Laterality = Laterality.UNKNOWN
    laterality: Laterality = field(default=Laterality.UNKNOWN, init=False)
    finding_number: None = field(default=None, init=False)
    reason: str = field(default="missing_finding_identity", init=False)

    def __post_init__(self) -> None:
        self.reported_laterality = Laterality.coerce(self.reported_laterality)


@dataclass
class InvalidAccessionRecord:
    """A row whose accession is configured as invalid, retained under its patient.

    Attributes
    ----------
    patient_id : str or None
        Reported patient; None records remain graph-level unresolved records.
    accession_number : str
        Invalid source value, never registered as an exam key.
    table : str
        Input table name.
    values : dict
        Mapped semantic values, keyed as ``grain.field`` for wide MagView rows.
        Includes explicit nulls; no physical column names or consumer metadata.
    source : SourceRef or None
        Physical evidence only.
    reason : str
        ``invalid_accession``. These are snapshot records, without semantic IDs;
        refresh replaces each addressed patient/table snapshot. Merge appends
        every incoming row and emits a diagnostic; repeated loads retain repeats.
    """

    patient_id: Optional[str]
    accession_number: str
    table: str
    values: Dict[str, Any]
    source: Optional[SourceRef] = None
    reason: str = field(default="invalid_accession", init=False)
