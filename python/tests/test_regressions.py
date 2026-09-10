"""Regressions for source positions and Python's actual lexical lookup rules."""

from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from anti_slop import check_source  # noqa: E402


class SourceAndScopeTests(unittest.TestCase):
    def test_non_newline_separators_do_not_change_diagnostic_positions(self):
        for separator in ["\u2028", "\u2029", "\x0b", "\x0c"]:
            with self.subTest(separator=repr(separator)):
                source = f"from typing import cast\ntext = '{separator}'; user = cast(User, raw)\n"
                diagnostic = check_source(source)[0]
                self.assertEqual(diagnostic.code, "ASPY003")
                self.assertEqual(diagnostic.line, 2)
                self.assertEqual(
                    diagnostic.column, source.split("\n")[1].index("cast(") + 1
                )

    def test_public_checker_normalizes_physical_newlines(self):
        lines = [
            "from typing import cast",
            "# SAFETY: SDK guarantees the return type.",
            "user = cast(User, raw)",
        ]
        for newline in ["\n", "\r\n", "\r"]:
            with self.subTest(newline=repr(newline)):
                self.assertEqual(check_source(newline.join(lines)), [])

    def test_nested_classes_do_not_close_over_the_outer_class_namespace(self):
        cases = [
            (
                """
                def cast(*args):
                    return args[-1]
                class Outer:
                    from typing import cast
                    class Inner:
                        value = cast(int, 1)
                        def method(self):
                            return cast(int, 1)
                """,
                [],
            ),
            (
                """
                from typing import cast
                class Outer:
                    def cast(*args):
                        return args[-1]
                    class Inner:
                        value = cast(int, 1)
                        def method(self):
                            return cast(int, 1)
                """,
                ["ASPY003", "ASPY003"],
            ),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    [item.code for item in check_source(textwrap.dedent(source))],
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
