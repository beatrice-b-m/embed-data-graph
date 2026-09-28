"""MagView-specific normalization helpers.

This module keeps MagView source-code parsing out of the source-neutral core
anatomy objects. The normalized output is a core ``AnatomicalPosition`` plus
local evidence and warning records that are plain dataclasses for now.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Tuple

from embed_data_graph.core.anatomy import (
    AnatomicalLocationCategory,
    AnatomicalPosition,
    ClockFacePosition,
    DepthThird,
    MedialLateralAxis,
    Quadrant,
    SuperiorInferiorAxis,
)
from embed_data_graph.core.primitives import Laterality


@dataclass(frozen=True)
class MagViewSourceEvidence:
    """Serializable source-code evidence used during MagView normalization.

    Attributes
    ----------
    field : str
        Source column name associated with the evidence or warning.
    raw_value : str
        Original unnormalized value retained as source evidence; not a semantic
        identity.
    normalized_kind : str
        Non-empty label describing the normalized concept.
    normalized_value : str
        Normalized value retained alongside source evidence.
    """

    field: str
    """Source column name associated with the evidence or warning."""
    raw_value: str
    """Original unnormalized value retained as source evidence; not a semantic identity."""
    normalized_kind: str
    """Non-empty label describing the normalized concept."""
    normalized_value: str
    """Normalized value retained alongside source evidence."""


@dataclass(frozen=True)
class MagViewNormalizationWarning:
    """Serializable warning emitted for unknown or conflicting source values.

    Attributes
    ----------
    code : str
        Non-empty machine-readable diagnostic code.
    message : str
        Non-empty human-readable diagnostic explanation.
    field : Optional[str]
        Source column name associated with the evidence or warning. Default:
        None.
    raw_value : Optional[str]
        Original unnormalized value retained as source evidence; not a semantic
        identity. Default: None.
    """

    code: str
    """Non-empty machine-readable diagnostic code."""
    message: str
    """Non-empty human-readable diagnostic explanation."""
    field: Optional[str] = None
    """Source column name associated with the evidence or warning. Default: None."""
    raw_value: Optional[str] = None
    """Original unnormalized value retained as source evidence; not a semantic
    identity. Default: None.
    """


@dataclass(frozen=True)
class MagViewLocationNormalization:
    """Normalized MagView location result and source evidence.

    Attributes
    ----------
    position : AnatomicalPosition
        Normalized AnatomicalPosition; unobserved axes remain UNKNOWN.
    evidence : Tuple[MagViewSourceEvidence, ...]
        Ordered evidence for the normalized source codes. Default: ().
    warnings : Tuple[MagViewNormalizationWarning, ...]
        Diagnostic messages/records in emission order; empty means none emitted.
        Default: ().
    """

    position: AnatomicalPosition
    """Normalized AnatomicalPosition; unobserved axes remain UNKNOWN."""
    evidence: Tuple[MagViewSourceEvidence, ...] = ()
    """Ordered evidence for the normalized source codes. Default: ()."""
    warnings: Tuple[MagViewNormalizationWarning, ...] = ()
    """Diagnostic messages/records in emission order; empty means none emitted. Default: ()."""


@dataclass(frozen=True)
class _LocationMapping:
    ml: MedialLateralAxis = MedialLateralAxis.UNKNOWN
    si: SuperiorInferiorAxis = SuperiorInferiorAxis.UNKNOWN
    depth: DepthThird = DepthThird.UNKNOWN
    category: Optional[AnatomicalLocationCategory] = None

    def to_quadrant(self, laterality: Laterality) -> Quadrant:
        return Quadrant(
            laterality=laterality,
            ml=self.ml,
            si=self.si,
            depth=self.depth,
        )


_LOCATION_CODES = {
    "OU": _LocationMapping(ml=MedialLateralAxis.LATERAL),
    "L": _LocationMapping(ml=MedialLateralAxis.LATERAL),
    "IN": _LocationMapping(ml=MedialLateralAxis.MEDIAL),
    "D": _LocationMapping(ml=MedialLateralAxis.MEDIAL),
    "Z": _LocationMapping(
        ml=MedialLateralAxis.MEDIAL,
        si=SuperiorInferiorAxis.INFERIOR,
    ),
    "X": _LocationMapping(
        ml=MedialLateralAxis.MEDIAL,
        si=SuperiorInferiorAxis.SUPERIOR,
    ),
    "Y": _LocationMapping(
        ml=MedialLateralAxis.LATERAL,
        si=SuperiorInferiorAxis.INFERIOR,
    ),
    "W": _LocationMapping(
        ml=MedialLateralAxis.LATERAL,
        si=SuperiorInferiorAxis.SUPERIOR,
    ),
    "C": _LocationMapping(
        ml=MedialLateralAxis.CENTRAL,
        si=SuperiorInferiorAxis.CENTRAL,
        category=AnatomicalLocationCategory.CENTRAL,
    ),
    "CENTRAL": _LocationMapping(
        ml=MedialLateralAxis.CENTRAL,
        si=SuperiorInferiorAxis.CENTRAL,
        category=AnatomicalLocationCategory.CENTRAL,
    ),
    "A": _LocationMapping(
        si=SuperiorInferiorAxis.SUPERIOR,
        depth=DepthThird.POSTERIOR,
        category=AnatomicalLocationCategory.AXILLARY_TAIL,
    ),
    "T": _LocationMapping(
        si=SuperiorInferiorAxis.SUPERIOR,
        depth=DepthThird.POSTERIOR,
        category=AnatomicalLocationCategory.AXILLARY_TAIL,
    ),
    "AX": _LocationMapping(
        si=SuperiorInferiorAxis.SUPERIOR,
        depth=DepthThird.POSTERIOR,
        category=AnatomicalLocationCategory.AXILLARY_TAIL,
    ),
    "AXILLARYTAIL": _LocationMapping(
        si=SuperiorInferiorAxis.SUPERIOR,
        depth=DepthThird.POSTERIOR,
        category=AnatomicalLocationCategory.AXILLARY_TAIL,
    ),
    "AXILLARY_TAIL": _LocationMapping(
        si=SuperiorInferiorAxis.SUPERIOR,
        depth=DepthThird.POSTERIOR,
        category=AnatomicalLocationCategory.AXILLARY_TAIL,
    ),
    "UP": _LocationMapping(si=SuperiorInferiorAxis.SUPERIOR),
    "U": _LocationMapping(si=SuperiorInferiorAxis.SUPERIOR),
    "LO": _LocationMapping(si=SuperiorInferiorAxis.INFERIOR),
    "I": _LocationMapping(si=SuperiorInferiorAxis.INFERIOR),
    "S": _LocationMapping(
        ml=MedialLateralAxis.CENTRAL,
        si=SuperiorInferiorAxis.CENTRAL,
        depth=DepthThird.ANTERIOR,
        category=AnatomicalLocationCategory.SUBAREOLAR,
    ),
    "SUBAREOLAR": _LocationMapping(
        ml=MedialLateralAxis.CENTRAL,
        si=SuperiorInferiorAxis.CENTRAL,
        depth=DepthThird.ANTERIOR,
        category=AnatomicalLocationCategory.SUBAREOLAR,
    ),
    "RA": _LocationMapping(
        ml=MedialLateralAxis.CENTRAL,
        si=SuperiorInferiorAxis.CENTRAL,
        depth=DepthThird.ANTERIOR,
        category=AnatomicalLocationCategory.RETROAREOLAR,
    ),
    "RETRO": _LocationMapping(
        ml=MedialLateralAxis.CENTRAL,
        si=SuperiorInferiorAxis.CENTRAL,
        depth=DepthThird.ANTERIOR,
        category=AnatomicalLocationCategory.RETROAREOLAR,
    ),
    "RETROAREOLAR": _LocationMapping(
        ml=MedialLateralAxis.CENTRAL,
        si=SuperiorInferiorAxis.CENTRAL,
        depth=DepthThird.ANTERIOR,
        category=AnatomicalLocationCategory.RETROAREOLAR,
    ),
    "AN": _LocationMapping(depth=DepthThird.ANTERIOR),
    "MD": _LocationMapping(depth=DepthThird.MIDDLE),
}

_DEPTH_CODES = {
    "A": DepthThird.ANTERIOR,
    "AN": DepthThird.ANTERIOR,
    "ANTERIOR": DepthThird.ANTERIOR,
    "M": DepthThird.MIDDLE,
    "MD": DepthThird.MIDDLE,
    "MIDDLE": DepthThird.MIDDLE,
    "P": DepthThird.POSTERIOR,
    "POSTERIOR": DepthThird.POSTERIOR,
}


def normalize_magview_location(
    *,
    laterality: Any,
    location_code: Any = None,
    depth_code: Any = None,
    clock_code: Any = None,
) -> MagViewLocationNormalization:
    """Normalize MagView location, depth, and clock codes.

    Clock position supplies the preferred medial/lateral and superior/inferior
    axes when present. Explicit depth is applied before location-derived depth,
    so it has precedence over defaults implied by codes such as subareolar or
    axillary tail.

    Parameters
    ----------
    laterality : object
        Side accepted by Laterality.coerce. Non-unilateral values emit a warning.
    location_code, depth_code, clock_code : object, optional
        Source codes, delimited strings or iterables; defaults None mean absent.
        Location examples include OU and IN; depth accepts A/M/P; clock accepts
        hours 1–12. Unknown/conflicting codes are retained in warnings/evidence.

    Returns
    -------
    MagViewLocationNormalization
        Anatomical position plus ordered evidence and warnings. Unknown axes
        remain UNKNOWN and absent clock/named location remains None. Inputs are
        not mutated. This does not localize a finding in an image.

    Examples
    --------
    >>> result = normalize_magview_location(laterality="L", location_code="OU")
    >>> result.position.quadrant.ml.value
    'lateral'
    """

    side = Laterality.coerce(laterality)
    evidence: list[MagViewSourceEvidence] = []
    warnings: list[MagViewNormalizationWarning] = []

    if not side.is_unilateral:
        warnings.append(
            MagViewNormalizationWarning(
                code="unsupported_laterality",
                message="MagView location normalization requires left or right laterality.",
                field="laterality",
                raw_value="" if laterality is None else str(laterality),
            )
        )

    quadrant = Quadrant(laterality=side)
    location_category: Optional[AnatomicalLocationCategory] = None
    clock_position: Optional[ClockFacePosition] = None

    explicit_depth = _parse_depth_codes(depth_code, evidence, warnings)
    if explicit_depth is not DepthThird.UNKNOWN:
        quadrant = Quadrant(laterality=side, depth=explicit_depth)

    clock_position = _parse_clock_codes(clock_code, evidence, warnings)
    if clock_position is None:
        clock_position = _parse_clock_from_location(location_code, evidence, warnings)

    clock_quadrant: Optional[Quadrant] = None
    if clock_position is not None and side.is_unilateral:
        clock_quadrant = clock_position.to_quadrant(side)
        quadrant = _merge_quadrant(
            base=quadrant,
            candidate=clock_quadrant,
            source="clock",
            warnings=warnings,
            prefer_candidate=True,
        )

    for raw_code in _iter_codes(location_code):
        code = _normalize_code(raw_code)
        if _is_clock_code(code):
            continue
        mapping = _LOCATION_CODES.get(code)
        if mapping is None:
            warnings.append(
                MagViewNormalizationWarning(
                    code="unknown_location_code",
                    message=f"Unknown MagView location code: {raw_code!r}.",
                    field="location_code",
                    raw_value=str(raw_code),
                )
            )
            continue

        evidence.append(
            MagViewSourceEvidence(
                field="location_code",
                raw_value=str(raw_code),
                normalized_kind="location",
                normalized_value=_mapping_value(mapping),
            )
        )
        location_category = _merge_category(
            existing=location_category,
            candidate=mapping.category,
            raw_value=str(raw_code),
            warnings=warnings,
        )
        if clock_quadrant is not None:
            _warn_if_quadrant_conflicts(
                clock_quadrant=clock_quadrant,
                location_quadrant=mapping.to_quadrant(side),
                raw_value=str(raw_code),
                warnings=warnings,
            )
        quadrant = _merge_quadrant(
            base=quadrant,
            candidate=mapping.to_quadrant(side),
            source="location_code",
            warnings=warnings,
            prefer_candidate=False,
        )

    position = AnatomicalPosition(
        laterality=side,
        quadrant=quadrant,
        clock_position=clock_position,
        location_category=location_category,
    )
    return MagViewLocationNormalization(
        position=position,
        evidence=tuple(evidence),
        warnings=tuple(warnings),
    )


def _parse_depth_codes(
    value: Any,
    evidence: list[MagViewSourceEvidence],
    warnings: list[MagViewNormalizationWarning],
) -> DepthThird:
    depth = DepthThird.UNKNOWN
    for raw_code in _iter_codes(value):
        code = _normalize_code(raw_code)
        candidate = _DEPTH_CODES.get(code)
        if candidate is None:
            warnings.append(
                MagViewNormalizationWarning(
                    code="unknown_depth_code",
                    message=f"Unknown MagView depth code: {raw_code!r}.",
                    field="depth_code",
                    raw_value=str(raw_code),
                )
            )
            continue
        evidence.append(
            MagViewSourceEvidence(
                field="depth_code",
                raw_value=str(raw_code),
                normalized_kind="depth",
                normalized_value=candidate.value,
            )
        )
        if depth is not DepthThird.UNKNOWN and depth is not candidate:
            warnings.append(
                MagViewNormalizationWarning(
                    code="conflicting_depth_code",
                    message=(
                        "Conflicting MagView depth codes; keeping the first "
                        f"explicit depth {depth.value!r}."
                    ),
                    field="depth_code",
                    raw_value=str(raw_code),
                )
            )
            continue
        depth = candidate
    return depth


def _parse_clock_codes(
    value: Any,
    evidence: list[MagViewSourceEvidence],
    warnings: list[MagViewNormalizationWarning],
) -> Optional[ClockFacePosition]:
    clock: Optional[ClockFacePosition] = None
    for raw_code in _iter_codes(value):
        code = _normalize_code(raw_code)
        if not _is_clock_code(code):
            warnings.append(
                MagViewNormalizationWarning(
                    code="unknown_clock_code",
                    message=f"Unknown MagView clock code: {raw_code!r}.",
                    field="clock_code",
                    raw_value=str(raw_code),
                )
            )
            continue
        try:
            candidate = ClockFacePosition.coerce(code)
        except ValueError:
            warnings.append(
                MagViewNormalizationWarning(
                    code="unknown_clock_code",
                    message=f"Unknown MagView clock code: {raw_code!r}.",
                    field="clock_code",
                    raw_value=str(raw_code),
                )
            )
            continue

        evidence.append(
            MagViewSourceEvidence(
                field="clock_code",
                raw_value=str(raw_code),
                normalized_kind="clock",
                normalized_value=str(candidate.hour),
            )
        )
        if clock is not None and clock != candidate:
            warnings.append(
                MagViewNormalizationWarning(
                    code="conflicting_clock_code",
                    message=(
                        "Conflicting MagView clock codes; keeping the first "
                        f"clock position {clock.hour!r}."
                    ),
                    field="clock_code",
                    raw_value=str(raw_code),
                )
            )
            continue
        clock = candidate
    return clock


def _parse_clock_from_location(
    value: Any,
    evidence: list[MagViewSourceEvidence],
    warnings: list[MagViewNormalizationWarning],
) -> Optional[ClockFacePosition]:
    clock: Optional[ClockFacePosition] = None
    for raw_code in _iter_codes(value):
        code = _normalize_code(raw_code)
        if not _is_clock_code(code):
            continue
        try:
            candidate = ClockFacePosition.coerce(code)
        except ValueError:
            continue

        evidence.append(
            MagViewSourceEvidence(
                field="location_code",
                raw_value=str(raw_code),
                normalized_kind="clock",
                normalized_value=str(candidate.hour),
            )
        )
        if clock is not None and clock != candidate:
            warnings.append(
                MagViewNormalizationWarning(
                    code="conflicting_clock_code",
                    message=(
                        "Conflicting MagView clock values in location codes; "
                        f"keeping the first clock position {clock.hour!r}."
                    ),
                    field="location_code",
                    raw_value=str(raw_code),
                )
            )
            continue
        clock = candidate
    return clock


def _merge_quadrant(
    *,
    base: Quadrant,
    candidate: Quadrant,
    source: str,
    warnings: list[MagViewNormalizationWarning],
    prefer_candidate: bool,
) -> Quadrant:
    ml = _merge_axis(
        axis_name="ml",
        existing=base.ml,
        candidate=candidate.ml,
        unknown=MedialLateralAxis.UNKNOWN,
        source=source,
        warnings=warnings,
        prefer_candidate=prefer_candidate,
    )
    si = _merge_axis(
        axis_name="si",
        existing=base.si,
        candidate=candidate.si,
        unknown=SuperiorInferiorAxis.UNKNOWN,
        source=source,
        warnings=warnings,
        prefer_candidate=prefer_candidate,
    )
    depth = _merge_axis(
        axis_name="depth",
        existing=base.depth,
        candidate=candidate.depth,
        unknown=DepthThird.UNKNOWN,
        source=source,
        warnings=warnings,
        prefer_candidate=prefer_candidate,
    )
    return Quadrant(laterality=base.laterality, ml=ml, si=si, depth=depth)


def _merge_axis(
    *,
    axis_name: str,
    existing: Any,
    candidate: Any,
    unknown: Any,
    source: str,
    warnings: list[MagViewNormalizationWarning],
    prefer_candidate: bool,
) -> Any:
    if candidate is unknown:
        return existing
    if existing is unknown:
        return candidate
    if existing is candidate:
        return existing

    warnings.append(
        MagViewNormalizationWarning(
            code=f"conflicting_{axis_name}",
            message=(
                f"Conflicting MagView {axis_name} values from {source}; "
                f"{'using new value' if prefer_candidate else 'keeping existing value'}."
            ),
            field=source,
            raw_value=getattr(candidate, "value", str(candidate)),
        )
    )
    return candidate if prefer_candidate else existing


def _warn_if_quadrant_conflicts(
    *,
    clock_quadrant: Quadrant,
    location_quadrant: Quadrant,
    raw_value: str,
    warnings: list[MagViewNormalizationWarning],
) -> None:
    checks = (
        ("ml", clock_quadrant.ml, location_quadrant.ml, MedialLateralAxis.UNKNOWN),
        ("si", clock_quadrant.si, location_quadrant.si, SuperiorInferiorAxis.UNKNOWN),
    )
    for axis_name, clock_value, location_value, unknown in checks:
        if location_value is unknown or clock_value is location_value:
            continue
        warnings.append(
            MagViewNormalizationWarning(
                code="conflicting_clock_quadrant",
                message=(
                    "MagView clock position conflicts with location quadrant; "
                    "clock-derived axes are preferred."
                ),
                field="location_code",
                raw_value=raw_value,
            )
        )


def _merge_category(
    *,
    existing: Optional[AnatomicalLocationCategory],
    candidate: Optional[AnatomicalLocationCategory],
    raw_value: str,
    warnings: list[MagViewNormalizationWarning],
) -> Optional[AnatomicalLocationCategory]:
    if candidate is None:
        return existing
    if existing is None or existing is candidate:
        return candidate
    warnings.append(
        MagViewNormalizationWarning(
            code="conflicting_location_category",
            message="Conflicting MagView named location categories; keeping the first.",
            field="location_code",
            raw_value=raw_value,
        )
    )
    return existing


def _iter_codes(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return ()
        return tuple(part for part in re.split(r"[,;/|]+", text) if part.strip())
    if isinstance(value, Iterable):
        codes: list[str] = []
        for item in value:
            codes.extend(_iter_codes(item))
        return tuple(codes)
    return (str(value),)


def _normalize_code(value: Any) -> str:
    text = str(value).strip().upper()
    text = text.replace("-", "_").replace(" ", "_")
    return text


def _is_clock_code(code: str) -> bool:
    return bool(re.fullmatch(r"C?(1[0-2]|[1-9])(?::?00)?", code))


def _mapping_value(mapping: _LocationMapping) -> str:
    parts = []
    if mapping.ml is not MedialLateralAxis.UNKNOWN:
        parts.append(f"ml={mapping.ml.value}")
    if mapping.si is not SuperiorInferiorAxis.UNKNOWN:
        parts.append(f"si={mapping.si.value}")
    if mapping.depth is not DepthThird.UNKNOWN:
        parts.append(f"depth={mapping.depth.value}")
    if mapping.category is not None:
        parts.append(f"category={mapping.category.value}")
    return ",".join(parts) if parts else "unknown"
