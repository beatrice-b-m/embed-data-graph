"""Source-neutral primitive values used across the unified toolkit."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Tuple, Type, TypeVar, Union


_CoercibleEnumT = TypeVar("_CoercibleEnumT", bound="CoercibleEnum")


class CoercibleEnum(Enum):
    """Enum with explicit, non-throwing coercion for source data values."""

    @classmethod
    def coerce(cls: Type[_CoercibleEnumT], value: Any) -> _CoercibleEnumT:
        """Return an existing member, exact enum value, or recognized source alias.
        Missing/unrecognized values become UNKNOWN for concrete package enums. Enum
        subclasses without UNKNOWN may raise ValueError.
        """

        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except (TypeError, ValueError):
            return cls._coerce_unknown(value)

    @classmethod
    def _coerce_unknown(cls: Type[_CoercibleEnumT], value: Any) -> _CoercibleEnumT:
        unknown = getattr(cls, "UNKNOWN", None)
        if unknown is None:
            raise ValueError(f"{value!r} is not a valid {cls.__name__}")
        return unknown


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


class Laterality(CoercibleEnum):
    """Breast side encoded independently of any source table.

    Members
    -------
    LEFT='L', RIGHT='R', BILATERAL='B', UNKNOWN='UNKNOWN'.
    """

    LEFT = "L"
    RIGHT = "R"
    BILATERAL = "B"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _coerce_unknown(cls, value: Any) -> "Laterality":
        aliases = {
            "LEFT": cls.LEFT,
            "LT": cls.LEFT,
            "L": cls.LEFT,
            "RIGHT": cls.RIGHT,
            "RT": cls.RIGHT,
            "R": cls.RIGHT,
            "BILATERAL": cls.BILATERAL,
            "BOTH": cls.BILATERAL,
            "B": cls.BILATERAL,
        }
        return aliases.get(_normalized_text(value), cls.UNKNOWN)

    @property
    def is_unilateral(self) -> bool:
        """True for LEFT and RIGHT only; BILATERAL and UNKNOWN are False."""

        return self in {self.LEFT, self.RIGHT}

    def expand(self) -> Tuple["Laterality", ...]:
        """Return (LEFT, RIGHT) for BILATERAL, (self,) for a unilateral side, or () for
        UNKNOWN. Order is always left then right.
        """

        if self is self.BILATERAL:
            return (self.LEFT, self.RIGHT)
        if self.is_unilateral:
            return (self,)
        return ()


class ViewPosition(CoercibleEnum):
    """Mammography view position.

    Members
    -------
    CC='CC', MLO='MLO', ML='ML', LM='LM', XCCL='XCCL', UNKNOWN='UNKNOWN'.
    """

    CC = "CC"
    MLO = "MLO"
    ML = "ML"
    LM = "LM"
    XCCL = "XCCL"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _coerce_unknown(cls, value: Any) -> "ViewPosition":
        text = _normalized_text(value)
        if not text:
            return cls.UNKNOWN

        match = re.search(r"\b(XCCL|MLO|CC|ML|LM)\b", text)
        if match:
            return cls(match.group(1))
        return cls.UNKNOWN


class ImageModality(CoercibleEnum):
    """Image acquisition or derived-image category.

    Members
    -------
    FFDM='2D', DBT='3D', S2D='S2D', UNKNOWN='UNKNOWN'.
    """

    FFDM = "2D"
    DBT = "3D"
    S2D = "S2D"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _coerce_unknown(cls, value: Any) -> "ImageModality":
        aliases = {
            "2D": cls.FFDM,
            "FFDM": cls.FFDM,
            "DM": cls.FFDM,
            "MAMMOGRAPHY": cls.FFDM,
            "3D": cls.DBT,
            "DBT": cls.DBT,
            "TOMO": cls.DBT,
            "TOMOSYNTHESIS": cls.DBT,
            "S2D": cls.S2D,
            "CVIEW": cls.S2D,
            "C-VIEW": cls.S2D,
            "SYNTHETIC 2D": cls.S2D,
        }
        return aliases.get(_normalized_text(value), cls.UNKNOWN)


class OrientationDirection(CoercibleEnum):
    """DICOM patient orientation direction component.

    Members
    -------
    P='P', A='A', L='L', R='R', HL='HL', HR='HR', FL='FL', FR='FR', H='H',
    F='F', UNKNOWN='UNKNOWN'.
    """

    P = "P"
    A = "A"
    L = "L"
    R = "R"
    HL = "HL"
    HR = "HR"
    FL = "FL"
    FR = "FR"
    H = "H"
    F = "F"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _coerce_unknown(cls, value: Any) -> "OrientationDirection":
        text = _normalized_text(value)
        if text in cls.__members__:
            return cls[text]
        return cls.UNKNOWN


@dataclass(frozen=True)
class PatientOrientation:
    """Two-component DICOM patient orientation.

    Attributes
    ----------
    row : OrientationDirection
        DICOM row direction (direction along a displayed row).
    column : OrientationDirection
        DICOM column direction (direction along a displayed column).
    """

    row: OrientationDirection
    """DICOM row direction (direction along a displayed row)."""
    column: OrientationDirection
    """DICOM column direction (direction along a displayed column)."""

    @classmethod
    def coerce(
        cls,
        value: Union[
            "PatientOrientation",
            str,
            Iterable[Union[str, OrientationDirection]],
        ],
    ) -> "PatientOrientation":
        """Return orientation from an existing object, two-item iterable, or Python-
        literal string such as "['P', 'L']". Unrecognized components become UNKNOWN.
        Invalid syntax or arity raises ValueError. Existing objects are returned
        unchanged.
        """

        if isinstance(value, PatientOrientation):
            return value
        parsed = cls._parse(value)
        return cls(
            row=OrientationDirection.coerce(parsed[0]),
            column=OrientationDirection.coerce(parsed[1]),
        )

    @classmethod
    def _parse(
        cls,
        value: Union[str, Iterable[Union[str, OrientationDirection]]],
    ) -> Tuple[Union[str, OrientationDirection], Union[str, OrientationDirection]]:
        if isinstance(value, str):
            try:
                value = ast.literal_eval(value)
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f"Invalid patient orientation: {value!r}") from exc

        try:
            parsed = tuple(value)
        except TypeError as exc:
            raise ValueError(f"Invalid patient orientation: {value!r}") from exc

        if len(parsed) != 2:
            raise ValueError(f"Patient orientation requires 2 directions: {value!r}")
        return parsed[0], parsed[1]

    @property
    def exact(self) -> bool:
        """True when neither component is UNKNOWN; does not validate orientation consistency."""

        return (
            self.row is not OrientationDirection.UNKNOWN
            and self.column is not OrientationDirection.UNKNOWN
        )

    def as_tuple(self) -> Tuple[str, str]:
        """Return string-valued (row, column) direction codes, preserving order."""

        return self.row.value, self.column.value


class FovRotation(CoercibleEnum):
    """Field-of-view rotation metadata.

    Members
    -------
    NONE=0.0, FULL=180.0, UNKNOWN='UNKNOWN'.
    """

    NONE = 0.0
    FULL = 180.0
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _coerce_unknown(cls, value: Any) -> "FovRotation":
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return cls.UNKNOWN
        if numeric == 0.0:
            return cls.NONE
        if numeric == 180.0:
            return cls.FULL
        return cls.UNKNOWN


class FovHorizontalFlip(CoercibleEnum):
    """Field-of-view horizontal flip metadata.

    Members
    -------
    YES='YES', NO='NO', UNKNOWN='UNKNOWN'.
    """

    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _coerce_unknown(cls, value: Any) -> "FovHorizontalFlip":
        aliases = {
            "Y": cls.YES,
            "YES": cls.YES,
            "TRUE": cls.YES,
            "1": cls.YES,
            "N": cls.NO,
            "NO": cls.NO,
            "FALSE": cls.NO,
            "0": cls.NO,
        }
        return aliases.get(_normalized_text(value), cls.UNKNOWN)
