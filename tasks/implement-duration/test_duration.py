import unittest

from duration import format_duration, parse_duration


class ParseTest(unittest.TestCase):
    def test_basic_units(self):
        self.assertEqual(parse_duration("1w"), 604800)
        self.assertEqual(parse_duration("2d"), 172800)
        self.assertEqual(parse_duration("3h"), 10800)
        self.assertEqual(parse_duration("4m"), 240)
        self.assertEqual(parse_duration("5s"), 5)

    def test_combined_and_whitespace(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("1h 30m"), 5400)
        self.assertEqual(parse_duration("  2d   4h "), 187200)
        self.assertEqual(parse_duration("1w2d3h4m5s"), 788645)

    def test_case_insensitive(self):
        self.assertEqual(parse_duration("1H30M"), 5400)

    def test_decimal(self):
        self.assertEqual(parse_duration("1.5h"), 5400)
        self.assertEqual(parse_duration("0.5m"), 30)

    def test_decimal_rejected(self):
        for bad in ("1.25h", "0.1s", "1.h", ".5h"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_duration(bad)

    def test_bare_number_is_seconds(self):
        self.assertEqual(parse_duration("90"), 90)
        self.assertEqual(parse_duration("0"), 0)

    def test_negative(self):
        self.assertEqual(parse_duration("-1h30m"), -5400)
        self.assertEqual(parse_duration("-90"), -90)

    def test_invalid(self):
        for bad in ("", "   ", "h", "1x", "30m1h", "1h1h", "1h 30", "1h-30m", "--1h", "1 h"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_duration(bad)


class FormatTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(format_duration(3723), "1h2m3s")
        self.assertEqual(format_duration(3600), "1h")
        self.assertEqual(format_duration(90061), "1d1h1m1s")
        self.assertEqual(format_duration(604800), "7d")

    def test_zero_and_negative(self):
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(-90), "-1m30s")

    def test_type_errors(self):
        for bad in (1.5, "60", True, None):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                format_duration(bad)


class RoundTripTest(unittest.TestCase):
    def test_round_trip(self):
        for n in (0, 1, 59, 60, 61, 3599, 3600, 86399, 86400, 90061, 1_000_000, -1, -3725):
            with self.subTest(n=n):
                self.assertEqual(parse_duration(format_duration(n)), n)


if __name__ == "__main__":
    unittest.main()
