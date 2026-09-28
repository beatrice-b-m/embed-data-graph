"""Breast anatomy models that are independent of source-code systems."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Tuple

from embed_data_graph.core.primitives import Laterality


class MedialLateralAxis(Enum):
    """Discrete medial/lateral breast axis.

    Members
    -------
    MEDIAL='medial', CENTRAL='central', LATERAL='lateral', UNKNOWN='unknown'.
    """

    MEDIAL = "medial"
    CENTRAL = "central"
    LATERAL = "lateral"
    UNKNOWN = "unknown"


class SuperiorInferiorAxis(Enum):
    """Discrete superior/inferior breast axis.

    Members
    -------
    INFERIOR='inferior', CENTRAL='central', SUPERIOR='superior',
    UNKNOWN='unknown'.
    """

    INFERIOR = "inferior"
    CENTRAL = "central"
    SUPERIOR = "superior"
    UNKNOWN = "unknown"


class DepthThird(Enum):
    """Named thirds along nipple-to-posterior depth.

    Members
    -------
    ANTERIOR='anterior', MIDDLE='middle', POSTERIOR='posterior',
    UNKNOWN='unknown'.
    """

    ANTERIOR = "anterior"
    MIDDLE = "middle"
    POSTERIOR = "posterior"
    UNKNOWN = "unknown"


class AnatomicalLocationCategory(Enum):
    """Named locations that should not be forced into quadrant-only anatomy.

    Members
    -------
    CENTRAL='central', RETROAREOLAR='retroareolar', SUBAREOLAR='subareolar',
    AXILLARY_TAIL='axillary_tail', UNKNOWN='unknown'.
    """

    CENTRAL = "central"
    RETROAREOLAR = "retroareolar"
    SUBAREOLAR = "subareolar"
    AXILLARY_TAIL = "axillary_tail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClockFacePosition:
    """Clock-face breast location using conventional 1 through 12 hours.

    Attributes
    ----------
    hour : int
        Integer clock hour, conventionally 1–12. Out-of-range integers are
        retained for validate; bool/non-integer raises ValueError.
    """

    hour: int
    """Integer clock hour, conventionally 1–12. Out-of-range integers are retained
    for validate; bool/non-integer raises ValueError.
    """

    def __post_init__(self) -> None:
        if isinstance(self.hour, bool) or not isinstance(self.hour, int):
            raise ValueError("Clock-face hour must be an integer")

    @classmethod
    def coerce(cls, value: Any) -> "ClockFacePosition":
        """Return an existing position or parse an integer/text hour, accepting
        C-prefix and :00 suffix. Invalid syntax and non-integer construction raise
        ValueError. Out-of-range integers are retained for validate.
        """

        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)

        text = str(value).strip().upper()
        match = re.fullmatch(r"(?:C)?(-?\d+?)(?::00)?", text)
        if not match:
            raise ValueError(f"Unrecognized clock-face position: {value!r}")
        return cls(int(match.group(1)))

    def to_quadrant(self, laterality: Laterality) -> "Quadrant":
        """Map hour to a new side-specific Quadrant with unknown depth. laterality must
        coerce to LEFT or RIGHT or ValueError is raised. Hours outside 1–12 produce
        unknown axes. Cardinal hours map to central axes.
        """

        side = Laterality.coerce(laterality)
        if side not in {Laterality.LEFT, Laterality.RIGHT}:
            raise ValueError(f"Clock-face mapping requires a breast side: {laterality!r}")

        if not 1 <= self.hour <= 12:
            return Quadrant(laterality=side)
        if self.hour in {6, 12}:
            ml = MedialLateralAxis.CENTRAL
        elif self.hour in {1, 2, 3, 4, 5}:
            ml = (
                MedialLateralAxis.LATERAL
                if side is Laterality.LEFT
                else MedialLateralAxis.MEDIAL
            )
        else:
            ml = (
                MedialLateralAxis.MEDIAL
                if side is Laterality.LEFT
                else MedialLateralAxis.LATERAL
            )

        if self.hour in {3, 9}:
            si = SuperiorInferiorAxis.CENTRAL
        elif self.hour in {10, 11, 12, 1, 2}:
            si = SuperiorInferiorAxis.SUPERIOR
        else:
            si = SuperiorInferiorAxis.INFERIOR

        return Quadrant(laterality=side, ml=ml, si=si)


@dataclass(frozen=True)
class Quadrant:
    """Discrete three-axis anatomical position for a breast side.

    Attributes
    ----------
    laterality : Laterality
        Breast side. Coercible values are normalized; unknown values become
        UNKNOWN where coercion is supported.
    ml : MedialLateralAxis
        Medial/lateral axis category; UNKNOWN when not observed. Default:
        MedialLateralAxis.UNKNOWN.
    si : SuperiorInferiorAxis
        Superior/inferior axis category; UNKNOWN when not observed. Default:
        SuperiorInferiorAxis.UNKNOWN.
    depth : DepthThird
        Anterior/middle/posterior depth third; UNKNOWN when unobserved. Default:
        DepthThird.UNKNOWN.
    """

    laterality: Laterality
    """Breast side. Coercible values are normalized; unknown values become UNKNOWN
    where coercion is supported.
    """
    ml: MedialLateralAxis = MedialLateralAxis.UNKNOWN
    """Medial/lateral axis category; UNKNOWN when not observed. Default:
    MedialLateralAxis.UNKNOWN.
    """
    si: SuperiorInferiorAxis = SuperiorInferiorAxis.UNKNOWN
    """Superior/inferior axis category; UNKNOWN when not observed. Default:
    SuperiorInferiorAxis.UNKNOWN.
    """
    depth: DepthThird = DepthThird.UNKNOWN
    """Anterior/middle/posterior depth third; UNKNOWN when unobserved. Default:
    DepthThird.UNKNOWN.
    """

    def __post_init__(self) -> None:
        side = Laterality.coerce(self.laterality)
        object.__setattr__(self, "laterality", side)

    def merge_missing(self, other: "Quadrant") -> "Quadrant":
        """Return a new quadrant filling only this object's UNKNOWN axes from other.
        Known axes win without conflict detection. Different lateralities raise
        ValueError; neither input is mutated.
        """

        if self.laterality is not other.laterality:
            raise ValueError(
                "Cannot merge anatomical positions from different lateralities"
            )
        return Quadrant(
            laterality=self.laterality,
            ml=self.ml if self.ml is not MedialLateralAxis.UNKNOWN else other.ml,
            si=self.si if self.si is not SuperiorInferiorAxis.UNKNOWN else other.si,
            depth=self.depth if self.depth is not DepthThird.UNKNOWN else other.depth,
        )


@dataclass(frozen=True)
class AnatomicalPosition:
    """Clinical anatomical position with optional named and measured fields.

    Attributes
    ----------
    laterality : Laterality
        Breast side. Coercible values are normalized; unknown values become
        UNKNOWN where coercion is supported.
    quadrant : Quadrant
        Discrete position with matching laterality; a mismatch raises
        ValueError.
    clock_position : Optional[ClockFacePosition]
        Optional reported clock-face location; no value is inferred from
        quadrant. Default: None.
    location_category : Optional[AnatomicalLocationCategory]
        Optional named location such as retroareolar, retained independently of
        quadrant. Default: None.
    distance_from_nipple_cm : Optional[float]
        Reported distance from nipple in centimeters; None means unavailable.
        Default: None.
    """

    laterality: Laterality
    """Breast side. Coercible values are normalized; unknown values become UNKNOWN
    where coercion is supported.
    """
    quadrant: Quadrant
    """Discrete position with matching laterality; a mismatch raises ValueError."""
    clock_position: Optional[ClockFacePosition] = None
    """Optional reported clock-face location; no value is inferred from quadrant.
    Default: None.
    """
    location_category: Optional[AnatomicalLocationCategory] = None
    """Optional named location such as retroareolar, retained independently of
    quadrant. Default: None.
    """
    distance_from_nipple_cm: Optional[float] = None
    """Reported distance from nipple in centimeters; None means unavailable. Default: None."""

    def __post_init__(self) -> None:
        side = Laterality.coerce(self.laterality)
        if side is not self.quadrant.laterality:
            raise ValueError("AnatomicalPosition laterality must match its quadrant")
        object.__setattr__(self, "laterality", side)


@dataclass(frozen=True)
class ContinuousAnatomicalPosition:
    """Continuous anatomical coordinates in a declared breast coordinate frame.

    Attributes
    ----------
    laterality : Laterality
        Breast side. Coercible values are normalized; unknown values become
        UNKNOWN where coercion is supported.
    ml_value : Optional[float]
        Dimensionless medial/lateral coordinate. <= -0.5 maps medial; >= 0.5
        maps lateral; intermediate values map central. None means unobserved.
        Default: None.
    si_value : Optional[float]
        Dimensionless superior/inferior coordinate. <= -0.5 maps inferior; >=
        0.5 maps superior; intermediate values map central. None means
        unobserved. Default: None.
    depth_value : Optional[float]
        Dimensionless nipple-to-posterior coordinate on a nominal 0–2 scale;
        values are not clipped. None means unobserved. Default: None.
    coordinate_frame_id : Optional[str]
        Caller-defined coordinate frame label; None means unspecified. Default:
        None.
    """

    laterality: Laterality
    """Breast side. Coercible values are normalized; unknown values become UNKNOWN
    where coercion is supported.
    """
    ml_value: Optional[float] = None
    """Dimensionless medial/lateral coordinate. <= -0.5 maps medial; >= 0.5 maps
    lateral; intermediate values map central. None means unobserved. Default:
    None.
    """
    si_value: Optional[float] = None
    """Dimensionless superior/inferior coordinate. <= -0.5 maps inferior; >= 0.5
    maps superior; intermediate values map central. None means unobserved.
    Default: None.
    """
    depth_value: Optional[float] = None
    """Dimensionless nipple-to-posterior coordinate on a nominal 0–2 scale; values
    are not clipped. None means unobserved. Default: None.
    """
    coordinate_frame_id: Optional[str] = None
    """Caller-defined coordinate frame label; None means unspecified. Default: None."""

    @property
    def observable_axes(self) -> Tuple[str, ...]:
        """Return non-None axis names in fixed order: ml, si, depth."""

        axes = []
        if self.ml_value is not None:
            axes.append("ml")
        if self.si_value is not None:
            axes.append("si")
        if self.depth_value is not None:
            axes.append("depth")
        return tuple(axes)

    def to_quadrant(self) -> Quadrant:
        """Return a new discrete quadrant. ml/si thresholds are -0.5 and +0.5
        inclusive; depth < 2/3 is anterior, < 4/3 middle, otherwise posterior. None
        maps to UNKNOWN. Values are not clipped or checked for finiteness.
        """

        return Quadrant(
            laterality=Laterality.coerce(self.laterality),
            ml=_quantize_ml(self.ml_value),
            si=_quantize_si(self.si_value),
            depth=_quantize_depth(self.depth_value),
        )


def _quantize_ml(value: Optional[float]) -> MedialLateralAxis:
    if value is None:
        return MedialLateralAxis.UNKNOWN
    if value <= -0.5:
        return MedialLateralAxis.MEDIAL
    if value >= 0.5:
        return MedialLateralAxis.LATERAL
    return MedialLateralAxis.CENTRAL


def _quantize_si(value: Optional[float]) -> SuperiorInferiorAxis:
    if value is None:
        return SuperiorInferiorAxis.UNKNOWN
    if value <= -0.5:
        return SuperiorInferiorAxis.INFERIOR
    if value >= 0.5:
        return SuperiorInferiorAxis.SUPERIOR
    return SuperiorInferiorAxis.CENTRAL


def _quantize_depth(value: Optional[float]) -> DepthThird:
    if value is None:
        return DepthThird.UNKNOWN
    if value < 2 / 3:
        return DepthThird.ANTERIOR
    if value < 4 / 3:
        return DepthThird.MIDDLE
    return DepthThird.POSTERIOR

