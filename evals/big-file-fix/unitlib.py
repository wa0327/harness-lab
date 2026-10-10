"""unitlib -- physical quantities, unit conversion and quantity parsing.

``unitlib`` is a dependency-free (standard library only) toolkit for programs
that need to read, convert, compare and print measured values: recipe and
lab-notebook tools, engineering calculators, data cleaning pipelines and the
like.

The main pieces are:

* :class:`Dimension` -- exponent vectors over the base dimensions (length,
  mass, time, ...) with the usual algebra.
* :class:`Prefix` -- SI and IEC binary prefixes, plus helpers for picking a
  prefix that keeps a number readable.
* :class:`Unit` -- a named or composite unit: a scale factor relative to the
  coherent SI unit of its dimension, and an optional offset for scales such
  as degrees Celsius.
* :class:`UnitRegistry` -- the catalogue of known units.  It resolves symbols,
  names, plurals, aliases and prefixed forms, and parses unit expressions such
  as ``"kg·m²/s²"`` or ``"J/(kg*K)"``.
* :class:`Quantity` -- a magnitude with a unit, supporting arithmetic,
  comparison and conversion.
* Parsing helpers (:func:`parse_number`, :func:`parse_quantity`,
  :func:`parse_range`, :func:`parse_measurement`) that accept the formats people
  actually write: ``"1,250.5 kg"``, ``"3½ cups"``, ``"5 ft 3 in"``,
  ``"5'3\\""``, ``"20–25 °C"``, ``"9.81 ± 0.02 m/s^2"``.
* Formatting helpers (:func:`format_number`, :func:`format_quantity`,
  :func:`format_compound`, :func:`format_duration`) and plain-text tables
  (:func:`render_table`, :func:`conversion_table`).

Quick tour::

    >>> Quantity(5, "km").to("mi")
    <Quantity(3.10685596119, 'mi')>
    >>> parse_quantity("3 ft 4 in").to("cm")
    <Quantity(101.6, 'cm')>
    >>> format_quantity(Quantity(0.000047, "F"), auto_prefix=True)
    '47 µF'

Conventions
-----------
Every unit is stored as ``factor`` (and ``offset``) relative to the coherent
SI unit of its dimension, so converting between two ordinary units of the
same dimension is ``value * src.factor / dst.factor``.  Units with an offset
(``°C``, ``°F``) are only allowed on their own; to combine temperatures with
other units use the corresponding difference units (``delta_degC``,
``delta_degF``), as in ``"W/(m^2*delta_degC)"``.

Angles are treated as dimensionless (radian = 1), following SI.  Information
(bits) is a separate base dimension so that data sizes do not silently mix
with plain counts.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from functools import total_ordering
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

__version__ = "2.4.1"

__all__ = [
    # errors
    "UnitError",
    "UnknownUnitError",
    "DimensionalityError",
    "ParseError",
    "OffsetUnitError",
    # numbers
    "isclose",
    "clean_float",
    "round_sig",
    "round_half_up",
    "format_number",
    "format_engineering",
    "parse_number",
    "VULGAR_FRACTIONS",
    # dimensions and prefixes
    "BASE_DIMENSIONS",
    "Dimension",
    "DIMENSIONLESS",
    "named_dimension",
    "Prefix",
    "SI_PREFIXES",
    "BINARY_PREFIXES",
    "NO_PREFIX",
    "best_prefix",
    # units
    "Unit",
    "UnitRegistry",
    "DEFAULT_DEFINITIONS",
    "get_registry",
    "set_registry",
    "parse_unit",
    # quantities
    "Quantity",
    "Measurement",
    "convert",
    "convert_value",
    "parse_quantity",
    "parse_range",
    "parse_measurement",
    # formatting
    "format_quantity",
    "format_compound",
    "format_duration",
    "render_table",
    "conversion_table",
    "UNIT_SYSTEMS",
    "to_system",
    "humanize",
]

Number = Union[int, float, Fraction]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class UnitError(Exception):
    """Base class for every error raised by unitlib."""


class UnknownUnitError(UnitError, LookupError):
    """A unit symbol or name could not be resolved by the registry."""

    def __init__(self, name: str, suggestions: Sequence[str] = ()):
        self.name = name
        self.suggestions = tuple(suggestions)
        message = f"unknown unit {name!r}"
        if self.suggestions:
            message += " (did you mean " + ", ".join(repr(s) for s in self.suggestions) + "?)"
        super().__init__(message)

    def __str__(self) -> str:  # LookupError would otherwise repr() the message
        return self.args[0]


class DimensionalityError(UnitError, TypeError):
    """Two units or quantities have incompatible dimensions."""

    def __init__(self, first: Any, second: Any = None, *, operation: str = "convert"):
        self.first = first
        self.second = second
        self.operation = operation
        if second is None:
            message = str(first)
        else:
            message = (
                f"cannot {operation} {_describe_operand(first)} "
                f"and {_describe_operand(second)}"
            )
        super().__init__(message)


class ParseError(UnitError, ValueError):
    """Text could not be parsed as a number, unit or quantity.

    When the position of the problem is known the message includes the
    offending text with a caret underneath, like a compiler diagnostic.
    """

    def __init__(self, message: str, text: str = "", position: Optional[int] = None):
        self.text = text
        self.position = position
        self.reason = message
        if text and position is not None:
            message = f"{message}\n    {text}\n    {' ' * position}^"
        elif text:
            message = f"{message}: {text!r}"
        super().__init__(message)


class OffsetUnitError(UnitError, TypeError):
    """The operation is ambiguous for a unit with an offset (e.g. °C)."""


def _describe_operand(obj: Any) -> str:
    dimension = getattr(obj, "dimension", None)
    if dimension is None:
        return repr(obj)
    return f"{obj} [{dimension.describe()}]"


# ---------------------------------------------------------------------------
# Number helpers
# ---------------------------------------------------------------------------

_REL_TOL = 1e-9
_ABS_TOL = 1e-12


def isclose(a: float, b: float, rel_tol: float = _REL_TOL, abs_tol: float = _ABS_TOL) -> bool:
    """``math.isclose`` with tolerances suited to unit conversion results."""
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def clean_float(x: float, digits: int = 12) -> float:
    """Remove binary floating point noise from a conversion result.

    >>> clean_float(0.1 + 0.2)
    0.3
    >>> clean_float(1.8796 / 0.0254)
    74.0
    """
    x = float(x)
    if x == 0 or not math.isfinite(x):
        return x
    return float(f"{x:.{digits}g}")


def round_sig(x: float, sig: int = 3) -> float:
    """Round *x* to *sig* significant figures.

    >>> round_sig(123456, 2)
    120000.0
    >>> round_sig(0.0012345, 3)
    0.00123
    >>> round_sig(-987.65, 1)
    -1000.0
    """
    if sig < 1:
        raise ValueError(f"sig must be at least 1, got {sig}")
    x = float(x)
    if x == 0 or not math.isfinite(x):
        return x
    digits = sig - math.floor(math.log10(abs(x)))
    return round(x, digits)


def round_half_up(x: float, ndigits: int = 0) -> float:
    """Round half away from zero, the way most people round by hand.

    Python's :func:`round` uses banker's rounding on the binary value, so
    ``round(2.5) == 2`` and ``round(0.125, 2) == 0.12``.  This helper works on
    the shortest decimal representation instead:

    >>> round_half_up(2.5)
    3.0
    >>> round_half_up(-0.125, 2)
    -0.13
    """
    x = float(x)
    if not math.isfinite(x):
        return x
    quantum = Decimal(1).scaleb(-ndigits)
    return float(Decimal(repr(x)).quantize(quantum, rounding=ROUND_HALF_UP))


def _places_for_sig(x: float, sig: int) -> int:
    """Number of decimal places needed to show *sig* significant figures of *x*."""
    if x == 0:
        return max(sig - 1, 0)
    return max(0, sig - 1 - math.floor(math.log10(abs(x))))


def _plain(x: Number) -> str:
    """Shortest natural rendering of a number, without exponent where sensible."""
    if isinstance(x, bool):
        x = int(x)
    if isinstance(x, int):
        return str(x)
    if isinstance(x, Fraction):
        if x.denominator == 1:
            return str(x.numerator)
        x = float(x)
    if not math.isfinite(x):
        return "nan" if math.isnan(x) else ("inf" if x > 0 else "-inf")
    text = f"{clean_float(x):.12g}"
    if "e" in text and 1e-7 <= abs(x) < 1e16:
        text = format(Decimal(text), "f")
    if "." in text and "e" not in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _group_thousands(text: str, separator: str) -> str:
    sign = ""
    if text[:1] in "+-":
        sign, text = text[0], text[1:]
    integer, dot, fraction = text.partition(".")
    if not integer.isdigit():
        return sign + text
    groups = []
    while len(integer) > 3:
        groups.append(integer[-3:])
        integer = integer[:-3]
    groups.append(integer)
    return sign + separator.join(reversed(groups)) + dot + fraction


def format_number(
    x: Number,
    decimals: Optional[int] = None,
    sig: Optional[int] = None,
    *,
    thousands: str = "",
    decimal_point: str = ".",
    strip_zeros: bool = False,
    plus: bool = False,
    half_up: bool = False,
) -> str:
    """Format a number for display.

    Exactly one of *decimals* (fixed decimal places) or *sig* (significant
    figures) may be given; with neither the shortest natural form is used.

    >>> format_number(1234.5678, 2, thousands=",")
    '1,234.57'
    >>> format_number(0.000123456, sig=3)
    '0.000123'
    >>> format_number(2.50, 2, strip_zeros=True)
    '2.5'
    """
    if decimals is not None and sig is not None:
        raise ValueError("give either decimals or sig, not both")
    if isinstance(x, Fraction):
        x = float(x)
    if isinstance(x, float) and not math.isfinite(x):
        return _plain(x)
    if sig is not None:
        rounded = round_sig(x, sig)
        text = f"{rounded:.{_places_for_sig(rounded, sig)}f}"
    elif decimals is not None:
        if decimals < 0:
            raise ValueError("decimals must not be negative")
        value = round_half_up(x, decimals) if half_up else x
        text = f"{value:.{decimals}f}"
    else:
        text = _plain(x)
    if strip_zeros and "." in text:
        text = text.rstrip("0").rstrip(".")
    if text.startswith("-") and not text.strip("-0."):
        text = text[1:]  # "-0.00" -> "0.00"
    if thousands:
        text = _group_thousands(text, thousands)
    if decimal_point != ".":
        text = text.replace(".", decimal_point)
    if plus and not text.startswith("-"):
        text = "+" + text
    return text


_SUPERSCRIPT_TO_ASCII = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_ASCII_TO_SUPERSCRIPT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
_SUPERSCRIPT_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def superscript(n: Union[int, Fraction]) -> str:
    """Render an exponent with Unicode superscripts: ``-2`` -> ``⁻²``."""
    if isinstance(n, Fraction) and n.denominator != 1:
        return "^(" + str(n) + ")"
    return str(int(n)).translate(_ASCII_TO_SUPERSCRIPT)


def format_engineering(x: float, sig: int = 4, *, unicode: bool = False) -> str:
    """Format *x* in engineering notation (exponent a multiple of three).

    >>> format_engineering(47000)
    '47e3'
    >>> format_engineering(0.00012345, 3)
    '123e-6'
    >>> format_engineering(1500, unicode=True)
    '1.5×10³'
    """
    x = float(x)
    if x == 0:
        return "0"
    if not math.isfinite(x):
        return _plain(x)
    exponent = 3 * math.floor(math.log10(abs(x)) / 3)
    mantissa = round_sig(x / 10.0 ** exponent, sig)
    if abs(mantissa) >= 1000:
        mantissa /= 1000
        exponent += 3
    text = _plain(mantissa)
    if exponent == 0:
        return text
    if unicode:
        return f"{text}×10{superscript(exponent)}"
    return f"{text}e{exponent}"


# Parsing --------------------------------------------------------------------

VULGAR_FRACTIONS: Dict[str, Fraction] = {
    "½": Fraction(1, 2),
    "⅓": Fraction(1, 3),
    "⅔": Fraction(2, 3),
    "¼": Fraction(1, 4),
    "¾": Fraction(3, 4),
    "⅕": Fraction(1, 5),
    "⅖": Fraction(2, 5),
    "⅗": Fraction(3, 5),
    "⅘": Fraction(4, 5),
    "⅙": Fraction(1, 6),
    "⅚": Fraction(5, 6),
    "⅐": Fraction(1, 7),
    "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8),
    "⅝": Fraction(5, 8),
    "⅞": Fraction(7, 8),
    "⅑": Fraction(1, 9),
    "⅒": Fraction(1, 10),
}

_VULGAR_CLASS = "".join(VULGAR_FRACTIONS)

# Characters people use for a minus sign.  The en dash is deliberately not in
# the list: "5–10" is a range, not "5" followed by "-10".
_MINUS_SIGNS = "-\u2212\ufe63\uff0d"

_FRACTION_RE = re.compile(r"(?:(?P<whole>\d+)[ \t]+)?(?P<num>\d+)[ \t]*[/\u2044][ \t]*(?P<den>\d+)")

_GROUP_SEPARATORS = ",_'\u00a0\u202f "

_DECIMAL_RE = re.compile(
    r"(?P<int>\d{1,3}(?:(?P<sep>[,_'\u00a0\u202f ])\d{3})(?:(?P=sep)\d{3})*|\d*)"
    r"(?:\.(?P<frac>\d*))?"
    r"(?:[eE](?P<exp>[-+]?\d+))?"
)

_SCIENTIFIC_RE = re.compile(
    r"(?:(?P<mant>[\d.,_'\u00a0\u202f]+)[ \t]*[×x·*][ \t]*)?"
    r"10[ \t]*(?:(?:\^|\*\*)[ \t]*(?P<exp>[-+]?\d+)|(?P<sup>[⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+))"
)


def _normalise_minus(text: str) -> str:
    for ch in _MINUS_SIGNS[1:]:
        text = text.replace(ch, "-")
    return text


def _parse_decimal(text: str, original: str, decimal_point: str = ".") -> float:
    if decimal_point != ".":
        if decimal_point not in ",'":
            raise ValueError(f"unsupported decimal point {decimal_point!r}")
        text = text.replace(".", "\0").replace(decimal_point, ".").replace("\0", ",")
    m = _DECIMAL_RE.fullmatch(text)
    if not m or not (m.group("int") or m.group("frac")):
        raise ParseError("not a number", original)
    digits = m.group("int")
    if m.group("sep"):
        digits = digits.replace(m.group("sep"), "")
    literal = (digits or "0") + "." + (m.group("frac") or "0")
    if m.group("exp"):
        literal += "e" + m.group("exp")
    return float(literal)


def _mixed_value(sign: int, whole: int, frac: Fraction) -> float:
    """Value of a (possibly mixed) fraction such as ``2 1/4`` or ``-¾``."""
    return float(sign * whole + frac)


def parse_number(text: str, *, decimal_point: str = ".") -> float:
    """Parse a number the way people write it.

    Accepted forms, each with an optional leading sign (``-``, ``+`` or the
    Unicode minus sign ``−``):

    * integers and decimals: ``"42"``, ``"0.5"``, ``".75"``, ``"1,234,567.89"``,
      ``"1_000"``, ``"12 345.6"`` (thin or no-break space grouping)
    * scientific notation: ``"6.022e23"``, ``"1.5E-3"``, ``"1.5×10^3"``,
      ``"2.5·10⁻⁴"``, ``"10^6"``
    * fractions: ``"3/4"``, ``"½"``, ``"1 1/2"``, ``"1½"``, ``"2 ¾"``

    With ``decimal_point=","`` the roles of comma and period are swapped, so
    ``"1.234,5"`` is 1234.5.

    >>> parse_number("1,250.5")
    1250.5
    >>> parse_number("2½")
    2.5
    >>> parse_number("−3.2e-2")
    -0.032
    """
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    s = _normalise_minus(text.strip())
    if not s:
        raise ParseError("empty number", text)
    sign = 1
    if s[0] in "+-":
        sign = -1 if s[0] == "-" else 1
        s = s[1:].lstrip()
        if not s:
            raise ParseError("sign without digits", text)
    # "½", "3½", "3 ½"
    if s[-1] in VULGAR_FRACTIONS:
        whole_text = s[:-1].strip()
        if whole_text and not whole_text.isdigit():
            raise ParseError("malformed mixed number", text)
        return _mixed_value(sign, int(whole_text or 0), VULGAR_FRACTIONS[s[-1]])
    # "3/4", "1 1/2"
    m = _FRACTION_RE.fullmatch(s)
    if m:
        numerator, denominator = int(m.group("num")), int(m.group("den"))
        if denominator == 0:
            raise ParseError("zero denominator in fraction", text)
        return _mixed_value(sign, int(m.group("whole") or 0), Fraction(numerator, denominator))
    # "1.5×10^3", "10⁻⁶"
    m = _SCIENTIFIC_RE.fullmatch(s)
    if m:
        mantissa = _parse_decimal(m.group("mant"), text, decimal_point) if m.group("mant") else 1.0
        exponent_text = m.group("exp") or m.group("sup").translate(_SUPERSCRIPT_TO_ASCII)
        return sign * mantissa * 10.0 ** int(exponent_text)
    return sign * _parse_decimal(s, text, decimal_point)


def try_parse_number(text: str, default: Optional[float] = None, **kwargs: Any) -> Optional[float]:
    """Like :func:`parse_number` but return *default* instead of raising."""
    try:
        return parse_number(text, **kwargs)
    except (ParseError, TypeError):
        return default


def as_fraction(x: float, max_denominator: int = 16) -> str:
    """Render *x* as a (mixed) fraction with a small denominator.

    Useful for cooking and woodworking output, where ``0.375`` reads better
    as ``3/8``:

    >>> as_fraction(2.75)
    '2 3/4'
    >>> as_fraction(-0.125)
    '-1/8'
    >>> as_fraction(1.0)
    '1'
    """
    frac = Fraction(x).limit_denominator(max_denominator)
    sign = "-" if frac < 0 else ""
    frac = abs(frac)
    whole, rest = divmod(frac.numerator, frac.denominator)
    if rest == 0:
        return f"{sign}{whole}"
    if whole == 0:
        return f"{sign}{rest}/{frac.denominator}"
    return f"{sign}{whole} {rest}/{frac.denominator}"


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

#: Names of the base dimensions, in the order used by :attr:`Dimension.exponents`.
BASE_DIMENSIONS: Tuple[str, ...] = (
    "length",
    "mass",
    "time",
    "current",
    "temperature",
    "substance",
    "luminosity",
    "information",
)

#: Conventional one-letter symbols of the base dimensions (ISO 80000-1 where
#: one exists; ``B`` for information).
DIMENSION_SYMBOLS: Tuple[str, ...] = ("L", "M", "T", "I", "Θ", "N", "J", "B")

_SYMBOL_INDEX = {sym: i for i, sym in enumerate(DIMENSION_SYMBOLS)}
_SYMBOL_INDEX["Q"] = _SYMBOL_INDEX["Θ"]  # ASCII stand-in for theta
_NAME_INDEX = {name: i for i, name in enumerate(BASE_DIMENSIONS)}

_DIM_TERM_RE = re.compile(
    r"(?P<sym>\[[a-z ]+\]|[A-Za-zΘ]+)"
    r"(?:\s*(?:\^|\*\*)\s*\(?(?P<exp>[-+]?\d+)\)?|(?P<sup>[⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+))?"
)


@dataclass(frozen=True)
class Dimension:
    """Exponents of the base dimensions, e.g. velocity is ``L·T⁻¹``.

    Dimensions are immutable and hashable, and support ``*``, ``/`` and
    ``**`` with the obvious meaning:

    >>> force = Dimension.parse("M L T^-2")
    >>> (force * Dimension.parse("L")).name
    'energy'
    >>> str(force / Dimension.parse("L^2"))
    'L⁻¹·M·T⁻²'
    """

    exponents: Tuple[int, ...] = (0,) * len(BASE_DIMENSIONS)

    def __post_init__(self) -> None:
        if len(self.exponents) != len(BASE_DIMENSIONS):
            raise ValueError(
                f"expected {len(BASE_DIMENSIONS)} exponents, got {len(self.exponents)}"
            )
        cleaned = []
        for e in self.exponents:
            if isinstance(e, float) and not e.is_integer():
                raise ValueError(f"dimension exponents must be integers, got {e!r}")
            cleaned.append(int(e))
        object.__setattr__(self, "exponents", tuple(cleaned))

    # Construction ---------------------------------------------------------

    @classmethod
    def base(cls, name: str) -> "Dimension":
        """The dimension of a single base quantity, by name or symbol."""
        index = _NAME_INDEX.get(name.strip("[] "))
        if index is None:
            index = _SYMBOL_INDEX.get(name)
        if index is None:
            raise ValueError(f"unknown base dimension {name!r}")
        exps = [0] * len(BASE_DIMENSIONS)
        exps[index] = 1
        return cls(tuple(exps))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, int]) -> "Dimension":
        """Build a dimension from ``{"length": 1, "time": -1}``-style mappings.

        Keys may be base dimension names or their symbols.
        """
        exps = [0] * len(BASE_DIMENSIONS)
        for key, value in mapping.items():
            index = _NAME_INDEX.get(key, _SYMBOL_INDEX.get(key))
            if index is None:
                raise ValueError(f"unknown base dimension {key!r}")
            exps[index] += int(value)
        return cls(tuple(exps))

    @classmethod
    def parse(cls, text: str) -> "Dimension":
        """Parse a dimension written with symbols or bracketed names.

        Terms are separated by whitespace, ``*`` or ``·``; a single ``/``
        makes every following term negative.  Exponents may be written
        ``^-2``, ``**2`` or with superscripts.

        >>> Dimension.parse("L·T⁻²") == Dimension.parse("[length]/[time]^2")
        True
        >>> Dimension.parse("1").dimensionless
        True
        """
        text = text.strip()
        if text in ("", "1", "[]", "[dimensionless]"):
            return DIMENSIONLESS
        result = DIMENSIONLESS
        sign = 1
        pos = 0
        while pos < len(text):
            ch = text[pos]
            if ch in " \t*·":
                pos += 1
                continue
            if ch == "/":
                if sign < 0:
                    raise ValueError(f"more than one '/' in dimension {text!r}")
                sign = -1
                pos += 1
                continue
            m = _DIM_TERM_RE.match(text, pos)
            if not m:
                raise ValueError(f"cannot parse dimension {text!r} at position {pos}")
            exponent = 1
            if m.group("exp"):
                exponent = int(m.group("exp"))
            elif m.group("sup"):
                exponent = int(m.group("sup").translate(_SUPERSCRIPT_TO_ASCII))
            result = result * cls.base(m.group("sym")) ** (sign * exponent)
            pos = m.end()
        return result

    # Algebra --------------------------------------------------------------

    def __mul__(self, other: "Dimension") -> "Dimension":
        if not isinstance(other, Dimension):
            return NotImplemented
        return Dimension(tuple(a + b for a, b in zip(self.exponents, other.exponents)))

    def __truediv__(self, other: "Dimension") -> "Dimension":
        if not isinstance(other, Dimension):
            return NotImplemented
        return Dimension(tuple(a - b for a, b in zip(self.exponents, other.exponents)))

    def __pow__(self, power: Union[int, Fraction]) -> "Dimension":
        if isinstance(power, Fraction) and power.denominator != 1:
            return self.root(power.denominator) ** power.numerator
        if isinstance(power, float):
            if not power.is_integer():
                return self ** Fraction(power).limit_denominator(12)
            power = int(power)
        return Dimension(tuple(e * int(power) for e in self.exponents))

    def root(self, n: int) -> "Dimension":
        """The *n*-th root; every exponent must be divisible by *n*."""
        if n <= 0:
            raise ValueError("root must be positive")
        if any(e % n for e in self.exponents):
            raise DimensionalityError(f"cannot take root {n} of dimension {self}")
        return Dimension(tuple(e // n for e in self.exponents))

    def inverse(self) -> "Dimension":
        return Dimension(tuple(-e for e in self.exponents))

    # Inspection -----------------------------------------------------------

    @property
    def dimensionless(self) -> bool:
        return not any(self.exponents)

    def as_dict(self) -> Dict[str, int]:
        """Non-zero exponents keyed by base dimension name."""
        return {name: e for name, e in zip(BASE_DIMENSIONS, self.exponents) if e}

    @property
    def name(self) -> Optional[str]:
        """Conventional name of the dimension (``"force"``), if it has one."""
        return _NAME_BY_DIMENSION.get(self)

    def describe(self) -> str:
        """The conventional name if there is one, otherwise the symbolic form."""
        return self.name or str(self)

    def __str__(self) -> str:
        if self.dimensionless:
            return "1"
        parts = []
        for symbol, e in zip(DIMENSION_SYMBOLS, self.exponents):
            if e == 0:
                continue
            parts.append(symbol if e == 1 else symbol + superscript(e))
        return "·".join(parts)

    def __repr__(self) -> str:
        return f"Dimension({str(self)!r})"


DIMENSIONLESS = Dimension()

_NAMED_DIMENSIONS_SPEC: Tuple[Tuple[str, str], ...] = (
    ("dimensionless", "1"),
    # base
    ("length", "L"),
    ("mass", "M"),
    ("time", "T"),
    ("current", "I"),
    ("temperature", "Θ"),
    ("substance", "N"),
    ("luminosity", "J"),
    ("information", "B"),
    # mechanics
    ("area", "L^2"),
    ("volume", "L^3"),
    ("frequency", "T^-1"),
    ("velocity", "L T^-1"),
    ("acceleration", "L T^-2"),
    ("jerk", "L T^-3"),
    ("force", "M L T^-2"),
    ("energy", "M L^2 T^-2"),
    ("power", "M L^2 T^-3"),
    ("pressure", "M L^-1 T^-2"),
    ("momentum", "M L T^-1"),
    ("angular momentum", "M L^2 T^-1"),
    ("density", "M L^-3"),
    ("linear density", "M L^-1"),
    ("area density", "M L^-2"),
    ("specific volume", "L^3 M^-1"),
    ("dynamic viscosity", "M L^-1 T^-1"),
    ("kinematic viscosity", "L^2 T^-1"),
    ("volumetric flow", "L^3 T^-1"),
    ("mass flow", "M T^-1"),
    ("specific energy", "L^2 T^-2"),
    ("wavenumber", "L^-1"),
    ("fuel economy", "L^-2"),
    ("irradiance", "M T^-3"),
    # electromagnetism
    ("charge", "I T"),
    ("voltage", "M L^2 T^-3 I^-1"),
    ("resistance", "M L^2 T^-3 I^-2"),
    ("conductance", "M^-1 L^-2 T^3 I^2"),
    ("capacitance", "M^-1 L^-2 T^4 I^2"),
    ("inductance", "M L^2 T^-2 I^-2"),
    ("magnetic flux", "M L^2 T^-2 I^-1"),
    ("magnetic flux density", "M T^-2 I^-1"),
    ("electric field", "M L T^-3 I^-1"),
    # thermal
    ("heat capacity", "M L^2 T^-2 Θ^-1"),
    ("specific heat capacity", "L^2 T^-2 Θ^-1"),
    ("thermal conductivity", "M L T^-3 Θ^-1"),
    ("heat transfer coefficient", "M T^-3 Θ^-1"),
    # chemistry, photometry, data
    ("concentration", "N L^-3"),
    ("molar mass", "M N^-1"),
    ("catalytic activity", "N T^-1"),
    ("illuminance", "J L^-2"),
    ("data rate", "B T^-1"),
)

#: Conventional dimension names, e.g. ``NAMED_DIMENSIONS["force"]``.
NAMED_DIMENSIONS: Dict[str, Dimension] = {
    name: Dimension.parse(spec) for name, spec in _NAMED_DIMENSIONS_SPEC
}

_NAME_BY_DIMENSION: Dict[Dimension, str] = {}
for _name, _dim in NAMED_DIMENSIONS.items():
    _NAME_BY_DIMENSION.setdefault(_dim, _name)
del _name, _dim


def named_dimension(name: str) -> Dimension:
    """Look up a dimension by its conventional name (``"pressure"``)."""
    key = name.strip().lower().replace("_", " ")
    try:
        return NAMED_DIMENSIONS[key]
    except KeyError:
        close = difflib.get_close_matches(key, NAMED_DIMENSIONS, n=3, cutoff=0.7)
        hint = f" (did you mean {', '.join(close)}?)" if close else ""
        raise ValueError(f"unknown dimension name {name!r}{hint}") from None


# ---------------------------------------------------------------------------
# Prefixes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Prefix:
    """A unit prefix such as kilo (``k``, 10³) or kibi (``Ki``, 2¹⁰)."""

    symbol: str
    name: str
    factor: float
    binary: bool = False

    @property
    def exponent(self) -> int:
        """Power of 10 (or of 2 for binary prefixes) represented by the prefix."""
        if self.factor == 1:
            return 0
        if self.binary:
            return round(math.log2(self.factor))
        return round(math.log10(self.factor))

    def __str__(self) -> str:
        return self.symbol

    def __bool__(self) -> bool:
        return bool(self.symbol)


NO_PREFIX = Prefix("", "", 1.0)

#: SI prefixes from quetta (10³⁰) down to quecto (10⁻³⁰), largest first.
SI_PREFIXES: Tuple[Prefix, ...] = (
    Prefix("Q", "quetta", 1e30),
    Prefix("R", "ronna", 1e27),
    Prefix("Y", "yotta", 1e24),
    Prefix("Z", "zetta", 1e21),
    Prefix("E", "exa", 1e18),
    Prefix("P", "peta", 1e15),
    Prefix("T", "tera", 1e12),
    Prefix("G", "giga", 1e9),
    Prefix("M", "mega", 1e6),
    Prefix("k", "kilo", 1e3),
    Prefix("h", "hecto", 1e2),
    Prefix("da", "deca", 1e1),
    Prefix("d", "deci", 1e-1),
    Prefix("c", "centi", 1e-2),
    Prefix("m", "milli", 1e-3),
    Prefix("µ", "micro", 1e-6),
    Prefix("n", "nano", 1e-9),
    Prefix("p", "pico", 1e-12),
    Prefix("f", "femto", 1e-15),
    Prefix("a", "atto", 1e-18),
    Prefix("z", "zepto", 1e-21),
    Prefix("y", "yocto", 1e-24),
    Prefix("r", "ronto", 1e-27),
    Prefix("q", "quecto", 1e-30),
)

#: IEC binary prefixes, largest first.
BINARY_PREFIXES: Tuple[Prefix, ...] = (
    Prefix("Yi", "yobi", 2.0 ** 80, True),
    Prefix("Zi", "zebi", 2.0 ** 70, True),
    Prefix("Ei", "exbi", 2.0 ** 60, True),
    Prefix("Pi", "pebi", 2.0 ** 50, True),
    Prefix("Ti", "tebi", 2.0 ** 40, True),
    Prefix("Gi", "gibi", 2.0 ** 30, True),
    Prefix("Mi", "mebi", 2.0 ** 20, True),
    Prefix("Ki", "kibi", 2.0 ** 10, True),
)

# Alternative spellings accepted on input.  "u" is the traditional ASCII
# stand-in for micro; U+03BC GREEK SMALL LETTER MU is what most keyboards
# produce, while SI_PREFIXES uses U+00B5 MICRO SIGN.
_PREFIX_SYMBOL_ALIASES = {"u": "µ", "\u03bc": "µ"}
_PREFIX_NAME_ALIASES = {"deka": "deca"}

_PREFIX_BY_SYMBOL: Dict[str, Prefix] = {p.symbol: p for p in SI_PREFIXES + BINARY_PREFIXES}
_PREFIX_BY_NAME: Dict[str, Prefix] = {p.name: p for p in SI_PREFIXES + BINARY_PREFIXES}
for _alias, _target in _PREFIX_SYMBOL_ALIASES.items():
    _PREFIX_BY_SYMBOL[_alias] = _PREFIX_BY_SYMBOL[_target]
for _alias, _target in _PREFIX_NAME_ALIASES.items():
    _PREFIX_BY_NAME[_alias] = _PREFIX_BY_NAME[_target]
del _alias, _target

# Longest first, so that "da" is tried before "d" and "Ki" before "K".
_PREFIX_SYMBOLS_BY_LENGTH = sorted(_PREFIX_BY_SYMBOL, key=len, reverse=True)
_PREFIX_NAMES_BY_LENGTH = sorted(_PREFIX_BY_NAME, key=len, reverse=True)


def prefix_by_symbol(symbol: str) -> Optional[Prefix]:
    """The prefix with the given symbol (``"k"``, ``"Mi"``, ``"u"``), or ``None``."""
    return _PREFIX_BY_SYMBOL.get(symbol)


def prefix_by_name(name: str) -> Optional[Prefix]:
    """The prefix with the given name (``"kilo"``, ``"mebi"``), or ``None``."""
    return _PREFIX_BY_NAME.get(name.lower())


def split_prefix_symbol(text: str) -> Iterator[Tuple[Prefix, str]]:
    """Yield every ``(prefix, rest)`` split of *text* on a prefix symbol.

    Longer prefixes are yielded first; the caller decides which split names
    a real unit.  ``rest`` is never empty.
    """
    for symbol in _PREFIX_SYMBOLS_BY_LENGTH:
        if len(text) > len(symbol) and text.startswith(symbol):
            yield _PREFIX_BY_SYMBOL[symbol], text[len(symbol):]


def split_prefix_name(text: str) -> Iterator[Tuple[Prefix, str]]:
    """Like :func:`split_prefix_symbol` for spelled-out names (``"kilometre"``)."""
    lowered = text.lower()
    for name in _PREFIX_NAMES_BY_LENGTH:
        if len(lowered) > len(name) and lowered.startswith(name):
            yield _PREFIX_BY_NAME[name], text[len(name):]


# Ladders used to pick a readable prefix, largest first.  Only the
# engineering prefixes (powers of 10³) take part for decimal units; hecto,
# deca, deci and centi are legal but unusual in automatically formatted output.
_ENGINEERING_LADDER: Tuple[Prefix, ...] = tuple(
    sorted(
        [p for p in SI_PREFIXES if p.exponent % 3 == 0] + [NO_PREFIX],
        key=lambda p: p.factor,
        reverse=True,
    )
)
_BINARY_LADDER: Tuple[Prefix, ...] = BINARY_PREFIXES + (NO_PREFIX,)


def best_prefix(
    value: float,
    *,
    binary: bool = False,
    allowed: Optional[Iterable[Union[str, Prefix]]] = None,
) -> Prefix:
    """Choose the prefix that keeps the mantissa of *value* readable.

    For decimal prefixes the mantissa ends up in ``[1, 1000)``, for binary
    prefixes in ``[1, 1024)``.  Values smaller than every candidate get the
    smallest candidate; zero, infinities and NaN get :data:`NO_PREFIX`.

    *allowed* restricts the candidates, e.g. ``allowed=("", "k", "M")``.

    >>> best_prefix(4700).symbol
    'k'
    >>> best_prefix(0.000047).symbol
    'µ'
    >>> best_prefix(3 * 2**20, binary=True).symbol
    'Mi'
    """
    magnitude = abs(value)
    if magnitude == 0 or not math.isfinite(magnitude):
        return NO_PREFIX
    if allowed is not None:
        candidates = []
        for item in allowed:
            if isinstance(item, Prefix):
                candidates.append(item)
            elif item == "":
                candidates.append(NO_PREFIX)
            else:
                prefix = prefix_by_symbol(item)
                if prefix is None:
                    raise ValueError(f"unknown prefix {item!r}")
                candidates.append(prefix)
        ladder = tuple(sorted(candidates, key=lambda p: p.factor, reverse=True))
        if not ladder:
            raise ValueError("allowed must name at least one prefix")
    else:
        ladder = _BINARY_LADDER if binary else _ENGINEERING_LADDER
    for prefix in ladder:
        if magnitude > prefix.factor:
            return prefix
    return ladder[-1]


# ---------------------------------------------------------------------------
# Unit definitions
# ---------------------------------------------------------------------------
#
# One unit per line, columns separated by "|":
#
#   symbol | definition | name | plural | aliases | flags
#
# * definition: "[dimension]" for base units, or an optional number (decimal
#   or simple fraction such as 5/9) followed by a unit expression built from
#   units defined *earlier* in the table.
# * plural: only needed when the regular English plural of the name is wrong
#   ("feet", "hertz", "degrees Celsius").
# * aliases: comma separated alternative symbols or names.
# * flags: "prefix" allows SI prefixes, "binary" also allows IEC prefixes,
#   "offset=<x>" gives the zero offset relative to the base unit, in units of
#   the unit itself (degC has offset 273.15).
#
# Values are exact where a definition is exact (international yard and pound
# of 1959, US customary volumes based on the 231 in³ gallon, the thermochemical
# calorie, the International Table Btu, CODATA 2018 for the electronvolt and
# the dalton).

DEFAULT_DEFINITIONS = """
# --- SI base units ---------------------------------------------------------
m        | [length]               | metre                   |                  | meter                        | prefix
g        | 0.001 [mass]           | gram                    |                  | gramme                       | prefix
s        | [time]                 | second                  |                  | sec, secs                    | prefix
A        | [current]              | ampere                  |                  | amp, amps                    | prefix
K        | [temperature]          | kelvin                  | kelvin           | kelvins                      | prefix
mol      | [substance]            | mole                    |                  |                              | prefix
cd       | [luminosity]           | candela                 |                  |                              | prefix
bit      | [information]          | bit                     |                  | b                            | prefix binary

# --- dimensionless ---------------------------------------------------------
rad      | 1                      | radian                  |                  |                              | prefix
sr       | 1                      | steradian               |                  |                              |
%        | 0.01                   | percent                 | percent          | pct                          |
‰        | 0.001                  | per mille               | per mille        | permille                     |
ppm      | 1e-6                   | part per million        | parts per million|                              |
ppb      | 1e-9                   | part per billion        | parts per billion|                              |
dozen    | 12                     | dozen                   | dozen            | doz                          |
deg      | 0.017453292519943295 rad | degree                |                  | °, arcdeg                    |
arcmin   | 1/60 deg               | arcminute               |                  |                              |
arcsec   | 1/60 arcmin            | arcsecond               |                  |                              | prefix
grad     | 0.015707963267948967 rad | gradian               |                  | gon                          |
turn     | 6.283185307179586 rad  | turn                    |                  | rev, revolution              |

# --- length ----------------------------------------------------------------
in       | 0.0254 m               | inch                    |                  | ″                            |
ft       | 12 in                  | foot                    | feet             | ′                            |
yd       | 3 ft                   | yard                    |                  |                              |
mi       | 1760 yd                | mile                    |                  | statute mile                 |
mil      | 0.001 in               | mil                     |                  | thou                         |
hand     | 4 in                   | hand                    |                  |                              |
ch       | 22 yd                  | chain                   |                  |                              |
fur      | 220 yd                 | furlong                 |                  |                              |
ftm      | 6 ft                   | fathom                  |                  |                              |
nmi      | 1852 m                 | nautical mile           |                  | NM, nautical_mile            |
Å        | 1e-10 m                | ångström                |                  | angstrom, \u212b             |
au       | 149597870700 m         | astronomical unit       |                  | AU                           |
ly       | 9460730472580800 m     | light-year              |                  | lightyear, light year        |
pc       | 3.0856775814913673e16 m | parsec                 |                  |                              | prefix

# --- mass ------------------------------------------------------------------
t        | 1000 kg                | tonne                   |                  | metric ton                   | prefix
lb       | 0.45359237 kg          | pound                   |                  | lbs, lbm                     |
oz       | 0.0625 lb              | ounce                   |                  |                              |
gr       | 64.79891 mg            | grain                   |                  |                              |
dr       | 27.34375 gr            | dram                    |                  |                              |
st       | 14 lb                  | stone                   | stone            |                              |
ton      | 2000 lb                | short ton               |                  | short_ton                    |
LT       | 2240 lb                | long ton                |                  | long_ton                     |
ozt      | 31.1034768 g           | troy ounce              |                  | oz_t                         |
ct       | 200 mg                 | carat                   |                  |                              |
Da       | 1.6605390666e-27 kg    | dalton                  |                  | u, amu                       | prefix

# --- time ------------------------------------------------------------------
min      | 60 s                   | minute                  |                  | mins                         |
h        | 60 min                 | hour                    |                  | hr, hrs                      |
d        | 24 h                   | day                     |                  |                              |
wk       | 7 d                    | week                    |                  |                              |
fortnight | 14 d                  | fortnight               |                  |                              |
yr       | 365.25 d               | year                    |                  | julian year                  |
mo       | 30.436875 d            | month                   |                  |                              |
decade   | 10 yr                  | decade                  |                  |                              |
century  | 100 yr                 | century                 |                  |                              |
millennium | 1000 yr              | millennium              | millennia        |                              |

# --- frequency and rates ---------------------------------------------------
Hz       | 1/s                    | hertz                   | hertz            |                              | prefix
rpm      | 1/min                  | revolution per minute   | revolutions per minute | r/min                  |
Bq       | 1/s                    | becquerel               |                  |                              | prefix
Ci       | 3.7e10 Bq              | curie                   |                  |                              | prefix

# --- area and volume -------------------------------------------------------
ha       | 10000 m^2              | hectare                 |                  |                              |
acre     | 4840 yd^2              | acre                    |                  | ac                           |
barn     | 1e-28 m^2              | barn                    |                  |                              | prefix
L        | 0.001 m^3              | litre                   |                  | l, liter, ℓ                  | prefix
cc       | cm^3                   | cubic centimetre        |                  |                              |
gal      | 231 in^3               | gallon                  |                  | US_gal                       |
qt       | 0.25 gal               | quart                   |                  |                              |
pt       | 0.5 qt                 | pint                    |                  |                              |
cup      | 0.5 pt                 | cup                     |                  |                              |
floz     | 0.125 cup              | fluid ounce             |                  | fl oz, fl_oz                 |
tbsp     | 0.5 floz               | tablespoon              |                  | Tbsp                         |
tsp      | 1/3 tbsp               | teaspoon                |                  |                              |
bbl      | 42 gal                 | barrel                  |                  | oil barrel                   |
bu       | 35.23907016688 L       | bushel                  |                  |                              |
imp_gal  | 4.54609 L              | imperial gallon         |                  | UK_gal                       |
imp_qt   | 0.25 imp_gal           | imperial quart          |                  |                              |
imp_pt   | 0.5 imp_qt             | imperial pint           |                  | UK_pt                        |
imp_floz | 0.05 imp_pt            | imperial fluid ounce    |                  | UK_floz                      |

# --- velocity, acceleration -------------------------------------------------
kn       | nmi/h                  | knot                    |                  |                              |
mph      | mi/h                   | mile per hour           | miles per hour   |                              |
kph      | km/h                   | kilometre per hour      | kilometres per hour | kmh                       |
gn       | 9.80665 m/s^2          | standard gravity        |                  | g0, g_n                      |
Gal      | 0.01 m/s^2             | galileo                 |                  |                              | prefix

# --- force -----------------------------------------------------------------
N        | kg*m/s^2               | newton                  |                  |                              | prefix
dyn      | 1e-5 N                 | dyne                    |                  |                              |
kgf      | 9.80665 N              | kilogram-force          |                  | kp                           |
lbf      | 4.4482216152605 N      | pound-force             |                  |                              |
kip      | 1000 lbf               | kip                     |                  |                              |
pdl      | 0.138254954376 N       | poundal                 |                  |                              |

# --- energy and power ------------------------------------------------------
J        | N*m                    | joule                   |                  |                              | prefix
erg      | 1e-7 J                 | erg                     |                  |                              |
cal      | 4.184 J                | calorie                 |                  |                              | prefix
Cal      | 1000 cal               | food calorie            |                  |                              |
Btu      | 1055.05585262 J        | British thermal unit    |                  | BTU                          |
therm    | 100000 Btu             | therm                   |                  |                              |
eV       | 1.602176634e-19 J      | electronvolt            |                  |                              | prefix
ft_lbf   | ft*lbf                 | foot-pound              |                  |                              |
W        | J/s                    | watt                    |                  |                              | prefix
Wh       | W*h                    | watt-hour               |                  |                              | prefix
hp       | 735.49875 W            | horsepower              | horsepower       | bhp                          |
PS       | 735.49875 W            | metric horsepower       | metric horsepower | cv                          |
hp_e     | 746 W                  | electrical horsepower   | electrical horsepower |                         |
TR       | 3516.8528420666667 W   | ton of refrigeration    | tons of refrigeration |                         |

# --- pressure --------------------------------------------------------------
Pa       | N/m^2                  | pascal                  |                  |                              | prefix
bar      | 100000 Pa              | bar                     |                  |                              | prefix
atm      | 101325 Pa              | standard atmosphere     |                  |                              |
at       | 98066.5 Pa             | technical atmosphere    |                  |                              |
Torr     | 133.32236842105263 Pa  | torr                    |                  |                              | prefix
mmHg     | 133.322387415 Pa       | millimetre of mercury   | millimetres of mercury |                        |
inHg     | 3386.389 Pa            | inch of mercury         | inches of mercury |                             |
psi      | lbf/in^2               | pound per square inch   | pounds per square inch |                        |
ksi      | 1000 psi               | kilopound per square inch | kilopounds per square inch |                    |

# --- temperature -----------------------------------------------------------
°C       | K                      | degree Celsius          | degrees Celsius  | degC, ℃, celsius             | offset=273.15
°F       | 5/9 K                  | degree Fahrenheit       | degrees Fahrenheit | degF, ℉, fahrenheit        | offset=459.67
°R       | 5/9 K                  | degree Rankine          | degrees Rankine  | degR, rankine                |
Δ°C      | K                      | delta degree Celsius    | delta degrees Celsius | delta_degC              |
Δ°F      | 5/9 K                  | delta degree Fahrenheit | delta degrees Fahrenheit | delta_degF           |

# --- electricity and magnetism ---------------------------------------------
C        | A*s                    | coulomb                 |                  |                              | prefix
V        | W/A                    | volt                    |                  |                              | prefix
Ω        | V/A                    | ohm                     |                  | \u2126                       | prefix
S        | A/V                    | siemens                 | siemens          | mho                          | prefix
F        | C/V                    | farad                   |                  |                              | prefix
Wb       | V*s                    | weber                   |                  |                              | prefix
T        | Wb/m^2                 | tesla                   |                  |                              | prefix
H        | Wb/A                   | henry                   | henries          |                              | prefix
Ah       | A*h                    | ampere-hour             |                  |                              | prefix
G        | 1e-4 T                 | gauss                   |                  |                              | prefix
Mx       | 1e-8 Wb                | maxwell                 |                  |                              |

# --- light, chemistry, radiation --------------------------------------------
lm       | cd*sr                  | lumen                   |                  |                              | prefix
lx       | lm/m^2                 | lux                     | lux              |                              | prefix
M        | mol/L                  | molar                   |                  |                              | prefix
kat      | mol/s                  | katal                   |                  |                              | prefix
Gy       | J/kg                   | gray                    |                  |                              | prefix
Sv       | J/kg                   | sievert                 |                  |                              | prefix

# --- viscosity -------------------------------------------------------------
P        | 0.1 Pa*s               | poise                   |                  |                              | prefix
St       | 0.0001 m^2/s           | stokes                  | stokes           |                              | prefix

# --- information -----------------------------------------------------------
B        | 8 bit                  | byte                    |                  | octet                        | prefix binary
nibble   | 4 bit                  | nibble                  |                  |                              |
bps      | bit/s                  | bit per second          | bits per second  |                              | prefix

# --- fuel economy ----------------------------------------------------------
mpg      | mi/gal                 | mile per gallon         | miles per gallon |                              |
"""


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def _default_plural(name: str) -> str:
    """Regular English plural of a unit name.

    Compound names are pluralised on their head word: "mile per hour" ->
    "miles per hour", "inch of mercury" -> "inches of mercury".
    """
    if not name:
        return name
    for joiner in (" per ", " of "):
        if joiner in name:
            head, _, tail = name.partition(joiner)
            return _default_plural(head) + joiner + tail
    words = name.rsplit(" ", 1)
    last = words[-1]
    if last.endswith(("s", "x", "z", "ch", "sh")):
        last += "es"
    elif last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        last = last[:-1] + "ies"
    else:
        last += "s"
    words[-1] = last
    return " ".join(words)


def _needs_parens(symbol: str, operators: str) -> bool:
    return any(op in symbol for op in operators) and not (
        symbol.startswith("(") and symbol.endswith(")")
    )


class Unit:
    """A unit of measurement.

    A unit is described by its :attr:`dimension`, its :attr:`factor` (the size
    of one unit expressed in the coherent SI unit of that dimension) and, for
    temperature scales, an :attr:`offset`: a value ``v`` in this unit equals
    ``(v + offset) * factor`` in the SI unit.

    Units are normally obtained from a :class:`UnitRegistry` rather than
    constructed directly.  They can be multiplied, divided and raised to
    integer powers to form composite units:

    >>> reg = get_registry()
    >>> speed = reg.get("km") / reg.get("h")
    >>> speed.symbol, round(speed.factor, 6)
    ('km/h', 0.277778)
    """

    __slots__ = (
        "symbol",
        "name",
        "factor",
        "dimension",
        "offset",
        "_plural",
        "prefixable",
        "binary_prefixable",
        "aliases",
        "definition",
        "root",
        "prefix",
        "composite",
    )

    def __init__(
        self,
        symbol: str,
        factor: float,
        dimension: Dimension,
        *,
        name: str = "",
        plural: str = "",
        offset: float = 0.0,
        prefixable: bool = False,
        binary_prefixable: bool = False,
        aliases: Sequence[str] = (),
        definition: str = "",
        root: Optional["Unit"] = None,
        prefix: Prefix = NO_PREFIX,
        composite: bool = False,
    ):
        factor = float(factor)
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError(f"unit factor must be positive and finite, got {factor!r}")
        if not isinstance(dimension, Dimension):
            raise TypeError("dimension must be a Dimension")
        self.symbol = symbol
        self.name = name
        self.factor = factor
        self.dimension = dimension
        self.offset = float(offset)
        self._plural = plural
        self.prefixable = prefixable
        self.binary_prefixable = binary_prefixable
        self.aliases = tuple(aliases)
        self.definition = definition
        self.root = root if root is not None else self
        self.prefix = prefix
        self.composite = composite

    # Construction helpers ---------------------------------------------------

    @classmethod
    def scalar(cls, value: Number) -> "Unit":
        """A dimensionless unit representing a pure number (``1000``)."""
        if value <= 0:
            raise ValueError("a scalar unit must be positive")
        return cls(_plain(value), float(value), DIMENSIONLESS, composite=True)

    def with_prefix(self, prefix: Prefix) -> "Unit":
        """This unit with *prefix* applied: ``m`` + kilo -> ``km``."""
        if not prefix:
            return self
        if self.prefix:
            raise UnitError(f"{self.symbol!r} already has a prefix")
        if not self.accepts_prefix(prefix):
            raise UnitError(f"{self.symbol!r} does not take the prefix {prefix.name!r}")
        return Unit(
            prefix.symbol + self.symbol,
            clean_float(self.factor * prefix.factor, 15),
            self.dimension,
            name=prefix.name + self.name if self.name else "",
            plural=prefix.name + self.plural if self.name else "",
            offset=self.offset,
            root=self,
            prefix=prefix,
        )

    def accepts_prefix(self, prefix: Prefix) -> bool:
        if self.prefix or self.composite:
            return False
        if prefix.binary:
            return self.binary_prefixable
        return self.prefixable

    # Properties -------------------------------------------------------------

    @property
    def plural(self) -> str:
        if self._plural:
            return self._plural
        return _default_plural(self.name)

    @property
    def is_offset(self) -> bool:
        return self.offset != 0.0

    @property
    def dimensionless(self) -> bool:
        return self.dimension.dimensionless

    def long_name(self, plural: bool = False) -> str:
        """Spelled-out name for display; composite units fall back to the symbol."""
        if not self.name:
            return self.symbol
        return self.plural if plural else self.name

    def is_compatible(self, other: "Unit") -> bool:
        """True if quantities in the two units can be converted into each other."""
        return isinstance(other, Unit) and self.dimension == other.dimension

    def factor_to(self, other: "Unit") -> float:
        """Multiplier converting a value in this unit to *other* (no offsets)."""
        if not self.is_compatible(other):
            raise DimensionalityError(self, other)
        if self.is_offset or other.is_offset:
            raise OffsetUnitError(
                f"conversion between {self.symbol!r} and {other.symbol!r} is not a pure factor"
            )
        return self.factor / other.factor

    # Algebra ----------------------------------------------------------------

    def _check_plain(self, other: "Unit", operation: str) -> None:
        for unit in (self, other):
            if unit.is_offset:
                raise OffsetUnitError(
                    f"cannot {operation} the offset unit {unit.symbol!r}; "
                    f"use a temperature difference unit such as 'delta_degC' instead"
                )

    def __mul__(self, other: Union["Unit", Number]) -> "Unit":
        if isinstance(other, (int, float, Fraction)) and not isinstance(other, bool):
            other = Unit.scalar(other)
        if not isinstance(other, Unit):
            return NotImplemented
        self._check_plain(other, "multiply")
        if self.symbol == "":
            return other
        if other.symbol == "":
            return self
        left = f"({self.symbol})" if _needs_parens(self.symbol, "/") else self.symbol
        right = f"({other.symbol})" if _needs_parens(other.symbol, "/") else other.symbol
        return Unit(
            f"{left}·{right}",
            self.factor * other.factor,
            self.dimension * other.dimension,
            composite=True,
        )

    __rmul__ = __mul__

    def __truediv__(self, other: Union["Unit", Number]) -> "Unit":
        if isinstance(other, (int, float, Fraction)) and not isinstance(other, bool):
            other = Unit.scalar(other)
        if not isinstance(other, Unit):
            return NotImplemented
        self._check_plain(other, "divide")
        if other.symbol == "":
            return self
        right = f"({other.symbol})" if _needs_parens(other.symbol, "·/") else other.symbol
        left = self.symbol or "1"
        return Unit(
            f"{left}/{right}",
            self.factor / other.factor,
            self.dimension / other.dimension,
            composite=True,
        )

    def __rtruediv__(self, other: Number) -> "Unit":
        if isinstance(other, (int, float, Fraction)) and not isinstance(other, bool):
            return Unit.scalar(other) / self if other != 1 else DIMENSIONLESS_UNIT / self
        return NotImplemented

    def __pow__(self, power: Union[int, Fraction]) -> "Unit":
        if isinstance(power, float) and power.is_integer():
            power = int(power)
        if not isinstance(power, (int, Fraction)):
            raise TypeError(f"unit exponents must be integers or fractions, got {power!r}")
        if power == 1:
            return self
        self._check_plain(self, "raise to a power")
        if power == 0:
            return DIMENSIONLESS_UNIT
        base = f"({self.symbol})" if self.composite and _needs_parens(self.symbol, "·/") else self.symbol
        return Unit(
            base + superscript(power),
            self.factor ** float(power),
            self.dimension ** power,
            composite=True,
        )

    # Comparison and display ---------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Unit):
            return NotImplemented
        return (
            self.dimension == other.dimension
            and isclose(self.factor, other.factor)
            and isclose(self.offset, other.offset)
        )

    def __hash__(self) -> int:
        return hash((self.dimension, clean_float(self.factor, 10), clean_float(self.offset, 10)))

    def __str__(self) -> str:
        return self.symbol

    def __repr__(self) -> str:
        return f"<Unit {self.symbol!r}>"


#: The unit of pure numbers.
DIMENSIONLESS_UNIT = Unit("", 1.0, DIMENSIONLESS, name="", composite=True)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_DEF_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_DEFINITION_RE = re.compile(rf"(?P<num>{_DEF_NUMBER}(?:/{_DEF_NUMBER})?)(?:\s+(?P<expr>\S.*))?")
_BASE_DIMENSION_RE = re.compile(r"\[(?P<dim>[a-z ]+)\]")


def _definition_number(text: str) -> float:
    numerator, _, denominator = text.partition("/")
    value = float(numerator)
    if denominator:
        value /= float(denominator)
    return value


def _looks_like_name(alias: str) -> bool:
    """Aliases that are words ("meter", "julian year") rather than symbols ("NM")."""
    letters = alias.replace(" ", "").replace("-", "").replace("_", "")
    return len(alias) >= 4 and letters.isalpha() and alias == alias.lower()


def _singular_candidates(word: str) -> Iterator[str]:
    """Possible singular forms of an English plural, most specific first."""
    if len(word) > 4 and word.endswith("ies"):
        yield word[:-3] + "y"  # centuries -> century
    if len(word) > 3 and word.endswith("es") and word[:-2].endswith(("s", "x", "z", "sh")):
        yield word[:-2]  # inches -> inch, gausses -> gauss (but miles -> mile)
    if len(word) > 2 and word.endswith("s"):
        yield word[:-1]  # metres -> metre, light-years -> light-year


class UnitRegistry:
    """A catalogue of units and the rules for looking them up.

    Lookups (:meth:`get`) accept, in order of precedence:

    1. symbols and symbol-like aliases, case-sensitively (``"mA"`` is not
       ``"MA"``);
    2. names, explicit plurals and word aliases (``"metre"``, ``"feet"``,
       ``"meter"``);
    3. regular plurals of names (``"inches"``, ``"centuries"``);
    4. a prefix symbol followed by the symbol of a unit that takes prefixes
       (``"km"``, ``"µs"``, ``"us"``, ``"KiB"``), or a prefix name followed
       by a name (``"kilometres"``, ``"mebibytes"``);
    5. names compared case-insensitively (``"Metres"``, ``"KILOGRAM"``).

    Anything else is treated as a unit expression (``"kg*m/s^2"``) by
    :meth:`parse_unit`.

    >>> reg = UnitRegistry()
    >>> reg.get("kilometres").symbol
    'km'
    >>> reg.parse_unit("N*m") == reg.get("J")
    True
    """

    # Units with factor 1 that should not be picked as *the* unit of their
    # dimension: J/kg is a specific energy before it is an absorbed dose.
    _NOT_COHERENT_DEFAULTS = frozenset({"Gy", "Sv", "Bq"})

    def __init__(self, definitions: Optional[str] = None, *, defaults: bool = True):
        self._units: Dict[str, Unit] = {}
        self._symbols: Dict[str, Unit] = {}
        self._names: Dict[str, Unit] = {}
        self._folded: Dict[str, Unit] = {}
        self._cache: Dict[str, Unit] = {}
        self._expression_cache: Dict[str, Unit] = {}
        if defaults:
            self.load_definitions(DEFAULT_DEFINITIONS)
        if definitions:
            self.load_definitions(definitions)

    # Defining units -------------------------------------------------------------

    def load_definitions(self, text: str) -> List[Unit]:
        """Define every unit in a definitions table (see :data:`DEFAULT_DEFINITIONS`)."""
        defined = []
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            columns = [c.strip() for c in line.split("|")]
            if len(columns) < 2:
                raise UnitError(f"line {lineno}: expected 'symbol | definition | ...': {raw!r}")
            columns += [""] * (6 - len(columns))
            symbol, definition, name, plural, aliases, flags = columns[:6]
            options: Dict[str, Any] = {}
            for flag in flags.split():
                key, _, value = flag.partition("=")
                if key == "prefix":
                    options["prefix"] = True
                elif key == "binary":
                    options["binary"] = True
                elif key == "offset":
                    options["offset"] = float(value)
                else:
                    raise UnitError(f"line {lineno}: unknown flag {flag!r}")
            try:
                unit = self.define(
                    symbol,
                    definition,
                    name=name,
                    plural=plural,
                    aliases=[a.strip() for a in aliases.split(",") if a.strip()],
                    **options,
                )
            except UnitError as exc:
                raise UnitError(f"line {lineno} ({symbol!r}): {exc}") from exc
            defined.append(unit)
        return defined

    def define(
        self,
        symbol: str,
        definition: str,
        *,
        name: str = "",
        plural: str = "",
        aliases: Sequence[str] = (),
        prefix: bool = False,
        binary: bool = False,
        offset: float = 0.0,
    ) -> Unit:
        """Define a new unit.

        *definition* is either ``"[dimension]"`` for a new base unit, or an
        optional number followed by an expression in existing units:

        >>> reg = UnitRegistry()
        >>> reg.define("smoot", "1.7018 m", name="smoot").factor
        1.7018
        """
        if not symbol or any(ch.isspace() for ch in symbol):
            raise UnitError(f"invalid unit symbol {symbol!r}")
        if symbol in self._units:
            raise UnitError(f"unit {symbol!r} is already defined")
        factor, dimension = self._evaluate_definition(definition)
        unit = Unit(
            symbol,
            factor,
            dimension,
            name=name,
            plural=plural,
            offset=offset,
            prefixable=prefix or binary,
            binary_prefixable=binary,
            aliases=aliases,
            definition=definition,
        )
        self._add_symbol(symbol, unit)
        if name:
            self._add_name(name, unit)
        if plural:
            self._add_name(plural, unit)
        for alias in aliases:
            if _looks_like_name(alias):
                self._add_name(alias, unit)
            else:
                self._add_symbol(alias, unit)
        self._units[symbol] = unit
        self._cache.clear()
        self._expression_cache.clear()
        return unit

    def _evaluate_definition(self, definition: str) -> Tuple[float, Dimension]:
        text = definition.strip()
        if not text:
            raise UnitError("empty definition")
        number = 1.0
        m = _DEFINITION_RE.fullmatch(text)
        if m:
            number = _definition_number(m.group("num"))
            text = (m.group("expr") or "").strip()
        if number <= 0:
            raise UnitError(f"definition must be positive: {definition!r}")
        if not text:
            return number, DIMENSIONLESS
        m = _BASE_DIMENSION_RE.fullmatch(text)
        if m:
            try:
                return number, Dimension.base(m.group("dim"))
            except ValueError as exc:
                raise UnitError(str(exc)) from None
        unit = self.parse_unit(text)
        if unit.is_offset:
            raise UnitError(f"cannot define a unit in terms of the offset unit {unit.symbol!r}")
        # Round away the binary noise that chained definitions accumulate
        # (1760 yd * 3 ft * 12 in * 0.0254 m is not exactly 1609.344 in floats).
        return clean_float(number * unit.factor, 15), unit.dimension

    def _add_symbol(self, key: str, unit: Unit) -> None:
        existing = self._symbols.get(key)
        if existing is not None and existing is not unit:
            raise UnitError(f"symbol {key!r} already refers to {existing.symbol!r}")
        self._symbols[key] = unit

    def _add_name(self, key: str, unit: Unit) -> None:
        existing = self._names.get(key)
        if existing is not None and existing is not unit:
            raise UnitError(f"name {key!r} already refers to {existing.symbol!r}")
        self._names[key] = unit
        self._folded.setdefault(key.casefold(), unit)

    # Lookup ---------------------------------------------------------------------

    def get(self, key: Union[str, Unit]) -> Unit:
        """Resolve a single unit symbol or name; raise :class:`UnknownUnitError`."""
        unit = self.find(key)
        if unit is None:
            raise UnknownUnitError(str(key), self.suggest(str(key)))
        return unit

    __getitem__ = get

    def find(self, key: Union[str, Unit]) -> Optional[Unit]:
        """Like :meth:`get` but return ``None`` for unknown units."""
        if isinstance(key, Unit):
            return key
        key = " ".join(key.split())
        if not key:
            return None
        unit = self._cache.get(key)
        if unit is None:
            unit = self._resolve(key)
            if unit is not None:
                self._cache[key] = unit
        return unit

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.find(key) is not None

    def _resolve(self, key: str) -> Optional[Unit]:
        unit = self._symbols.get(key) or self._names.get(key)
        if unit is not None:
            return unit
        unit = self._resolve_plural(key, self._names)
        if unit is not None:
            return unit
        unit = self._resolve_prefixed(key)
        if unit is not None:
            return unit
        folded = key.casefold()
        return self._folded.get(folded) or self._resolve_plural(folded, self._folded)

    @staticmethod
    def _resolve_plural(key: str, names: Mapping[str, Unit]) -> Optional[Unit]:
        for singular in _singular_candidates(key):
            unit = names.get(singular)
            if unit is not None:
                return unit
        return None

    def _resolve_prefixed(self, key: str) -> Optional[Unit]:
        for prefix, rest in split_prefix_symbol(key):
            base = self._symbols.get(rest)
            if base is not None and base.accepts_prefix(prefix):
                return base.with_prefix(prefix)
        for prefix, rest in split_prefix_name(key):
            folded = rest.casefold()
            base = (
                self._names.get(rest)
                or self._resolve_plural(rest, self._names)
                or self._folded.get(folded)
                or self._resolve_plural(folded, self._folded)
            )
            if base is not None and base.accepts_prefix(prefix):
                return base.with_prefix(prefix)
        return None

    def suggest(self, key: str, n: int = 3) -> List[str]:
        """Known symbols or names that look like *key* (for error messages)."""
        candidates = list(self._symbols) + list(self._names)
        return difflib.get_close_matches(key, candidates, n=n, cutoff=0.75)

    # Expressions ----------------------------------------------------------------

    def parse_unit(self, text: Union[str, Unit]) -> Unit:
        """Parse a unit expression such as ``"kg·m²/s²"`` or ``"J/(kg*K)"``.

        A plain symbol or name (including multi-word names such as
        ``"nautical mile"``) is looked up directly; anything else goes
        through the expression parser.  An empty string means
        dimensionless.
        """
        if isinstance(text, Unit):
            return text
        stripped = text.strip()
        if stripped in ("", "1"):
            return DIMENSIONLESS_UNIT
        unit = self.find(stripped)
        if unit is not None:
            return unit
        unit = self._expression_cache.get(stripped)
        if unit is None:
            unit = _UnitExpressionParser(self, stripped).parse()
            self._expression_cache[stripped] = unit
        return unit

    # Introspection --------------------------------------------------------------

    def __iter__(self) -> Iterator[Unit]:
        return iter(self._units.values())

    def __len__(self) -> int:
        return len(self._units)

    def symbols(self) -> List[str]:
        """Canonical symbols of all defined units, in definition order."""
        return list(self._units)

    def units_for(self, dimension: Union[Dimension, str]) -> List[Unit]:
        """Defined units of *dimension* (or dimension name), smallest first."""
        if isinstance(dimension, str):
            dimension = named_dimension(dimension)
        found = [u for u in self._units.values() if u.dimension == dimension]
        return sorted(found, key=lambda u: (u.factor, u.offset))

    def coherent_unit(self, dimension: Dimension) -> Unit:
        """The coherent SI unit of *dimension*.

        If the registry defines a named unit with factor 1 (``"N"`` for force)
        that unit is returned; otherwise a composite of base units is built
        (``"kg·m⁻³"``-style symbols).
        """
        if dimension.dimensionless:
            return DIMENSIONLESS_UNIT
        for unit in self._units.values():
            if (
                unit.symbol not in self._NOT_COHERENT_DEFAULTS
                and unit.dimension == dimension
                and unit.factor == 1.0
                and not unit.is_offset
                and unit.prefixable
            ):
                return unit
        return self._base_composite(dimension)

    def _base_composite(self, dimension: Dimension) -> Unit:
        base_symbols = ("m", "kg", "s", "A", "K", "mol", "cd", "bit")
        result = DIMENSIONLESS_UNIT
        for symbol, exponent in zip(base_symbols, dimension.exponents):
            if exponent:
                result = result * (self.get(symbol) ** exponent)
        return result

    def delta_unit(self, unit: Unit) -> Unit:
        """The difference unit matching an offset unit (``°C`` -> ``Δ°C``)."""
        if not unit.is_offset:
            return unit
        for candidate in self._units.values():
            if (
                candidate.dimension == unit.dimension
                and not candidate.is_offset
                and candidate.symbol.startswith("Δ")
                and isclose(candidate.factor, unit.factor)
            ):
                return candidate
        return Unit("Δ" + unit.symbol, unit.factor, unit.dimension, composite=True)

    def catalogue(self, dimension: Union[Dimension, str, None] = None) -> List[Tuple[str, str, float, str]]:
        """``(symbol, name, factor, dimension)`` rows describing defined units."""
        units = self.units_for(dimension) if dimension is not None else list(self._units.values())
        return [(u.symbol, u.name, u.factor, u.dimension.describe()) for u in units]

    def describe(self, key: str) -> str:
        """A short human readable description of a unit, for help output."""
        unit = self.get(key)
        lines = [f"{unit.symbol}: {unit.long_name() or '(unnamed)'}"]
        lines.append(f"  dimension: {unit.dimension.describe()} ({unit.dimension})")
        coherent = self.coherent_unit(unit.dimension)
        lines.append(f"  1 {unit.symbol} = {_plain(unit.factor)} {coherent.symbol}".rstrip())
        if unit.is_offset:
            lines.append(f"  offset: {_plain(unit.offset)}")
        if unit.root.aliases:
            lines.append("  aliases: " + ", ".join(unit.root.aliases))
        if unit.root.prefixable:
            kinds = "SI and binary" if unit.root.binary_prefixable else "SI"
            lines.append(f"  accepts {kinds} prefixes")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unit expression parser
# ---------------------------------------------------------------------------
#
# Grammar (left-associative, implicit multiplication by juxtaposition):
#
#   product  := power ( ("*" | "·" | "×") power | "/" power | power )*
#   power    := atom ( ("^" | "**") exponent | superscript | digits )?
#   exponent := ["-" | "+"] number | "(" ["-"] number [ "/" number ] ")"
#   atom     := name | number | "(" product ")"
#
# "kg m^2 s^-2", "kg·m²·s⁻²" and "kg*m**2/s**2" all denote the joule, and
# "J/kg/K" means J/(kg·K) -- division binds to the left like in arithmetic.


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str
    start: int
    end: int


# Letters (any script) and a few symbols; superscript digits are \w but
# belong to the exponent, so they are excluded explicitly.
_NAME_CHAR = r"(?:[^\W\d⁰¹²³⁴⁵⁶⁷⁸⁹]|[°%‰′″℃℉Å])"
_TOKEN_RE = re.compile(
    "|".join(
        f"(?P<{kind}>{pattern})"
        for kind, pattern in (
            ("ws", r"\s+"),
            ("number", r"(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"),
            ("pow", r"\*\*|\^"),
            ("mul", r"[*·×⋅•]"),
            ("div", r"[/÷]"),
            ("lpar", r"\("),
            ("rpar", r"\)"),
            ("sup", r"[⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+"),
            ("sign", r"[-+\u2212]"),
            ("name", rf"{_NAME_CHAR}(?:{_NAME_CHAR}|-(?=[^\W\d]))*"),
        )
    )
)


def _tokenize_unit(text: str) -> List[_Token]:
    tokens = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            raise ParseError(f"unexpected character {text[pos]!r} in unit", text, pos)
        kind = m.lastgroup or ""
        if kind != "ws":
            tokens.append(_Token(kind, m.group(), m.start(), m.end()))
        pos = m.end()
    return tokens


class _UnitExpressionParser:
    """Recursive descent parser producing a :class:`Unit` from an expression."""

    def __init__(self, registry: UnitRegistry, text: str):
        self.registry = registry
        self.text = text
        self.tokens = _tokenize_unit(text)
        self.pos = 0

    # Token helpers ----------------------------------------------------------------

    def _peek(self) -> Optional[_Token]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self) -> Optional[_Token]:
        tok = self._peek()
        if tok is not None:
            self.pos += 1
        return tok

    def _accept(self, kind: str) -> Optional[_Token]:
        tok = self._peek()
        if tok is not None and tok.kind == kind:
            self.pos += 1
            return tok
        return None

    def _expect(self, kind: str, what: str) -> _Token:
        tok = self._next()
        if tok is None:
            raise ParseError(f"expected {what} at end of unit", self.text, len(self.text))
        if tok.kind != kind:
            raise ParseError(f"expected {what}, found {tok.text!r}", self.text, tok.start)
        return tok

    # Grammar --------------------------------------------------------------------

    def parse(self) -> Unit:
        if not self.tokens:
            return DIMENSIONLESS_UNIT
        unit = self._parse_product()
        tok = self._peek()
        if tok is not None:
            raise ParseError(f"unexpected {tok.text!r} in unit", self.text, tok.start)
        return unit

    def _parse_product(self) -> Unit:
        unit = self._parse_power()
        while True:
            tok = self._peek()
            if tok is None:
                return unit
            if tok.kind == "mul":
                self._next()
                unit = unit * self._parse_power()
            elif tok.kind == "div":
                self._next()
                unit = unit / self._parse_product()
            elif tok.kind in ("name", "number", "lpar"):
                unit = unit * self._parse_power()
            else:
                return unit

    def _parse_power(self) -> Unit:
        start = self._peek()
        base = self._parse_atom()
        tok = self._peek()
        if tok is None:
            return base
        if tok.kind == "pow":
            self._next()
            return base ** self._parse_exponent()
        if tok.kind == "sup":
            self._next()
            return base ** int(tok.text.translate(_SUPERSCRIPT_TO_ASCII))
        if (
            tok.kind == "number"
            and start is not None
            and start.kind == "name"
            and tok.start == self.tokens[self.pos - 1].end
            and tok.text.isdigit()
        ):
            # "m2", "cm3": exponent written directly after the symbol
            self._next()
            return base ** int(tok.text)
        return base

    def _parse_exponent(self) -> Union[int, Fraction]:
        paren = self._accept("lpar") is not None
        negative = False
        sign = self._accept("sign")
        if sign is not None:
            negative = sign.text != "+"
        number = self._expect("number", "exponent")
        try:
            value = Fraction(number.text)
        except ValueError:
            raise ParseError("invalid exponent", self.text, number.start) from None
        if paren:
            if self._accept("div") is not None:
                denominator = self._expect("number", "exponent denominator")
                if Fraction(denominator.text) == 0:
                    raise ParseError("zero denominator in exponent", self.text, denominator.start)
                value /= Fraction(denominator.text)
            self._expect("rpar", "')'")
        if negative:
            value = -value
        return int(value) if value.denominator == 1 else value

    def _parse_atom(self) -> Unit:
        tok = self._next()
        if tok is None:
            raise ParseError("unexpected end of unit", self.text, len(self.text))
        if tok.kind == "name":
            unit = self.registry.find(tok.text)
            if unit is None:
                raise UnknownUnitError(tok.text, self.registry.suggest(tok.text))
            return unit
        if tok.kind == "number":
            value = float(tok.text)
            if value <= 0:
                raise ParseError("scale factors in units must be positive", self.text, tok.start)
            return Unit.scalar(value)
        if tok.kind == "lpar":
            inner = self._parse_product()
            self._expect("rpar", "')'")
            return inner
        raise ParseError(f"unexpected {tok.text!r} in unit", self.text, tok.start)


def parse_unit(text: Union[str, Unit], registry: Optional[UnitRegistry] = None) -> Unit:
    """Parse a unit expression with the default (or given) registry."""
    return (registry or get_registry()).parse_unit(text)


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

_default_registry: Optional[UnitRegistry] = None


def get_registry() -> UnitRegistry:
    """The process-wide default registry, created on first use."""
    global _default_registry
    if _default_registry is None:
        _default_registry = UnitRegistry()
    return _default_registry


def set_registry(registry: Optional[UnitRegistry]) -> None:
    """Replace the default registry (``None`` resets it to the built-in one)."""
    global _default_registry
    if registry is not None and not isinstance(registry, UnitRegistry):
        raise TypeError("expected a UnitRegistry")
    _default_registry = registry


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def convert_value(value: float, src: Unit, dst: Unit) -> float:
    """Convert a plain number from unit *src* to unit *dst*.

    Ordinary units only need their factors; units with an offset are taken
    through the coherent SI unit (kelvin for temperatures).

    >>> reg = get_registry()
    >>> convert_value(1, reg.get("mi"), reg.get("km"))
    1.609344
    >>> round(convert_value(212, reg.get("°F"), reg.get("°C")), 9)
    100.0
    """
    if src.dimension != dst.dimension:
        raise DimensionalityError(src, dst)
    if src.is_offset or dst.is_offset:
        base = (value + src.offset) * src.factor
        return base / dst.factor + dst.offset
    if src.factor == dst.factor:
        return value
    return value * src.factor / dst.factor


def convert(value: float, src: Union[str, Unit], dst: Union[str, Unit], registry: Optional[UnitRegistry] = None) -> float:
    """Convert *value* between two units given as strings or :class:`Unit` objects.

    >>> convert(100, "km/h", "m/s")
    27.77777777777778
    """
    reg = registry or get_registry()
    return convert_value(value, reg.parse_unit(src), reg.parse_unit(dst))


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------

_Real = (int, float, Fraction)


def _is_real(x: Any) -> bool:
    return isinstance(x, _Real) and not isinstance(x, bool)


@total_ordering
class Quantity:
    """A magnitude together with a unit.

    >>> q = Quantity(1.5, "km")
    >>> q.to("m")
    <Quantity(1500, 'm')>
    >>> (q + Quantity(250, "m")).m_as("km")
    1.75
    >>> (Quantity(10, "m") / Quantity(4, "s")).to("km/h")
    <Quantity(9, 'km/h')>

    Arithmetic converts the right operand to the unit of the left one, so
    the result of ``a + b`` is in ``a``'s unit.  Multiplication and division
    build composite units, which :meth:`simplify` can reduce to a named unit
    where one exists (``N·m`` -> ``J``).

    Comparisons work across units of the same dimension; quantities of
    different dimensions are never equal, and ordering them raises
    :class:`DimensionalityError`.
    """

    __slots__ = ("magnitude", "unit", "_registry")

    def __init__(
        self,
        magnitude: Number,
        unit: Union[str, Unit] = "",
        registry: Optional[UnitRegistry] = None,
    ):
        if isinstance(magnitude, Quantity):
            raise TypeError("use Quantity.to() to change the unit of a quantity")
        if not _is_real(magnitude):
            raise TypeError(f"magnitude must be a real number, got {type(magnitude).__name__}")
        self._registry = registry or get_registry()
        self.magnitude = magnitude
        self.unit = self._registry.parse_unit(unit) if isinstance(unit, str) else unit
        if not isinstance(self.unit, Unit):
            raise TypeError(f"unit must be a str or Unit, got {type(unit).__name__}")

    # Basic properties -------------------------------------------------------------

    @property
    def dimension(self) -> Dimension:
        return self.unit.dimension

    @property
    def dimensionless(self) -> bool:
        return self.unit.dimensionless

    @property
    def registry(self) -> UnitRegistry:
        return self._registry

    def _new(self, magnitude: Number, unit: Unit) -> "Quantity":
        return Quantity(magnitude, unit, self._registry)

    def _base_magnitude(self) -> float:
        """The magnitude expressed in the coherent SI unit."""
        return (self.magnitude + self.unit.offset) * self.unit.factor

    # Conversion -----------------------------------------------------------------

    def to(self, unit: Union[str, Unit]) -> "Quantity":
        """This quantity expressed in another unit of the same dimension."""
        target = self._registry.parse_unit(unit)
        return self._new(convert_value(self.magnitude, self.unit, target), target)

    def m_as(self, unit: Union[str, Unit]) -> float:
        """The magnitude of this quantity in *unit*, as a plain number."""
        target = self._registry.parse_unit(unit)
        return convert_value(self.magnitude, self.unit, target)

    def to_base(self) -> "Quantity":
        """Convert to the coherent SI unit of the dimension (``km/h`` -> ``m·s⁻¹``)."""
        return self.to(self._registry.coherent_unit(self.dimension))

    def simplify(self) -> "Quantity":
        """Replace a composite unit by the named coherent unit, if there is one.

        >>> (Quantity(3, "N") * Quantity(2, "m")).simplify()
        <Quantity(6, 'J')>
        """
        if not self.unit.composite:
            return self
        target = self._registry.coherent_unit(self.dimension)
        if target.composite and self.dimension.dimensionless:
            return self._new(self.magnitude * self.unit.factor, DIMENSIONLESS_UNIT)
        if target.composite:
            return self
        return self.to(target)

    def to_compact(self, *, binary: Optional[bool] = None) -> "Quantity":
        """Re-prefix the unit so that the magnitude is between 1 and 1000.

        Only units that accept prefixes are changed; others are returned as
        they are.  Information units use binary prefixes unless *binary* is
        ``False``.

        >>> Quantity(0.0047, "F").to_compact()
        <Quantity(4.7, 'mF')>
        >>> Quantity(1536, "B").to_compact()
        <Quantity(1.5, 'KiB')>
        """
        root = self.unit.root
        if not root.prefixable or root.is_offset:
            return self
        if binary is None:
            binary = root.binary_prefixable
        if binary and not root.binary_prefixable:
            raise UnitError(f"{root.symbol!r} does not take binary prefixes")
        value = convert_value(self.magnitude, self.unit, root)
        prefix = best_prefix(value, binary=binary)
        unit = root.with_prefix(prefix) if prefix else root
        return self._new(clean_float(value / prefix.factor), unit)

    def is_compatible(self, other: Union["Quantity", Unit, str]) -> bool:
        if isinstance(other, Quantity):
            other = other.unit
        elif isinstance(other, str):
            other = self._registry.parse_unit(other)
        return self.unit.is_compatible(other)

    # Arithmetic -----------------------------------------------------------------

    def _coerce(self, other: Any, operation: str) -> "Quantity":
        if isinstance(other, Quantity):
            return other
        if _is_real(other):
            return self._new(other, DIMENSIONLESS_UNIT)
        raise TypeError(f"cannot {operation} Quantity and {type(other).__name__}")

    def __add__(self, other: Any) -> "Quantity":
        if not isinstance(other, Quantity) and not _is_real(other):
            return NotImplemented
        other = self._coerce(other, "add")
        if self.dimension != other.dimension:
            raise DimensionalityError(self, other, operation="add")
        if self.unit.is_offset and other.unit.is_offset:
            raise OffsetUnitError(
                f"cannot add two absolute temperatures ({self} + {other}); "
                f"convert one of them to a difference first"
            )
        if self.unit.is_offset:
            delta = other.magnitude * other.unit.factor / self.unit.factor
            return self._new(self.magnitude + delta, self.unit)
        if other.unit.is_offset:
            return other + self
        return self._new(self.magnitude + other.m_as(self.unit), self.unit)

    def __radd__(self, other: Any) -> "Quantity":
        if _is_real(other) and other == 0 and not self.dimensionless:
            return self  # lets sum() work on quantities
        return self.__add__(other)

    def __sub__(self, other: Any) -> "Quantity":
        if not isinstance(other, Quantity) and not _is_real(other):
            return NotImplemented
        other = self._coerce(other, "subtract")
        if self.dimension != other.dimension:
            raise DimensionalityError(self, other, operation="subtract")
        if self.unit.is_offset and other.unit.is_offset:
            # absolute - absolute = difference, expressed in our delta unit
            delta_unit = self._registry.delta_unit(self.unit)
            difference = (self._base_magnitude() - other._base_magnitude()) / delta_unit.factor
            return self._new(difference, delta_unit)
        if other.unit.is_offset:
            raise OffsetUnitError(f"cannot subtract an absolute temperature ({other}) from {self}")
        return self + (-other)

    def __rsub__(self, other: Any) -> "Quantity":
        return (-self).__add__(other)

    def __mul__(self, other: Any) -> "Quantity":
        if _is_real(other):
            return self._new(self.magnitude * other, self.unit)
        if not isinstance(other, Quantity):
            return NotImplemented
        if other.dimensionless and other.unit.symbol == "":
            return self._new(self.magnitude * other.magnitude, self.unit)
        return self._new(self.magnitude * other.magnitude, self.unit * other.unit)

    def __rmul__(self, other: Any) -> "Quantity":
        if _is_real(other):
            return self._new(other * self.magnitude, self.unit)
        return NotImplemented

    def __truediv__(self, other: Any) -> "Quantity":
        if _is_real(other):
            return self._new(self.magnitude / other, self.unit)
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.unit == other.unit and self.unit.symbol == other.unit.symbol and not self.unit.is_offset:
            return self._new(self.magnitude / other.magnitude, DIMENSIONLESS_UNIT)
        return self._new(self.magnitude / other.magnitude, self.unit / other.unit)

    def __rtruediv__(self, other: Any) -> "Quantity":
        if _is_real(other):
            return self._new(other / self.magnitude, 1 / self.unit)
        return NotImplemented

    def __floordiv__(self, other: Any) -> float:
        """How many whole *other* fit into this quantity (same dimension)."""
        if not isinstance(other, Quantity):
            return NotImplemented
        return math.floor(self._comparable(other, "divide")._ratio(other))

    def _ratio(self, other: "Quantity") -> float:
        return self.magnitude / other.m_as(self.unit)

    def __mod__(self, other: Any) -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        other = self._comparable(other, "divide")
        return self._new(math.fmod(self.magnitude, other.m_as(self.unit)), self.unit)

    def __pow__(self, power: Union[int, Fraction, float]) -> "Quantity":
        if isinstance(power, float):
            power = int(power) if power.is_integer() else Fraction(power).limit_denominator(12)
        if not isinstance(power, (int, Fraction)):
            return NotImplemented
        exponent = float(power) if isinstance(power, Fraction) else power
        return self._new(self.magnitude ** exponent, self.unit ** power)

    def sqrt(self) -> "Quantity":
        """Square root; the unit's dimension must have even exponents."""
        return self._new(math.sqrt(self.magnitude), self.unit ** Fraction(1, 2))

    def __neg__(self) -> "Quantity":
        return self._new(-self.magnitude, self.unit)

    def __pos__(self) -> "Quantity":
        return self

    def __abs__(self) -> "Quantity":
        return self._new(abs(self.magnitude), self.unit)

    def __round__(self, ndigits: Optional[int] = None) -> "Quantity":
        return self._new(round(self.magnitude, ndigits) if ndigits is not None else round(self.magnitude), self.unit)

    def __float__(self) -> float:
        if not self.dimensionless:
            raise DimensionalityError(f"only dimensionless quantities convert to float, not {self}")
        return float(self.magnitude * self.unit.factor)

    def __int__(self) -> int:
        return int(float(self))

    def __bool__(self) -> bool:
        return bool(self.magnitude)

    # Comparison -----------------------------------------------------------------

    def _comparable(self, other: Any, operation: str = "compare") -> "Quantity":
        if _is_real(other):
            if other == 0:
                return self._new(0, self.unit)  # comparing with zero is always meaningful
            other = self._new(other, DIMENSIONLESS_UNIT)
        if not isinstance(other, Quantity):
            raise TypeError(f"cannot {operation} Quantity and {type(other).__name__}")
        if self.dimension != other.dimension:
            raise DimensionalityError(self, other, operation=operation)
        return other

    def __eq__(self, other: object) -> bool:
        if _is_real(other):
            if other == 0:
                return self.magnitude == 0 and not self.unit.is_offset
            return self.dimensionless and isclose(self.magnitude * self.unit.factor, other)
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.dimension != other.dimension:
            return False
        return isclose(self._base_magnitude(), other._base_magnitude())

    def __lt__(self, other: Any) -> bool:
        other = self._comparable(other)
        return self.magnitude < other.magnitude

    def __hash__(self) -> int:
        return hash((self.dimension, clean_float(self._base_magnitude(), 10)))

    def isclose(self, other: "Quantity", rel_tol: float = 1e-9, abs_tol: float = 0.0) -> bool:
        """Approximate equality in the unit of *self*; *abs_tol* is in that unit."""
        other = self._comparable(other)
        return math.isclose(self.magnitude, other.m_as(self.unit), rel_tol=rel_tol, abs_tol=abs_tol)

    # Display --------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<Quantity({_plain(self.magnitude)}, {self.unit.symbol!r})>"

    def __str__(self) -> str:
        return format_quantity(self)

    def __format__(self, spec: str) -> str:
        """Format with a number spec plus optional flags.

        Trailing flags: ``L`` spells out the unit name, ``C`` applies
        :meth:`to_compact` first.  The rest is a normal format spec for the
        magnitude::

            >>> f"{Quantity(2.5, 'km'):.2f}"
            '2.50 km'
            >>> f"{Quantity(2.5, 'km'):.1fL}"
            '2.5 kilometres'
        """
        long_names = compact = False
        while spec and spec[-1] in "LC":
            if spec[-1] == "L":
                long_names = True
            else:
                compact = True
            spec = spec[:-1]
        q = self.to_compact() if compact else self
        number = format(q.magnitude, spec) if spec else _plain(q.magnitude)
        label = q.unit.long_name(plural=not _is_singular(q.magnitude)) if long_names else q.unit.symbol
        return _join_number_and_unit(number, label)


# ---------------------------------------------------------------------------
# Measurements with uncertainty
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Measurement:
    """A quantity with an absolute uncertainty (``9.81 ± 0.02 m/s²``).

    Uncertainties are propagated in quadrature for independent errors.
    """

    value: Quantity
    uncertainty: Quantity

    def __post_init__(self) -> None:
        if self.value.dimension != self.uncertainty.dimension:
            raise DimensionalityError(self.value, self.uncertainty, operation="combine")
        if self.uncertainty.magnitude < 0:
            raise ValueError("uncertainty must not be negative")

    @property
    def relative(self) -> float:
        """Relative uncertainty (0.01 for 1 %)."""
        if self.value.magnitude == 0:
            return math.inf
        spread = self.uncertainty.magnitude * self.uncertainty.unit.factor / self.value.unit.factor
        return abs(spread / self.value.magnitude)

    def to(self, unit: Union[str, Unit]) -> "Measurement":
        value = self.value.to(unit)
        delta_unit = value.registry.delta_unit(value.unit)
        uncertainty_base = self.uncertainty.magnitude * self.uncertainty.unit.factor
        return Measurement(value, Quantity(uncertainty_base / delta_unit.factor, delta_unit, value.registry))

    def __add__(self, other: "Measurement") -> "Measurement":
        if not isinstance(other, Measurement):
            return NotImplemented
        value = self.value + other.value
        other_u = other.uncertainty.magnitude * other.uncertainty.unit.factor / self.uncertainty.unit.factor
        u = math.hypot(self.uncertainty.magnitude, other_u)
        return Measurement(value, Quantity(u, self.uncertainty.unit, value.registry))

    def __mul__(self, other: "Measurement") -> "Measurement":
        if not isinstance(other, Measurement):
            return NotImplemented
        value = self.value * other.value
        rel = math.hypot(self.relative, other.relative)
        return Measurement(value, Quantity(abs(value.magnitude) * rel, value.unit, value.registry))

    def __str__(self) -> str:
        return self.format()

    def format(self, decimals: Optional[int] = None) -> str:
        """``"9.81 ± 0.02 m/s²"``; *decimals* defaults to the uncertainty's precision."""
        u = self.uncertainty.magnitude * self.uncertainty.unit.factor / self.value.unit.factor
        if decimals is None:
            decimals = 0
            if u > 0:
                # one significant figure, two when the leading digit is 1
                exponent = math.floor(math.log10(u))
                digits = 2 if int(u / 10.0 ** exponent) == 1 else 1
                decimals = max(0, digits - 1 - exponent)
        value = format_number(self.value.magnitude, decimals)
        uncertainty = format_number(u, decimals)
        return _join_number_and_unit(f"{value} ± {uncertainty}", self.value.unit.symbol)


# ---------------------------------------------------------------------------
# Parsing quantities from text
# ---------------------------------------------------------------------------

_SPACE_LIKE = "\u00a0\u2007\u2009\u202f"

# The numeric part at the start of a quantity.  Kept in sync with what
# parse_number() accepts; the alternatives are ordered so that the longest
# reading wins ("1 1/2" before "1", "10^3" before "10").
_QUANTITY_NUMBER_RE = re.compile(
    r"""
    (?P<number>
      [-+\u2212]?[ \t]*
      (?:
          10[ \t]*(?:\^|\*\*)[ \t]*[-+]?\d+
        | 10[⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+
        | \d+[ \t]+\d+[ \t]*[/\u2044][ \t]*\d+(?![\d.])
        | \d+[ \t]*[/\u2044][ \t]*\d+(?![\d.])
        | \d*[ \t]*[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅐⅛⅜⅝⅞⅑⅒]
        | (?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?(?:[eE][-+]?\d+)?
          (?:[ \t]*[×x·*][ \t]*10[ \t]*(?:(?:\^|\*\*)[ \t]*[-+]?\d+|[⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+))?
        | \.\d+(?:[eE][-+]?\d+)?
      )
    )
    """,
    re.VERBOSE,
)

# 5'3", 5′ 3″, 6', 11"
_FEET_INCHES_RE = re.compile(
    r"(?P<sign>[-\u2212])?[ \t]*"
    r"(?:(?P<feet>\d+(?:\.\d+)?)[ \t]*(?:'|′))?[ \t]*"
    r"(?:(?P<inches>\d+(?:\.\d+)?(?:[ \t]+\d+/\d+)?|\d+/\d+)[ \t]*(?:\"|″|''))?"
)

# One "<number> <unit>" piece of a compound quantity such as "1 h 30 min".
_COMPOUND_PART_RE = re.compile(
    r"(?:and[ \t]+)?"
    r"(?P<number>[-+\u2212]?\d+(?:\.\d+)?)(?![eE][-+]?\d)[ \t]*"
    r"(?P<unit>[^\W\d][^\s\d,]*|°[^\s\d,]*)"
    r"[ \t]*,?[ \t]*"
)

_PER_RE = re.compile(r"\s+per\s+")


def _normalise_space(text: str) -> str:
    for ch in _SPACE_LIKE:
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _unit_from_text(registry: UnitRegistry, text: str) -> Unit:
    """Resolve the unit part of a quantity; also accepts "metres per second"."""
    unit = registry.find(text)
    if unit is not None:
        return unit
    if _PER_RE.search(text):
        return registry.parse_unit(_PER_RE.sub("/", text))
    return registry.parse_unit(text)


def _split_number_and_unit(text: str, original: str) -> Tuple[float, str]:
    """Split ``"1.5 km/h"`` into ``(1.5, "km/h")``."""
    m = _QUANTITY_NUMBER_RE.match(text)
    if m is None or not m.group("number").strip(" \t+-\u2212"):
        raise ParseError("expected a number", original, 0)
    return parse_number(m.group("number")), text[m.end():].strip()


def _split_compound(text: str) -> Optional[List[Tuple[str, str]]]:
    """Split ``"5 ft 3 in"`` into ``[("5", "ft"), ("3", "in")]``; ``None`` if not compound."""
    parts = []
    pos = 0
    while pos < len(text):
        m = _COMPOUND_PART_RE.match(text, pos)
        if m is None or m.end() == pos:
            return None
        parts.append((m.group("number"), m.group("unit")))
        pos = m.end()
    return parts if len(parts) >= 2 else None


def _sum_compound(parts: List[Tuple[str, str]], registry: UnitRegistry, original: str) -> Quantity:
    units = [registry.get(unit_text) for _, unit_text in parts]
    first = units[0]
    for unit in units[1:]:
        if unit.dimension != first.dimension:
            raise DimensionalityError(first, unit, operation="combine")
    if any(unit.is_offset for unit in units):
        raise OffsetUnitError(f"compound quantities cannot use offset units: {original!r}")
    negative = False
    total = 0.0
    for index, (number_text, _) in enumerate(parts):
        value = parse_number(number_text)
        if value < 0 or number_text[0] in "+-\u2212":
            if index > 0:
                raise ParseError("only the first part of a compound quantity may have a sign", original)
            negative = value < 0
        total += abs(value) * units[index].factor
    last = units[-1]
    magnitude = clean_float(total / last.factor)
    return Quantity(-magnitude if negative else magnitude, last, registry)


def parse_quantity(
    text: Union[str, Quantity],
    registry: Optional[UnitRegistry] = None,
    *,
    default_unit: Union[str, Unit, None] = None,
) -> Quantity:
    """Parse a quantity written by a person.

    Supported forms include::

        "12.5 kg"   "1,250 m"   "-40 °C"   "3½ cups"   "1 1/2 tsp"
        "6.02e23 mol"   "1.5×10^3 J"   "100 km/h"   "9.81 m·s⁻²"
        "5 ft 3 in"   "1 h 30 min 15 s"   "2 lb, 4 oz"   "5'3\\""
        "250 metres per second"   "kg"  (one kilogram)

    A number without a unit is dimensionless unless *default_unit* is given.

    >>> parse_quantity("1 h 30 min").to("min")
    <Quantity(90, 'min')>
    >>> parse_quantity("5'3\\"")
    <Quantity(63, 'in')>
    """
    if isinstance(text, Quantity):
        return text
    reg = registry or get_registry()
    s = _normalise_space(text)
    if not s:
        raise ParseError("empty quantity", text)

    m = _FEET_INCHES_RE.fullmatch(s)
    if m and (m.group("feet") or m.group("inches")):
        sign = -1 if m.group("sign") else 1
        if not m.group("inches"):
            return Quantity(sign * float(m.group("feet")), reg.get("ft"), reg)
        inches = parse_number(m.group("inches"))
        if m.group("feet"):
            inches += 12 * float(m.group("feet"))
        return Quantity(sign * inches, reg.get("in"), reg)

    parts = _split_compound(s)
    if parts is not None:
        return _sum_compound(parts, reg, text)

    m = _QUANTITY_NUMBER_RE.match(s)
    if m is None or not m.group("number").strip(" \t+-\u2212"):
        # No number at all: "kg" means one kilogram.
        unit = reg.find(s)
        if unit is None:
            raise ParseError("expected a number", text, 0)
        return Quantity(1, unit, reg)

    magnitude, unit_text = _split_number_and_unit(s, text)
    if unit_text:
        unit = _unit_from_text(reg, unit_text)
    elif default_unit is not None:
        unit = reg.parse_unit(default_unit)
    else:
        unit = DIMENSIONLESS_UNIT
    return Quantity(magnitude, unit, reg)


def try_parse_quantity(text: str, registry: Optional[UnitRegistry] = None) -> Optional[Quantity]:
    """Like :func:`parse_quantity` but return ``None`` instead of raising."""
    try:
        return parse_quantity(text, registry)
    except UnitError:
        return None


_RANGE_RE = re.compile(
    r"(?P<low>.+?)[ \t]*"
    r"(?:–|—|\.\.|[ \t]to[ \t]|(?<=[\d½⅓⅔¼¾⅛⅜⅝⅞])[ \t]*-[ \t]*(?=[\d.\-\u2212]))"
    r"[ \t]*(?P<high>.+)"
)


def parse_range(
    text: str,
    registry: Optional[UnitRegistry] = None,
) -> Tuple[Quantity, Quantity]:
    """Parse a range such as ``"5–10 kg"``, ``"20 to 25 °C"`` or ``"1 m .. 150 cm"``.

    When only the upper end has a unit, the lower end takes the same unit.
    The lower end must not be greater than the upper end.

    >>> parse_range("5-10 kg")
    (<Quantity(5, 'kg')>, <Quantity(10, 'kg')>)
    """
    reg = registry or get_registry()
    s = _normalise_space(text)
    m = _RANGE_RE.fullmatch(s)
    if m is None:
        raise ParseError("expected a range such as '5–10 kg'", text)
    low_text, high_text = m.group("low").strip(), m.group("high").strip()
    high = parse_quantity(high_text, reg)
    low_magnitude, low_unit_text = _split_number_and_unit(low_text, text)
    if low_unit_text:
        low = parse_quantity(low_text, reg)
        if low.dimension != high.dimension:
            raise DimensionalityError(low, high, operation="form a range from")
    else:
        low = Quantity(low_magnitude, high.unit, reg)
    if low.m_as(high.unit) > high.magnitude:
        raise ParseError("range is reversed (lower end is greater than upper end)", text)
    return low, high


_PLUS_MINUS_RE = re.compile(r"[ \t]*(?:±|\+/-|\+-)[ \t]*")
_PARENTHESISED_RE = re.compile(r"\((?P<inner>[^()]*)\)[ \t]*(?P<unit>.*)")


def parse_measurement(text: str, registry: Optional[UnitRegistry] = None) -> Measurement:
    """Parse a value with uncertainty.

    Accepted forms: ``"9.81 ± 0.02 m/s^2"``, ``"9.81 m/s^2 ± 0.02 m/s^2"``,
    ``"(12.3 ± 0.4) mm"``, ``"12.3 +/- 0.4 mm"`` and relative uncertainties
    such as ``"5 V ± 2%"``.

    >>> str(parse_measurement("(12.3 ± 0.4) mm"))
    '12.3 ± 0.4 mm'
    """
    reg = registry or get_registry()
    s = _normalise_space(text)
    shared_unit = ""
    m = _PARENTHESISED_RE.fullmatch(s)
    if m:
        s, shared_unit = m.group("inner"), m.group("unit").strip()
    pieces = _PLUS_MINUS_RE.split(s)
    if len(pieces) != 2:
        raise ParseError("expected 'value ± uncertainty'", text)
    left, right = (p.strip() for p in pieces)
    value_magnitude, value_unit_text = _split_number_and_unit(left, text)

    if right.endswith("%"):
        unit = _unit_from_text(reg, value_unit_text or shared_unit) if (value_unit_text or shared_unit) else DIMENSIONLESS_UNIT
        value = Quantity(value_magnitude, unit, reg)
        relative = parse_number(right[:-1]) / 100
        delta_unit = reg.delta_unit(unit)
        spread = abs(value_magnitude) * relative * unit.factor / delta_unit.factor
        return Measurement(value, Quantity(spread, delta_unit, reg))

    spread_magnitude, spread_unit_text = _split_number_and_unit(right, text)
    unit_text = value_unit_text or spread_unit_text or shared_unit
    unit = _unit_from_text(reg, unit_text) if unit_text else DIMENSIONLESS_UNIT
    value = Quantity(value_magnitude, unit, reg)
    spread_unit = _unit_from_text(reg, spread_unit_text) if spread_unit_text else unit
    if spread_unit.dimension != unit.dimension:
        raise DimensionalityError(unit, spread_unit, operation="combine")
    spread_unit = reg.delta_unit(spread_unit)
    return Measurement(value, Quantity(abs(spread_magnitude), spread_unit, reg))


# ---------------------------------------------------------------------------
# Formatting quantities
# ---------------------------------------------------------------------------

# Symbols written directly after the number, without a space (SI brochure
# 5.4.3 makes an exception for the plane angle symbols; percent is
# conventionally attached in running text).
_NO_SPACE_SYMBOLS = frozenset({"%", "‰", "°", "′", "″"})


def _is_singular(number: Union[Number, str]) -> bool:
    """English uses the singular only for exactly one ("1 metre", "1.5 metres")."""
    if isinstance(number, str):
        return number.lstrip("+-") == "1"
    return abs(number) == 1


def _join_number_and_unit(number: str, label: str, separator: str = " ") -> str:
    if not label:
        return number
    if label in _NO_SPACE_SYMBOLS:
        return number + label
    return number + separator + label


def format_quantity(
    quantity: Union[Quantity, str],
    decimals: Optional[int] = None,
    sig: Optional[int] = None,
    *,
    unit: Union[str, Unit, None] = None,
    style: str = "short",
    auto_prefix: bool = False,
    binary: Optional[bool] = None,
    thousands: str = "",
    strip_zeros: bool = False,
    separator: str = " ",
) -> str:
    """Format a quantity for display.

    *decimals* / *sig* control the number as in :func:`format_number`.
    *unit* converts first; *auto_prefix* picks a readable prefix (see
    :meth:`Quantity.to_compact`).  *style* is ``"short"`` for symbols or
    ``"long"`` for spelled-out names.

    >>> format_quantity(Quantity(1234.5, "m"), 1, thousands=",")
    '1,234.5 m'
    >>> format_quantity(Quantity(1, "ft"), style="long")
    '1 foot'
    >>> format_quantity(Quantity(2.5, "ft"), style="long")
    '2.5 feet'
    >>> format_quantity(Quantity(0.0021, "A"), auto_prefix=True)
    '2.1 mA'
    """
    if isinstance(quantity, str):
        quantity = parse_quantity(quantity)
    if unit is not None:
        quantity = quantity.to(unit)
    if auto_prefix:
        quantity = quantity.to_compact(binary=binary)
    number = format_number(
        quantity.magnitude,
        decimals,
        sig,
        thousands=thousands,
        strip_zeros=strip_zeros,
    )
    if style == "short":
        label = quantity.unit.symbol
    elif style == "long":
        label = quantity.unit.long_name(plural=not _is_singular(number))
    else:
        raise ValueError(f"style must be 'short' or 'long', not {style!r}")
    return _join_number_and_unit(number, label, separator)


def format_compound(
    quantity: Quantity,
    units: Sequence[Union[str, Unit]],
    *,
    decimals: int = 0,
    style: str = "short",
    separator: str = " ",
    drop_leading_zeros: bool = False,
) -> str:
    """Split a quantity over several units, largest first.

    Every part but the last is a whole number; the last part is rounded to
    *decimals* places.

    >>> format_compound(Quantity(1.85, "m"), ["ft", "in"])
    '6 ft 1 in'
    >>> format_compound(Quantity(100, "min"), ["h", "min"])
    '1 h 40 min'
    >>> format_compound(Quantity(2.25, "lb"), ["lb", "oz"], style="long")
    '2 pounds 4 ounces'
    """
    if not units:
        raise ValueError("at least one unit is required")
    registry = quantity.registry
    resolved = [registry.parse_unit(u) for u in units]
    for unit in resolved:
        if unit.dimension != quantity.dimension:
            raise DimensionalityError(quantity, unit, operation="express")
        if unit.is_offset:
            raise OffsetUnitError(f"cannot split a quantity over the offset unit {unit.symbol!r}")
    for larger, smaller in zip(resolved, resolved[1:]):
        if smaller.factor >= larger.factor:
            raise ValueError("units must be given from largest to smallest")
    if quantity.unit.is_offset:
        raise OffsetUnitError(f"cannot split an absolute temperature ({quantity})")

    base = quantity.magnitude * quantity.unit.factor
    negative = base < 0
    remaining = abs(base)
    values: List[float] = []
    for unit in resolved[:-1]:
        count = math.floor(remaining / unit.factor + 1e-9)
        values.append(count)
        remaining = max(remaining - count * unit.factor, 0.0)
    values.append(round(remaining / resolved[-1].factor, decimals))

    # Rounding the last part may produce a whole unit of the part before it.
    for i in range(len(values) - 1, 0, -1):
        ratio = round(resolved[i - 1].factor / resolved[i].factor, 9)
        if values[i] > ratio:
            values[i] -= ratio
            values[i - 1] += 1

    if drop_leading_zeros:
        while len(values) > 1 and values[0] == 0:
            values.pop(0)
            resolved.pop(0)

    pieces = []
    last_index = len(values) - 1
    for index, (value, unit) in enumerate(zip(values, resolved)):
        number = format_number(value, decimals) if index == last_index else str(int(value))
        if style == "long":
            label = unit.long_name(plural=not _is_singular(number))
        else:
            label = unit.symbol
        pieces.append(_join_number_and_unit(number, label))
    text = separator.join(pieces)
    if negative and any(values):
        text = "-" + text
    return text


def format_duration(
    value: Union[Quantity, float],
    *,
    units: Sequence[str] = ("d", "h", "min", "s"),
    decimals: int = 0,
    style: str = "short",
) -> str:
    """Format a duration (a time quantity or a number of seconds).

    Leading parts that are zero are omitted.

    >>> format_duration(3725)
    '1 h 2 min 5 s'
    >>> format_duration(Quantity(90, "min"), style="long")
    '1 hour 30 minutes 0 seconds'
    """
    if not isinstance(value, Quantity):
        value = Quantity(value, "s")
    return format_compound(
        value,
        units,
        decimals=decimals,
        style=style,
        drop_leading_zeros=True,
    )


def format_fraction(quantity: Quantity, unit: Union[str, Unit, None] = None, *, max_denominator: int = 16) -> str:
    """Format with a fractional magnitude, as on a tape measure or in a recipe.

    >>> format_fraction(Quantity(0.6875, "in"))
    '11/16 in'
    >>> format_fraction(Quantity(3.5, "cup"))
    '3 1/2 cup'
    """
    if unit is not None:
        quantity = quantity.to(unit)
    return _join_number_and_unit(as_fraction(quantity.magnitude, max_denominator), quantity.unit.symbol)


# ---------------------------------------------------------------------------
# Unit systems
# ---------------------------------------------------------------------------

#: Preferred display units per system and dimension name, smallest first.
#: :func:`to_system` picks the largest unit the value is at least one of.
UNIT_SYSTEMS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "si": {
        "length": ("mm", "cm", "m", "km"),
        "mass": ("mg", "g", "kg", "t"),
        "time": ("ms", "s", "min", "h", "d"),
        "area": ("mm^2", "cm^2", "m^2", "ha", "km^2"),
        "volume": ("mL", "L", "m^3"),
        "velocity": ("m/s", "km/h"),
        "acceleration": ("m/s^2",),
        "force": ("N", "kN", "MN"),
        "energy": ("J", "kJ", "MJ", "GJ"),
        "power": ("W", "kW", "MW", "GW"),
        "pressure": ("Pa", "kPa", "MPa"),
        "temperature": ("°C",),
        "density": ("kg/m^3",),
        "information": ("B", "kB", "MB", "GB", "TB"),
    },
    "us": {
        "length": ("in", "ft", "yd", "mi"),
        "mass": ("oz", "lb", "ton"),
        "time": ("s", "min", "h", "d"),
        "area": ("in^2", "ft^2", "acre", "mi^2"),
        "volume": ("tsp", "tbsp", "floz", "cup", "qt", "gal"),
        "velocity": ("ft/s", "mph"),
        "force": ("lbf", "kip"),
        "energy": ("ft_lbf", "Btu", "therm"),
        "power": ("W", "hp"),
        "pressure": ("psi", "ksi"),
        "temperature": ("°F",),
        "density": ("lb/ft^3",),
    },
    "imperial": {
        "length": ("in", "ft", "yd", "mi"),
        "mass": ("oz", "lb", "st", "LT"),
        "time": ("s", "min", "h", "d"),
        "area": ("in^2", "ft^2", "acre", "mi^2"),
        "volume": ("imp_floz", "imp_pt", "imp_gal"),
        "velocity": ("mph",),
        "force": ("lbf",),
        "energy": ("Btu", "therm"),
        "power": ("W", "hp"),
        "pressure": ("psi",),
        "temperature": ("°F",),
    },
}


def to_system(quantity: Quantity, system: str) -> Quantity:
    """Express *quantity* in the customary unit of a unit system.

    >>> to_system(Quantity(1500, "m"), "si")
    <Quantity(1.5, 'km')>
    >>> to_system(Quantity(30, "cm"), "us").unit.symbol
    'in'
    """
    try:
        table = UNIT_SYSTEMS[system.lower()]
    except KeyError:
        raise ValueError(f"unknown unit system {system!r}; choose from {sorted(UNIT_SYSTEMS)}") from None
    name = quantity.dimension.name
    if name is None or name not in table:
        raise UnitError(f"the {system!r} system has no preferred unit for {quantity.dimension.describe()}")
    registry = quantity.registry
    ladder = [registry.parse_unit(symbol) for symbol in table[name]]
    if len(ladder) == 1 or ladder[0].is_offset:
        return quantity.to(ladder[0])
    size = abs(quantity.magnitude * quantity.unit.factor)
    chosen = ladder[0]
    for unit in ladder:
        if size >= unit.factor * (1 - 1e-12):
            chosen = unit
    return quantity.to(chosen)


def humanize(quantity: Quantity, system: str = "si", sig: int = 3) -> str:
    """A short, readable rendering in the customary units of *system*.

    >>> humanize(Quantity(123456, "m"))
    '123 km'
    >>> humanize(Quantity(2.5, "kg"), "us")
    '5.51 lb'
    """
    converted = to_system(quantity, system)
    return format_quantity(converted, sig=sig, strip_zeros=True)


# ---------------------------------------------------------------------------
# Plain-text tables
# ---------------------------------------------------------------------------

_NUMERIC_CELL_RE = re.compile(r"[-+]?(?:\d[\d,]*)?(?:\.\d+)?(?:[eE][-+]?\d+)?%?")


def _cell_text(value: Any, number_format: Optional[Callable[[Any], str]]) -> str:
    if value is None:
        return ""
    if isinstance(value, Quantity):
        return format_quantity(value)
    if _is_real(value):
        return number_format(value) if number_format is not None else _plain(value)
    return str(value)


def _is_numeric_cell(text: str) -> bool:
    return bool(text) and any(ch.isdigit() for ch in text) and bool(_NUMERIC_CELL_RE.fullmatch(text))


def _align_cell(text: str, width: int, how: str) -> str:
    if how == "right":
        return text.rjust(width)
    if how == "center":
        return text.center(width)
    return text.ljust(width)


def render_table(
    rows: Iterable[Sequence[Any]],
    headers: Optional[Sequence[Any]] = None,
    *,
    align: Optional[Sequence[str]] = None,
    number_format: Optional[Callable[[Any], str]] = None,
    title: Optional[str] = None,
    column_separator: str = " | ",
    rule_char: str = "-",
) -> str:
    """Render rows as a plain-text table.

    Columns whose cells are all numbers are right-aligned, others are
    left-aligned, unless *align* gives ``"left"``, ``"right"`` or
    ``"center"`` per column.  Trailing whitespace is removed from every line.

    >>> print(render_table([("water", 1000), ("air", 1.2)], ["fluid", "kg/m³"]))
    fluid | kg/m³
    ------+------
    water |  1000
    air   |   1.2
    """
    cells = [[_cell_text(value, number_format) for value in row] for row in rows]
    header_cells = [str(h) for h in headers] if headers is not None else None
    widths_from = [len(row) for row in cells] + ([len(header_cells)] if header_cells is not None else [])
    ncols = max(widths_from, default=0)
    if ncols == 0:
        return title or ""
    cells = [row + [""] * (ncols - len(row)) for row in cells]
    if header_cells is not None:
        header_cells += [""] * (ncols - len(header_cells))

    if align is None:
        align = []
        for i in range(ncols):
            column = [row[i] for row in cells if row[i]]
            numeric = bool(column) and all(_is_numeric_cell(c) for c in column)
            align.append("right" if numeric else "left")
    else:
        align = list(align)
        if len(align) != ncols:
            raise ValueError(f"align has {len(align)} entries for {ncols} columns")
        for how in align:
            if how not in ("left", "right", "center"):
                raise ValueError(f"invalid alignment {how!r}")

    table = ([header_cells] if header_cells is not None else []) + cells
    widths = [max(len(row[i]) for row in cells) for i in range(ncols)]

    def render_row(row: Sequence[str]) -> str:
        return column_separator.join(
            _align_cell(cell, width, how) for cell, width, how in zip(row, widths, align)
        ).rstrip()

    lines = []
    if title:
        total = sum(widths) + len(column_separator) * (ncols - 1)
        lines.append(title.center(total).rstrip())
    if header_cells is not None:
        lines.append(render_row(header_cells))
        junction = column_separator.replace(" ", rule_char).replace("|", "+")
        lines.append(junction.join(rule_char * w for w in widths))
    lines.extend(render_row(row) for row in cells)
    return "\n".join(lines)


def conversion_table(
    values: Iterable[Number],
    from_unit: Union[str, Unit],
    to_units: Sequence[Union[str, Unit]],
    *,
    decimals: int = 3,
    header: str = "symbol",
    thousands: str = "",
    registry: Optional[UnitRegistry] = None,
) -> str:
    """A table converting each of *values* from one unit into several others.

    *header* chooses the column titles: ``"symbol"`` (``km``) or ``"name"``
    (``kilometre``).

    >>> print(conversion_table([1, 10], "kg", ["lb", "oz"], decimals=2))
    kg |    lb |     oz
    ---+-------+-------
     1 |  2.20 |  35.27
    10 | 22.05 | 352.74
    """
    reg = registry or get_registry()
    source = reg.parse_unit(from_unit)
    targets = [reg.parse_unit(u) for u in to_units]
    for target in targets:
        if target.dimension != source.dimension:
            raise DimensionalityError(source, target, operation="tabulate")

    def title(unit: Unit) -> str:
        if header == "symbol":
            return unit.symbol
        if header == "name":
            return unit.long_name()
        raise ValueError(f"header must be 'symbol' or 'name', not {header!r}")

    headers = [title(source)] + [title(t) for t in targets]
    rows = []
    for value in values:
        row = [format_number(value, thousands=thousands)]
        for target in targets:
            converted = convert_value(value, source, target)
            row.append(format_number(converted, decimals, thousands=thousands))
        rows.append(row)
    return render_table(rows, headers)


def unit_table(dimension: Union[str, Dimension], registry: Optional[UnitRegistry] = None) -> str:
    """List the defined units of a dimension with their size in SI units.

    >>> print(unit_table("time").splitlines()[2])
    s          | second     |         1
    """
    reg = registry or get_registry()
    units = reg.units_for(dimension)
    if not units:
        return ""
    coherent = reg.coherent_unit(units[0].dimension)
    rows = [
        (u.symbol, u.name, format_engineering(u.factor, 6) if (u.factor >= 1e6 or u.factor < 1e-3) else _plain(u.factor))
        for u in units
    ]
    return render_table(rows, ["symbol", "name", f"in {coherent.symbol}"], align=["left", "left", "right"])
