from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app


class ParseBoundedIntArgTests(unittest.TestCase):
    def test_returns_default_when_missing(self) -> None:
        self.assertEqual(
            app.parse_bounded_int_arg({}, "limit", default=100, minimum=1, maximum=500),
            100,
        )

    def test_clamps_to_bounds(self) -> None:
        self.assertEqual(
            app.parse_bounded_int_arg({"limit": ["0"]}, "limit", default=100, minimum=1, maximum=500),
            1,
        )
        self.assertEqual(
            app.parse_bounded_int_arg({"limit": ["999"]}, "limit", default=100, minimum=1, maximum=500),
            500,
        )

    def test_rejects_non_integer_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            app.parse_bounded_int_arg({"limit": ["abc"]}, "limit", default=100, minimum=1, maximum=500)


if __name__ == "__main__":
    unittest.main()
