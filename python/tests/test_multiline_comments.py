"""Regression coverage for comments attached to multiline closing lines."""

from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from anti_slop import check_source


class ClosingLineTests(unittest.TestCase):
    def test_suppression_on_expression_and_statement_closing_lines(self) -> None:
        for source in [
            """
            from typing import cast
            user = cast(
                User, sdk_result
            )  # anti-slop: ignore[ASPY003] -- contract documented in the SDK issue
            """,
            """
            from typing import cast
            users = [
                cast(
                    User, sdk_result
                ),  # anti-slop: ignore[ASPY003] -- SDK guarantees User instances
            ]
            """,
            """
            from typing import cast
            users = [
                cast(
                    User, sdk_result
                ),
            ]  # anti-slop: ignore[ASPY003] -- SDK guarantees User instances
            """,
        ]:
            with self.subTest(source=source):
                self.assertEqual(check_source(textwrap.dedent(source)), [])

    def test_safety_comment_on_expression_and_statement_closing_lines(self) -> None:
        for source in [
            """
            from typing import cast
            user = cast(
                User, sdk_result
            )  # SAFETY: The SDK guarantees User instances despite its stub.
            """,
            """
            from typing import cast
            users = [
                cast(User, sdk_result),
            ]  # SAFETY: The SDK guarantees User instances despite its stub.
            """,
        ]:
            with self.subTest(source=source):
                self.assertEqual(check_source(textwrap.dedent(source)), [])

    def test_closing_line_suppression_preserves_other_rules(self) -> None:
        source = """
            from typing import cast
            import json
            user = cast(
                User, json.loads(payload)
            )  # anti-slop: ignore[ASPY003] -- only the cast comment is waived
        """
        diagnostics = check_source(textwrap.dedent(source))
        self.assertEqual([item.code for item in diagnostics], ["ASPY001"])

    def test_closing_line_comments_do_not_silence_later_statements(self) -> None:
        for comment in [
            "# anti-slop: ignore[ASPY003] -- applies only to this SDK result",
            "# SAFETY: This SDK result is already validated.",
        ]:
            source = (
                "from typing import cast\n"
                "user = cast(\n"
                "    User, sdk_result\n"
                f")  {comment}\n"
                "other = cast(User, unvalidated)\n"
            )
            with self.subTest(comment=comment):
                self.assertEqual(
                    [(item.code, item.line) for item in check_source(source)],
                    [("ASPY003", 5)],
                )

    def test_unused_closing_line_suppression_still_fails(self) -> None:
        source = """
            user = (
                sdk_result
            )  # anti-slop: ignore[ASPY003] -- the cast has been removed
        """
        diagnostics = check_source(textwrap.dedent(source))
        self.assertEqual([item.code for item in diagnostics], ["ASPY901"])


if __name__ == "__main__":
    unittest.main()
