"""Tests for unitlib."""

import unittest

import unitlib
from unitlib import (
    Dimension,
    Quantity,
    UnitError,
    UnitRegistry,
    best_prefix,
    conversion_table,
    format_compound,
    format_duration,
    format_number,
    format_quantity,
    parse_measurement,
    parse_number,
    parse_quantity,
    parse_range,
    render_table,
    round_sig,
    to_system,
)

REG = unitlib.get_registry()


def sig9(x):
    """Compare floats to nine significant figures."""
    return float(f"{x:.9g}")


def attempt(fn):
    """Run fn() and return its result, or a short description of the error."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - table-driven tests report errors as values
        return f"{type(exc).__name__}: {exc}"


class UnitlibTestCase(unittest.TestCase):
    maxDiff = None


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


class NumberTest(UnitlibTestCase):
    def test_round_sig_table(self):
        cases = [
            (123456, 1),
            (123456, 2),
            (123456, 3),
            (123456, 4),
            (0.00123456, 1),
            (0.00123456, 2),
            (0.00123456, 3),
            (-987.654, 1),
            (-987.654, 2),
            (-987.654, 3),
            (299792458, 3),
            (6.02214076e23, 4),
            (1.602176634e-19, 3),
            (101325, 2),
            (0.000999, 2),
            (1, 3),
            (42, 5),
            (7.389056, 3),
            (3.14159265, 2),
            (2.718281828, 4),
            (0.0456, 1),
            (86400, 1),
        ]
        expected = [
            (123456, 1, 100000.0),
            (123456, 2, 120000.0),
            (123456, 3, 123000.0),
            (123456, 4, 123500.0),
            (0.00123456, 1, 0.001),
            (0.00123456, 2, 0.0012),
            (0.00123456, 3, 0.00123),
            (-987.654, 1, -1000.0),
            (-987.654, 2, -990.0),
            (-987.654, 3, -988.0),
            (299792458, 3, 300000000.0),
            (6.02214076e23, 4, 6.022e23),
            (1.602176634e-19, 3, 1.6e-19),
            (101325, 2, 100000.0),
            (0.000999, 2, 0.001),
            (1, 3, 1.0),
            (42, 5, 42.0),
            (7.389056, 3, 7.39),
            (3.14159265, 2, 3.1),
            (2.718281828, 4, 2.718),
            (0.0456, 1, 0.05),
            (86400, 1, 90000.0),
        ]
        self.assertEqual([(x, sig, round_sig(x, sig)) for x, sig in cases], expected)

    def test_format_number_significant_figures(self):
        cases = [
            (123456, 3),
            (0.000123456, 3),
            (9.80665, 3),
            (1013.25, 2),
            (2.5, 4),
            (0.1 + 0.2, 2),
            (1609.344, 4),
            (6.62607015e-34 * 1e34, 3),
            (343.2, 2),
            (0.0254, 1),
        ]
        self.assertEqual(
            [format_number(x, sig=sig) for x, sig in cases],
            ["123000", "0.000123", "9.81", "1000", "2.500", "0.30", "1609", "6.63", "340", "0.03"],
        )
        self.assertEqual(
            [
                format_quantity(Quantity(9.80665, "m/s^2"), sig=3),
                format_quantity(Quantity(1609.344, "m"), sig=2),
                format_quantity(Quantity(0.45359237, "kg"), sig=4),
            ],
            ["9.81 m/s²", "1600 m", "0.4536 kg"],
        )

    def test_parse_number_fractions(self):
        samples = [
            "½",
            "3½",
            "3 ½",
            "1 1/2",
            "3/4",
            "-3/4",
            "−2½",
            "-1 1/4",
            "+2 3/8",
            "-⅛",
            "10 ⅝",
            "−7/8",
            "-12 1/16",
        ]
        self.assertEqual(
            [(text, parse_number(text)) for text in samples],
            [
                ("½", 0.5),
                ("3½", 3.5),
                ("3 ½", 3.5),
                ("1 1/2", 1.5),
                ("3/4", 0.75),
                ("-3/4", -0.75),
                ("−2½", -2.5),
                ("-1 1/4", -1.25),
                ("+2 3/8", 2.375),
                ("-⅛", -0.125),
                ("10 ⅝", 10.625),
                ("−7/8", -0.875),
                ("-12 1/16", -12.0625),
            ],
        )

    def test_parse_quantity_negative_fractions(self):
        samples = [("-¾ in", "mm"), ("−1 1/2 ft", "in"), ("−2½ min", "s"), ("-1 3/4 cup", "floz")]
        self.assertEqual(
            {text: round(parse_quantity(text).m_as(unit), 6) for text, unit in samples},
            {"-¾ in": -19.05, "−1 1/2 ft": -18.0, "−2½ min": -150.0, "-1 3/4 cup": -14.0},
        )


# ---------------------------------------------------------------------------
# Dimensions and prefixes
# ---------------------------------------------------------------------------


class DimensionAndPrefixTest(UnitlibTestCase):
    def test_dimension_algebra_and_names(self):
        force = Dimension.parse("M L T^-2")
        self.assertEqual(str(force), "L·M·T⁻²")
        self.assertEqual(Dimension.parse("L·T⁻²"), Dimension.parse("[length]/[time]^2"))
        self.assertEqual((force * Dimension.parse("L")).name, "energy")
        self.assertEqual((force / Dimension.parse("L^2")).name, "pressure")
        self.assertEqual(Dimension.parse("L^2").root(2), Dimension.parse("L"))
        self.assertTrue((force / force).dimensionless)
        names = {
            expr: REG.parse_unit(expr).dimension.describe()
            for expr in ["N", "J/s", "Pa*m^3", "V*A", "C/s", "Ω*S", "kg/m^3", "lm/m^2", "mol/L", "bit/s", "Wb/m^2"]
        }
        self.assertEqual(
            names,
            {
                "N": "force",
                "J/s": "power",
                "Pa*m^3": "energy",
                "V*A": "power",
                "C/s": "current",
                "Ω*S": "dimensionless",
                "kg/m^3": "density",
                "lm/m^2": "illuminance",
                "mol/L": "concentration",
                "bit/s": "data rate",
                "Wb/m^2": "magnetic flux density",
            },
        )

    def test_best_prefix_boundaries(self):
        cases = [
            (1, False),
            (999, False),
            (1000, False),
            (1001, False),
            (999999, False),
            (1e6, False),
            (1e9, False),
            (0.001, False),
            (0.000999, False),
            (1e-6, False),
            (4700, False),
            (0.047, False),
            (2.2e-11, False),
            (1023, True),
            (1024, True),
            (1048576, True),
            (1536, True),
        ]
        self.assertEqual(
            [(value, binary, best_prefix(value, binary=binary).symbol) for value, binary in cases],
            [
                (1, False, ""),
                (999, False, ""),
                (1000, False, "k"),
                (1001, False, "k"),
                (999999, False, "k"),
                (1e6, False, "M"),
                (1e9, False, "G"),
                (0.001, False, "m"),
                (0.000999, False, "µ"),
                (1e-6, False, "µ"),
                (4700, False, "k"),
                (0.047, False, "m"),
                (2.2e-11, False, "p"),
                (1023, True, ""),
                (1024, True, "Ki"),
                (1048576, True, "Mi"),
                (1536, True, "Ki"),
            ],
        )

    def test_auto_prefix_formatting(self):
        samples = [
            (1000, "W"),
            (1e6, "Hz"),
            (0.001, "s"),
            (2.5e9, "Hz"),
            (4700, "Ω"),
            (0.000047, "F"),
            (1024, "B"),
            (1e-9, "m"),
            (1500, "m"),
            (1000, "kg"),
            (0.0033, "A"),
            (1e5, "Pa"),
            (2048, "B"),
            (0.001, "g"),
        ]
        self.assertEqual(
            [format_quantity(Quantity(value, unit), auto_prefix=True) for value, unit in samples],
            ["1 kW", "1 MHz", "1 ms", "2.5 GHz", "4.7 kΩ", "47 µF", "1 KiB", "1 nm", "1.5 km", "1 Mg", "3.3 mA", "100 kPa", "2 KiB", "1 mg"],
        )


# ---------------------------------------------------------------------------
# Unit table and lookups
# ---------------------------------------------------------------------------


class UnitTableTest(UnitlibTestCase):
    def test_common_conversions(self):
        cases = [
            (1, "mi", "km"),
            (1, "lb", "kg"),
            (1, "gal", "L"),
            (1, "kWh", "MJ"),
            (1, "atm", "kPa"),
            (1, "nmi", "m"),
            (1, "kn", "km/h"),
            (1, "acre", "m^2"),
            (1, "floz", "mL"),
            (1, "Btu", "kJ"),
            (1, "psi", "kPa"),
            (1, "mmHg", "Pa"),
            (1, "ly", "km"),
            (1, "oz", "g"),
            (1, "st", "kg"),
            (1, "cup", "mL"),
            (1, "imp_pt", "L"),
            (1, "bar", "psi"),
            (180, "deg", "rad"),
            (60, "mph", "m/s"),
            (1, "GiB", "MB"),
            (1, "kgf", "lbf"),
        ]
        self.assertEqual(
            {f"{v} {a} -> {b}": sig9(Quantity(v, a).m_as(b)) for v, a, b in cases},
            {
                "1 mi -> km": 1.609344,
                "1 lb -> kg": 0.45359237,
                "1 gal -> L": 3.78541178,
                "1 kWh -> MJ": 3.6,
                "1 atm -> kPa": 101.325,
                "1 nmi -> m": 1852.0,
                "1 kn -> km/h": 1.852,
                "1 acre -> m^2": 4046.85642,
                "1 floz -> mL": 29.5735296,
                "1 Btu -> kJ": 1.05505585,
                "1 psi -> kPa": 6.89475729,
                "1 mmHg -> Pa": 133.322387,
                "1 ly -> km": 9.46073047e12,
                "1 oz -> g": 28.3495231,
                "1 st -> kg": 6.35029318,
                "1 cup -> mL": 236.588237,
                "1 imp_pt -> L": 0.56826125,
                "1 bar -> psi": 14.5037738,
                "180 deg -> rad": 3.14159265,
                "60 mph -> m/s": 26.8224,
                "1 GiB -> MB": 1073.74182,
                "1 kgf -> lbf": 2.20462262,
            },
        )

    def test_power_units_in_watts(self):
        units = ["W", "kW", "MW", "mW", "hp", "PS", "hp_e", "TR", "Btu/h", "Btu/s", "ft_lbf/s", "cal/s", "kcal/h", "erg/s"]
        self.assertEqual(
            {unit: sig9(Quantity(1, unit).m_as("W")) for unit in units},
            {
                "W": 1.0,
                "kW": 1000.0,
                "MW": 1000000.0,
                "mW": 0.001,
                "hp": 745.699872,
                "PS": 735.49875,
                "hp_e": 746.0,
                "TR": 3516.85284,
                "Btu/h": 0.29307107,
                "Btu/s": 1055.05585,
                "ft_lbf/s": 1.35581795,
                "cal/s": 4.184,
                "kcal/h": 1.16222222,
                "erg/s": 1e-07,
            },
        )
    def test_engine_power_conversion(self):
        conversions = {
            "150 hp in kW": (150, "hp", "kW"),
            "300 PS in hp": (300, "PS", "hp"),
            "1 hp in ft_lbf/s": (1, "hp", "ft_lbf/s"),
            "100 kW in hp": (100, "kW", "hp"),
            "85 hp in PS": (85, "hp", "PS"),
            "1500 hp in MW": (1500, "hp", "MW"),
            "0.5 hp in W": (0.5, "hp", "W"),
            "200 hp in Btu/h": (200, "hp", "Btu/h"),
        }
        self.assertEqual(
            {label: round(Quantity(v, src).m_as(dst), 3) for label, (v, src, dst) in conversions.items()},
            {
                "150 hp in kW": 111.855,
                "300 PS in hp": 295.896,
                "1 hp in ft_lbf/s": 550.0,
                "100 kW in hp": 134.102,
                "85 hp in PS": 86.179,
                "1500 hp in MW": 1.119,
                "0.5 hp in W": 372.85,
                "200 hp in Btu/h": 508886.716,
            },
        )
    def test_plural_unit_names(self):
        reg = UnitRegistry()
        names = [
            "metres",
            "feet",
            "inches",
            "miles",
            "pounds",
            "ounces",
            "hours",
            "minutes",
            "gausses",
            "centuries",
            "kilometres",
            "millennia",
            "degrees Celsius",
            "nautical miles",
            "light-years",
            "pints",
            "bushels",
            "inches of mercury",
            "Inches",
        ]

        def symbol(name):
            unit = reg.find(name)
            return unit.symbol if unit is not None else None

        self.assertEqual(
            [(name, symbol(name)) for name in names],
            [
                ("metres", "m"),
                ("feet", "ft"),
                ("inches", "in"),
                ("miles", "mi"),
                ("pounds", "lb"),
                ("ounces", "oz"),
                ("hours", "h"),
                ("minutes", "min"),
                ("gausses", "G"),
                ("centuries", "century"),
                ("kilometres", "km"),
                ("millennia", "millennium"),
                ("degrees Celsius", "°C"),
                ("nautical miles", "nmi"),
                ("light-years", "ly"),
                ("pints", "pt"),
                ("bushels", "bu"),
                ("inches of mercury", "inHg"),
                ("Inches", "in"),
            ],
        )

    def test_parse_quantity_with_plural_names(self):
        samples = [
            ("12 inches", "ft"),
            ("6 feet 2 inches", "in"),
            ("3 inches", "cm"),
            ("2 feet 6 inches", "m"),
            ("1 foot", "in"),
        ]
        self.assertEqual(
            {text: attempt(lambda: round(parse_quantity(text).m_as(unit), 6)) for text, unit in samples},
            {
                "12 inches": 1.0,
                "6 feet 2 inches": 74.0,
                "3 inches": 7.62,
                "2 feet 6 inches": 0.762,
                "1 foot": 12.0,
            },
        )


# ---------------------------------------------------------------------------
# Unit expressions
# ---------------------------------------------------------------------------


class UnitExpressionTest(UnitlibTestCase):
    def test_unit_expression_forms(self):
        joule = REG.get("J")
        forms = [
            "kg·m²·s⁻²",
            "kg*m**2*s**-2",
            "kg m^2 s^-2",
            "(kg*m^2)/s^2",
            "N m",
            "N*m",
            "W*s",
            "kg m2/s2",
            "Pa·m³",
        ]
        self.assertEqual([(form, REG.parse_unit(form) == joule) for form in forms], [(form, True) for form in forms])
        prefixed = ["µs", "us", "μs", "KiB", "kilometre", "mA", "dam", "hPa", "kWh", "mebibytes"]
        self.assertEqual(
            {name: sig9(REG.get(name).factor) for name in prefixed},
            {
                "µs": 1e-6,
                "us": 1e-6,
                "μs": 1e-6,
                "KiB": 8192.0,
                "kilometre": 1000.0,
                "mA": 0.001,
                "dam": 10.0,
                "hPa": 100.0,
                "kWh": 3600000.0,
                "mebibytes": 8388608.0,
            },
        )
        self.assertEqual(REG.parse_unit("kg·m²/s²").symbol, "kg·m²/s²")
        self.assertEqual(REG.parse_unit("J/(kg*K)").symbol, "J/(kg·K)")

    def test_chained_division(self):
        expressions = ["J/kg/K", "m/s/s", "W/m^2/K", "mol/L/s", "Btu/h/ft^2", "kg/m/s", "kWh/m^2/yr", "L/min/m^2"]

        def describe(expr):
            unit = REG.parse_unit(expr)
            return (str(unit.dimension), unit.dimension.describe(), sig9(unit.factor))

        self.assertEqual(
            [(expr, describe(expr)) for expr in expressions],
            [
                ("J/kg/K", ("L²·T⁻²·Θ⁻¹", "specific heat capacity", 1.0)),
                ("m/s/s", ("L·T⁻²", "acceleration", 1.0)),
                ("W/m^2/K", ("M·T⁻³·Θ⁻¹", "heat transfer coefficient", 1.0)),
                ("mol/L/s", ("L⁻³·T⁻¹·N", "L⁻³·T⁻¹·N", 1000.0)),
                ("Btu/h/ft^2", ("M·T⁻³", "irradiance", 3.15459075)),
                ("kg/m/s", ("L⁻¹·M·T⁻¹", "dynamic viscosity", 1.0)),
                ("kWh/m^2/yr", ("M·T⁻³", "irradiance", 0.114077116)),
                ("L/min/m^2", ("L·T⁻¹", "velocity", 1.66666667e-05)),
            ],
        )

    def test_specific_heat_conversion(self):
        conversions = {
            "water, J/(kg*K)": (4.186, "kJ/kg/K", "J/(kg*K)"),
            "water, Btu/(lb*degR)": (4.186, "kJ/kg/K", "Btu/(lb*degR)"),
            "air, J/(g*K)": (1005, "J/kg/K", "J/(g*K)"),
            "1 Btu/lb/degR": (1, "Btu/lb/degR", "J/(kg*K)"),
            "1 cal/g/delta_degC": (1, "cal/g/delta_degC", "J/(kg*K)"),
            "aluminium, cal/(g*delta_degC)": (897, "J/kg/K", "cal/(g*delta_degC)"),
        }
        self.assertEqual(
            {label: attempt(lambda: round(Quantity(v, src).m_as(dst), 6)) for label, (v, src, dst) in conversions.items()},
            {
                "water, J/(kg*K)": 4186.0,
                "water, Btu/(lb*degR)": 0.999809,
                "air, J/(g*K)": 1.005,
                "1 Btu/lb/degR": 4186.8,
                "1 cal/g/delta_degC": 4184.0,
                "aluminium, cal/(g*delta_degC)": 0.214388,
            },
        )

# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------


class QuantityTest(UnitlibTestCase):
    def test_quantity_arithmetic(self):
        total = Quantity(5, "km") + Quantity(300, "m")
        self.assertEqual((total.unit.symbol, round(total.magnitude, 9)), ("km", 5.3))
        speed = Quantity(10, "m") / Quantity(4, "s")
        self.assertEqual(speed.unit.symbol, "m/s")
        self.assertEqual(round(speed.m_as("km/h"), 9), 9.0)
        work = (Quantity(3, "N") * Quantity(2, "m")).simplify()
        self.assertEqual((work.unit.symbol, work.magnitude), ("J", 6))
        area = Quantity(3, "m") ** 2
        self.assertEqual(round(area.m_as("ft^2"), 6), 96.875194)
        self.assertEqual(Quantity(1000, "m"), Quantity(1, "km"))
        self.assertNotEqual(Quantity(1, "kg"), Quantity(1, "L"))
        self.assertEqual(round((Quantity(1, "ft") - Quantity(6, "in")).magnitude, 9), 0.5)
        self.assertEqual(round(sum([Quantity(1, "h"), Quantity(30, "min"), Quantity(90, "s")]).m_as("min"), 9), 91.5)
        self.assertEqual(round(Quantity(2, "m^2").sqrt().m_as("cm"), 6), 141.421356)
        with self.assertRaises(UnitError):
            Quantity(1, "m") + Quantity(1, "s")

    def test_temperature_scale_table(self):
        rows = []
        for celsius in range(-40, 101, 10):
            q = Quantity(celsius, "°C")
            rows.append(
                (
                    celsius,
                    round(q.m_as("°F"), 6),
                    round(q.m_as("K"), 6),
                    round(Quantity(celsius + 273.15, "K").m_as("°C"), 6),
                )
            )
        self.assertEqual(
            rows,
            [
                (-40, -40.0, 233.15, -40.0),
                (-30, -22.0, 243.15, -30.0),
                (-20, -4.0, 253.15, -20.0),
                (-10, 14.0, 263.15, -10.0),
                (0, 32.0, 273.15, 0.0),
                (10, 50.0, 283.15, 10.0),
                (20, 68.0, 293.15, 20.0),
                (30, 86.0, 303.15, 30.0),
                (40, 104.0, 313.15, 40.0),
                (50, 122.0, 323.15, 50.0),
                (60, 140.0, 333.15, 60.0),
                (70, 158.0, 343.15, 70.0),
                (80, 176.0, 353.15, 80.0),
                (90, 194.0, 363.15, 90.0),
                (100, 212.0, 373.15, 100.0),
            ],
        )

    def test_fahrenheit_to_celsius(self):
        readings = ["98.6 °F", "32 °F", "-40 °F", "451 °F", "0 °F", "212 °F", "350 °F", "375 °F", "400 °F", "425 °F", "-459.67 °F", "68 °F"]
        self.assertEqual(
            {text: round(parse_quantity(text).m_as("°C"), 6) for text in readings},
            {
                "98.6 °F": 37.0,
                "32 °F": 0.0,
                "-40 °F": -40.0,
                "451 °F": 232.777778,
                "0 °F": -17.777778,
                "212 °F": 100.0,
                "350 °F": 176.666667,
                "375 °F": 190.555556,
                "400 °F": 204.444444,
                "425 °F": 218.333333,
                "-459.67 °F": -273.15,
                "68 °F": 20.0,
            },
        )
    def test_sort_mixed_lengths(self):
        texts = ["1 mi", "1500 m", "0.9 km", "5000 ft", "0.5 nmi", "1200 yd", "120000 cm", "3 fur", "1 ch", "2 hand", "800 m", "0.75 mi"]
        lengths = [parse_quantity(text) for text in texts]
        self.assertEqual(
            [str(q) for q in sorted(lengths)],
            ["2 hand", "1 ch", "3 fur", "800 m", "0.9 km", "0.5 nmi", "1200 yd", "120000 cm", "0.75 mi", "1500 m", "5000 ft", "1 mi"],
        )
    def test_ordering_operators(self):
        checks = {
            "1 km > 900 m": lambda: Quantity(1, "km") > Quantity(900, "m"),
            "2 lb < 1 kg": lambda: Quantity(2, "lb") < Quantity(1, "kg"),
            "1 h > 59 min": lambda: Quantity(1, "h") > Quantity(59, "min"),
            "12 in <= 1 ft": lambda: Quantity(12, "in") <= Quantity(1, "ft"),
            "3 ft >= 1 yd": lambda: Quantity(3, "ft") >= Quantity(1, "yd"),
            "1 gal > 4 L": lambda: Quantity(1, "gal") > Quantity(4, "L"),
            "1 nmi > 1 mi": lambda: Quantity(1, "nmi") > Quantity(1, "mi"),
            "100 mph > 150 km/h": lambda: Quantity(100, "mph") > Quantity(150, "km/h"),
            "1 acre < 4000 m^2": lambda: Quantity(1, "acre") < Quantity(4000, "m^2"),
            "1 atm > 1 bar": lambda: Quantity(1, "atm") > Quantity(1, "bar"),
            "max mass": lambda: str(max([Quantity(1.2, "lb"), Quantity(500, "g"), Quantity(16.5, "oz")])),
            "min volume": lambda: str(min([Quantity(2, "L"), Quantity(0.5, "gal"), Quantity(70, "floz")])),
        }
        self.assertEqual(
            {name: attempt(check) for name, check in checks.items()},
            {
                "1 km > 900 m": True,
                "2 lb < 1 kg": True,
                "1 h > 59 min": True,
                "12 in <= 1 ft": True,
                "3 ft >= 1 yd": True,
                "1 gal > 4 L": False,
                "1 nmi > 1 mi": True,
                "100 mph > 150 km/h": True,
                "1 acre < 4000 m^2": False,
                "1 atm > 1 bar": True,
                "max mass": "1.2 lb",
                "min volume": "0.5 gal",
            },
        )


# ---------------------------------------------------------------------------
# Parsing and formatting
# ---------------------------------------------------------------------------


class ParseAndFormatTest(UnitlibTestCase):
    def test_parse_and_format_quantities(self):
        self.assertEqual(parse_quantity("1,250.5 kg").magnitude, 1250.5)
        self.assertEqual(round(parse_quantity("3 1/2 cup").m_as("floz"), 9), 28.0)
        self.assertEqual(round(parse_quantity("1 h 30 min 15 s").m_as("s"), 9), 5415.0)
        self.assertEqual(repr(parse_quantity("5'3\"")), "<Quantity(63, 'in')>")
        self.assertEqual(round(parse_quantity("250 metres per second").m_as("km/h"), 9), 900.0)
        low, high = parse_range("5–10 kg")
        self.assertEqual((low.magnitude, low.unit.symbol, high.magnitude, high.unit.symbol), (5, "kg", 10, "kg"))
        self.assertEqual(str(parse_measurement("9.81 ± 0.02 m/s^2")), "9.81 ± 0.02 m/s²")
        self.assertEqual(format_quantity(Quantity(2.5, "km"), 2), "2.50 km")
        self.assertEqual(format_quantity(Quantity(2.5, "km"), style="long"), "2.5 kilometres")
        self.assertEqual(format_quantity(Quantity(1, "ft"), style="long"), "1 foot")
        self.assertEqual(format_quantity(Quantity(1234567.891, "m"), 1, thousands=","), "1,234,567.9 m")
        self.assertEqual(to_system(Quantity(30, "cm"), "us").unit.symbol, "in")
        self.assertEqual(format_compound(Quantity(1.85, "m"), ["ft", "in"]), "6 ft 1 in")
        self.assertEqual(format_duration(3725), "1 h 2 min 5 s")

    def test_format_compound_carries(self):
        inches = [11.4, 11.6, 71.9999, 35.97, 47.6, 59.99, 0.4, 0.6, 12, 100.2, 143.7, -23.8]
        results = [format_compound(Quantity(value, "in"), ["ft", "in"]) for value in inches]
        results.append(format_compound(Quantity(1.999, "lb"), ["lb", "oz"]))
        results.append(format_compound(Quantity(3.9999, "yd"), ["yd", "ft", "in"]))
        self.assertEqual(
            results,
            [
                "0 ft 11 in",
                "1 ft 0 in",
                "6 ft 0 in",
                "3 ft 0 in",
                "4 ft 0 in",
                "5 ft 0 in",
                "0 ft 0 in",
                "0 ft 1 in",
                "1 ft 0 in",
                "8 ft 4 in",
                "12 ft 0 in",
                "-2 ft 0 in",
                "2 lb 0 oz",
                "4 yd 0 ft 0 in",
            ],
        )

    def test_format_duration_carries(self):
        seconds = [59.7, 119.6, 3599.6, 7199.6, 86399.7, 3600, 61.2, 0.4, 172799.9, 3661, 45296.4, 359999.6]
        self.assertEqual(
            [(s, format_duration(s)) for s in seconds],
            [
                (59.7, "1 min 0 s"),
                (119.6, "2 min 0 s"),
                (3599.6, "1 h 0 min 0 s"),
                (7199.6, "2 h 0 min 0 s"),
                (86399.7, "1 d 0 h 0 min 0 s"),
                (3600, "1 h 0 min 0 s"),
                (61.2, "1 min 1 s"),
                (0.4, "0 s"),
                (172799.9, "2 d 0 h 0 min 0 s"),
                (3661, "1 h 1 min 1 s"),
                (45296.4, "12 h 34 min 56 s"),
                (359999.6, "4 d 4 h 0 min 0 s"),
            ],
        )


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class TableTest(UnitlibTestCase):
    def test_conversion_table_layout(self):
        table = conversion_table([0.4, 1, 3, 5, 10, 21.0975, 42.195, 100], "km", ["mi", "nmi", "ft"], header="name")
        self.assertEqual(
            table,
            "kilometre |   mile | nautical mile |       foot\n"
            "----------+--------+---------------+-----------\n"
            "      0.4 |  0.249 |         0.216 |   1312.336\n"
            "        1 |  0.621 |         0.540 |   3280.840\n"
            "        3 |  1.864 |         1.620 |   9842.520\n"
            "        5 |  3.107 |         2.700 |  16404.199\n"
            "       10 |  6.214 |         5.400 |  32808.399\n"
            "  21.0975 | 13.109 |        11.392 |  69217.520\n"
            "   42.195 | 26.219 |        22.783 | 138435.039\n"
            "      100 | 62.137 |        53.996 | 328083.990",
        )

    def test_render_table_long_headers(self):
        rows = [
            ("aluminium", 2700, 660.3, 69),
            ("copper", 8960, 1084.6, 117),
            ("iron", 7874, 1538, 211),
            ("lead", 11340, 327.5, 16),
            ("nickel", 8908, 1455, 200),
            ("titanium", 4506, 1668, 116),
            ("zinc", 7140, 419.5, 108),
        ]
        table = render_table(rows, ["material", "density (kg/m³)", "melting point (°C)", "E (GPa)"], title="Metals")
        self.assertEqual(
            table,
            "                          Metals\n"
            "material  | density (kg/m³) | melting point (°C) | E (GPa)\n"
            "----------+-----------------+--------------------+--------\n"
            "aluminium |            2700 |              660.3 |      69\n"
            "copper    |            8960 |             1084.6 |     117\n"
            "iron      |            7874 |               1538 |     211\n"
            "lead      |           11340 |              327.5 |      16\n"
            "nickel    |            8908 |               1455 |     200\n"
            "titanium  |            4506 |               1668 |     116\n"
            "zinc      |            7140 |              419.5 |     108",
        )


if __name__ == "__main__":
    unittest.main()
