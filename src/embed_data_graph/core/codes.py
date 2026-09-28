"""Source codes paired with their human-readable meaning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple, Union


@dataclass(frozen=True, eq=False)
class Code:
    """A source code together with its meaning, when the meaning is known.

    ``code`` is the source code as loaded (trimmed; alphabetic EMBED codes
    uppercased). ``meaning`` is its human-readable meaning, or None when the
    code is unknown or unresolved. A comma-separated code, such as a
    recommendation ``"B,U"``, lists its parts in ``tokens``; its meaning joins
    the meanings of the known parts with ``"; "`` and ``unknown`` lists the
    parts without one.

    Codes compare and hash by the code alone, never by meaning; a
    comma-separated code compares by its set of tokens, because their order
    and repetition carry no meaning. A Code never equals a plain string:
    compare ``.code`` or ``.meaning`` explicitly.

    Attributes
    ----------
    code : str
        Source code, non-empty.
    meaning : str or None, optional
        Human-readable meaning; None when unknown. Default None.
    tokens : tuple of str, optional
        Parts of a comma-separated code; empty for a single code.
    unknown : tuple of str, optional
        Parts, or the whole code, without a known meaning.

    Examples
    --------
    >>> Code("S", "Suspicious").meaning
    'Suspicious'
    >>> Code("S", "Suspicious") == Code("S")
    True
    >>> str(Code("9"))
    '9'
    """

    code: str
    """Source code as loaded."""
    meaning: Optional[str] = None
    """Human-readable meaning; None when unknown."""
    tokens: Tuple[str, ...] = ()
    """Parts of a comma-separated code; empty for a single code."""
    unknown: Tuple[str, ...] = field(default=())
    """Parts, or the whole code, without a known meaning."""

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("code must be a non-empty string")
        object.__setattr__(self, "code", self.code.strip())
        object.__setattr__(self, "tokens", tuple(self.tokens))
        object.__setattr__(self, "unknown", tuple(self.unknown))

    @property
    def _identity(self) -> Union[str, FrozenSet[str]]:
        return frozenset(self.tokens) if self.tokens else self.code

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Code) and self._identity == other._identity

    def __hash__(self) -> int:
        return hash(("Code", self._identity))

    @property
    def is_known(self) -> bool:
        """True when the code, or every part of it, has a known meaning."""

        return self.meaning is not None and not self.unknown

    def __str__(self) -> str:
        return self.meaning if self.meaning is not None else self.code

    @classmethod
    def coerce(cls, value: Any) -> Optional["Code"]:
        """Return ``value`` as a Code: None stays None, text becomes a Code without meaning."""

        if value is None or isinstance(value, Code):
            return value
        return cls(str(value))

    def to_dict(self) -> Dict[str, Any]:
        """Return ``{"code", "meaning"}``, plus ``tokens`` and ``unknown`` when present."""

        data: Dict[str, Any] = {"code": self.code, "meaning": self.meaning}
        if self.tokens:
            data["tokens"] = list(self.tokens)
        if self.unknown:
            data["unknown"] = list(self.unknown)
        return data


@dataclass(frozen=True)
class Vocabulary:
    """A table of code meanings used to decode source codes.

    Attributes
    ----------
    name : str
        Vocabulary name, for diagnostics.
    meanings : mapping of str to str
        Code to meaning. Lookups ignore case and surrounding whitespace.
    delimited : bool, optional
        Whether codes are comma-separated lists of parts. Default False.

    Examples
    --------
    >>> Vocabulary("demo", {"B": "Biopsy", "U": "Ultrasound"}, delimited=True).decode("u, b").meaning
    'Ultrasound; Biopsy'
    """

    name: str
    meanings: Mapping[str, str]
    delimited: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "meanings", {key.strip().upper(): value for key, value in self.meanings.items()})

    def decode(self, value: Optional[str]) -> Optional[Code]:
        """Return the Code for ``value`` with its meaning, or None when ``value`` is None or blank."""

        if value is None or not str(value).strip():
            return None
        text = str(value).strip()
        if not self.delimited:
            meaning = self.meanings.get(text.upper())
            return Code(text, meaning, unknown=() if meaning is not None else (text,))
        tokens = tuple(part.strip() for part in text.split(",") if part.strip())
        if len(tokens) == 1:
            meaning = self.meanings.get(tokens[0].upper())
            return Code(tokens[0], meaning, unknown=() if meaning is not None else tokens)
        known = [self.meanings.get(token.upper()) for token in tokens]
        meanings = [meaning for meaning in known if meaning is not None]
        unknown = tuple(token for token, meaning in zip(tokens, known) if meaning is None)
        return Code(text, "; ".join(meanings) if meanings else None, tokens, unknown)
