"""Finding-level imaging interpretation: assessment and recommendation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from embed_data_graph.core.codes import Code
from embed_data_graph.core.entity import plain_value
from embed_data_graph.core.source import SourceRef, optional_source


@dataclass(eq=False)
class ImagingInterpretation:
    """Assessment and recommendation documented for one finding.

    The interpretation is stored on its Finding and does not repeat the
    finding's identity. It is mutable so the loader can refresh it in place,
    keeping a consumer's reference and extra attributes.

    Attributes
    ----------
    assessment : Code or None, optional
        Reported BI-RADS assessment with its meaning; None means missing and
        no category is inferred. Text is accepted as a code without meaning.
    recommendation : Code or None, optional
        Reported recommendation, possibly several comma-separated codes, with
        their meanings. Default None.
    sources : tuple of SourceRef, optional
        Distinct source rows supporting the interpretation. Default ().

    Notes
    -----
    An assessment or recommendation is never a tissue diagnosis.

    Examples
    --------
    >>> from embed_data_graph import Code
    >>> ImagingInterpretation(assessment=Code("S", "Suspicious")).assessment.meaning
    'Suspicious'
    """

    assessment: Optional[Code] = None
    """Reported assessment and its meaning; None means missing."""
    recommendation: Optional[Code] = None
    """Reported recommendation codes and their meanings; None means missing."""
    sources: Tuple[SourceRef, ...] = field(default=())
    """Distinct source rows supporting the interpretation."""

    def __post_init__(self) -> None:
        self.assessment = Code.coerce(self.assessment)
        self.recommendation = Code.coerce(self.recommendation)
        sources = tuple(
            value for value in (optional_source(item) for item in self.sources) if value is not None
        )
        if len(set(sources)) != len(sources):
            raise ValueError("sources must be distinct")
        self.sources = sources

    @property
    def source(self) -> Optional[SourceRef]:
        """The first source row, or None when there is none."""

        return self.sources[0] if self.sources else None

    def update(self, **values: Any) -> "ImagingInterpretation":
        """Set fields in place, re-check them, and return this interpretation."""

        for name, value in values.items():
            setattr(self, name, value)
        self.__post_init__()
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Return ``{"assessment", "recommendation", "sources"}`` as JSON values."""

        return {
            "assessment": plain_value(self.assessment),
            "recommendation": plain_value(self.recommendation),
            "sources": plain_value(self.sources),
        }
