"""Behavioral and negative fixtures for the vendored checker; no application imports."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anti_slop import DEFAULT_RULES, check_source, main  # noqa: E402


def codes(source: str, *, selected=DEFAULT_RULES, modules=()) -> list[str]:
    return [item.code for item in check_source(textwrap.dedent(source), selected=frozenset(selected), internal_modules=modules)]


class CastTests(unittest.TestCase):
    def test_json_casts_and_import_aliases(self):
        cases = [
            "import typing, json\nx = typing.cast(User, json.loads(raw))",
            "from typing import cast as narrow\nfrom json import loads as decode\nx = narrow(User, decode(raw))",
            "import typing as t\nimport json as j\nx = t.cast(typ=User, val=j.load(file))",
            "from typing import cast\nimport json\nraw = json.loads(text)\nalias = raw\nx = cast(User, alias)",
            "from typing_extensions import cast\nimport json\nx = cast(User, json.loads(raw))",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(codes(source), ["ASPY001", "ASPY003"])

    def test_cast_comment_is_not_json_validation(self):
        self.assertEqual(codes('''
            from typing import cast
            import json
            # SAFETY: We expect this to be a user.
            user = cast(User, json.loads(raw))
        '''), ["ASPY001"])

    def test_no_runtime_execution(self):
        source = "raise RuntimeError('must not execute')\nimport missing_application\n"
        self.assertEqual(codes(source), [])

    def test_real_validation_and_dynamic_types_are_not_json_cast_violations(self):
        cases = [
            "import json\nuser = User.model_validate(json.loads(raw))",
            "from typing import cast\nimport json\n# SAFETY: validator establishes the contract.\nx = cast(User, validate(json.loads(raw)))",
            "from typing import Any, cast\nimport json\n# SAFETY: intentionally retains dynamic typing.\nx = cast(Any, json.loads(raw))",
            "from typing import cast\nimport json\n# SAFETY: object makes no claim about structure.\nx = cast(object, json.loads(raw))",
            "if isinstance(value, str):\n    print(value)",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_widening_annotated_arguments_and_locals(self):
        cases = [
            "from typing import Any, cast\ndef f(user: User):\n    erased: Any = user\n    return cast(User, erased)",
            "import typing as t\ndef f(user: User):\n    erased: object = user\n    return t.cast(User, erased)",
            "from typing import Any, cast\nuser: User = load()\nerased: Any = user\nx = cast(User, erased)",
            "from typing import Any, cast\ndef f(user: User):\n    erased: 'Any' = user\n    return cast(User, erased)",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(codes(source), ["ASPY002", "ASPY003"])

    def test_cast_widening_and_chains(self):
        self.assertEqual(codes('''
            from typing import Any, cast
            def f(user: User):
                # SAFETY: SDK annotation workaround.
                erased = cast(Any, user)
                return cast(User, erased)
        '''), ["ASPY002", "ASPY003"])
        self.assertEqual(codes('''
            from typing import Any, cast
            # SAFETY: explain both casts without changing the structural policy.
            user = cast(User, cast(Any, value))
        '''), ["ASPY002"])

    def test_no_type_flow_across_reassignment_branches_or_function_boundaries(self):
        cases = [
            "from typing import Any, cast\ndef f(user: User):\n    raw: Any = user\n    raw = external()\n    return cast(User, raw)",
            "from typing import Any, cast\ndef f(user: User):\n    if ready:\n        raw: Any = user\n    return cast(User, raw)",
            "from typing import Any, cast\ndef f(user: User):\n    raw: Any = user\n    def inner():\n        return cast(User, raw)",
            "from typing import Any, cast\ndef f(user: Any):\n    raw: Any = user\n    return cast(User, raw)",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(codes(source, selected={"ASPY001", "ASPY002"}), [])

    def test_shadowed_names_are_not_typing_cast(self):
        cases = [
            "def cast(*args): pass\nx = cast(User, data)",
            "from typing import cast\ndef f(cast):\n    return cast(User, data)",
            "from typing import cast\ndef f():\n    cast = custom\n    return cast(User, data)",
            "import typing\ntyping = custom\nx = typing.cast(User, data)",
            "import typing\ntyping.cast = custom\nx = typing.cast(User, data)",
            "from typing import cast\nf = lambda cast: cast(User, data)",
            "from typing import cast\nx = [cast(User, data) for cast in values]",
            "from typing import cast\nx = {cast(User, data) for cast in values}",
            "from typing import cast\nx = {key: cast(User, data) for key, cast in values}",
            "from typing import cast\nx = (cast(User, data) for cast in values)",
            "from typing import cast\ntry:\n    operation()\nexcept Exception as cast:\n    cast(User, data)",
            "from typing import cast\nmatch obj:\n    case {'cast': cast}:\n        cast(User, data)",
            "from typing import cast\ndef f():\n    global cast\n    return cast(User, data)",
            "from typing import cast\nfrom custom import *\nx = cast(User, data)",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])

    def test_methods_skip_the_class_namespace(self):
        self.assertEqual(codes('''
            from typing import cast
            class Container:
                cast = custom
                def read(self):
                    return cast(User, self.data)
        '''), ["ASPY003"])
        self.assertEqual(codes('''
            class Container:
                from typing import cast
                def read(self):
                    return cast(User, self.data)
        '''), [])

    def test_aliases_cycles_and_comprehension_outer_iterable(self):
        self.assertEqual(codes("from typing import cast\nnarrow = cast\nx = narrow(User, raw)"), ["ASPY003"])
        self.assertEqual(codes("a = b\nb = a\nx = a(User, raw)"), [])
        self.assertEqual(codes("from typing import cast\nx = [cast for cast in cast(list, values)]"), ["ASPY003"])

    def test_comments_are_tokens_and_need_a_nonempty_reason(self):
        cases = [
            ("# SAFETY: external validator enforces this.\nx = cast(User, raw)", []),
            ("x = cast(User, raw)  # SAFETY: SDK stub is too broad.", []),
            ("# SAFETY:\nx = cast(User, raw)", ["ASPY003"]),
            ("text = '# SAFETY: not a comment'\nx = cast(User, raw)", ["ASPY003"]),
            ("# SAFETY: attaches to something else.\ny = 0\nx = cast(User, raw)", ["ASPY003"]),
            ("# SAFETY: separated by a blank line.\n\nx = cast(User, raw)", ["ASPY003"]),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(codes("from typing import cast\n" + source), expected)

    def test_multiline_statement_comment_and_unicode_columns(self):
        self.assertEqual(codes('''
            from typing import cast
            # SAFETY: SDK result has an independently validated contract.
            result = (
                cast(User, raw)
            )
        '''), [])
        diagnostic = check_source("from typing import cast\né = '☃'; x = cast(User, raw)")[0]
        self.assertEqual(diagnostic.column, 14)


class AccumulatorTests(unittest.TestCase):
    def test_list_and_dictionary_copying(self):
        for source in [
            "items = []\nfor item in source:\n    items = items + [item]",
            "result = {}\nfor key, value in source:\n    result = {**result, key: value}",
            "items: list[int] = []\nwhile ready():\n    items = items + [read()]",
        ]:
            with self.subTest(source=source):
                self.assertEqual(codes(source), ["ASPY004"])

    def test_valid_collections_and_unknown_overloads(self):
        for source in [
            "items = []\nfor item in source:\n    items.append(item)",
            "items = []\nfor item in source:\n    items += [item]",
            "items = CustomCollection()\nfor item in source:\n    items = items + [item]",
            "items = []\nitems = items + [item]",
            "items = []\nfor items in source:\n    items = items + [item]",
            "items = []\nitems = custom\nfor item in source:\n    items = items + [item]",
            "items = []\nfor item in source:\n    clone = items + [item]",
            "values = map(transform, filter(predicate, source))",
        ]:
            with self.subTest(source=source):
                self.assertEqual(codes(source), [])


class PolicyTests(unittest.TestCase):
    def test_module_patching_is_explicit_and_resolved(self):
        selected = {"ASPY101"}
        for source in [
            "from unittest.mock import patch\npatch('owned.store.read')",
            "import unittest.mock as m\nm.patch('owned.store.read')",
            "from unittest.mock import patch\nimport owned.store as store\npatch.object(store, 'read')",
        ]:
            with self.subTest(source=source):
                self.assertEqual(codes(source, selected=selected, modules=("owned",)), ["ASPY101"])
        for source in [
            "from unittest.mock import patch\npatch('owned_elsewhere.store.read')",
            "from unittest.mock import patch\npatch('external.store.read')",
            "from unittest.mock import patch\npatch.dict('os.environ', {'A': 'B'})",
            "monkeypatch.setenv('A', 'B')",
            "def patch(target): pass\npatch('owned.store.read')",
            "from unittest.mock import patch\ndef f(patch):\n    patch('owned.store.read')",
        ]:
            with self.subTest(source=source):
                self.assertEqual(codes(source, selected=selected, modules=("owned",)), [])
        self.assertEqual(codes("from unittest.mock import patch\npatch('owned.store.read')"), [])

    def test_reasoned_suppressions_and_staleness(self):
        self.assertEqual(codes('''
            from typing import cast
            value = cast(User, raw)  # anti-slop: ignore[ASPY003] -- stub workaround reviewed here
        '''), [])
        self.assertEqual(codes('''
            from typing import cast
            # anti-slop: ignore[ASPY003] -- checked by the SDK
            value = (
                cast(User, raw)
            )
        '''), [])
        self.assertEqual(codes("x = 1  # anti-slop: ignore[ASPY003] -- no cast anymore"), ["ASPY901"])
        self.assertEqual(codes("# anti-slop: ignore[ASPY003] -- other profile\nx = 1", selected={"ASPY001"}), [])
        self.assertEqual(codes("x = 1  # anti-slop: ignore[ASPY999] -- typo"), ["ASPY900"])
        self.assertEqual(codes("x = 1  # anti-slop: ignore[ASPY003] --"), ["ASPY900"])
        self.assertEqual(codes("# anti-slop: ignore\nx = 1"), ["ASPY900"])
        self.assertEqual(codes("text = '# anti-slop: ignore'"), [])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = Path.cwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.previous)
        self.temp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(list(args))
        return status, out.getvalue(), err.getvalue()

    def test_json_and_exit_codes(self):
        Path("example.py").write_text("from typing import cast\nx = cast(User, raw)", encoding="utf-8")
        status, output, _ = self.run_cli("example.py", "--format", "json")
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output)[0]["code"], "ASPY003")
        self.assertEqual(self.run_cli("example.py", "--ignore", "ASPY003")[0], 0)
        Path("bad.py").write_text("def broken(", encoding="utf-8")
        status, output, _ = self.run_cli("bad.py", "--format", "json")
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output)[0]["code"], "ASPY000")
        self.assertEqual(self.run_cli("missing.py")[0], 2)
        self.assertEqual(self.run_cli("example.py", "--select", "ASPY999")[0], 2)

    def test_configuration_excludes_and_hidden_owned_source(self):
        Path("pyproject.toml").write_text('[tool.anti-slop.python]\nexclude = ["generated/*"]\n', encoding="utf-8")
        for directory in ["generated", ".venv", ".owned"]:
            Path(directory).mkdir()
            Path(directory, "bad.py").write_text("from typing import cast\nx = cast(User, raw)", encoding="utf-8")
        status, output, _ = self.run_cli(".", "--format", "json")
        self.assertEqual(status, 1)
        self.assertEqual(len(json.loads(output)), 1)
        self.assertTrue(json.loads(output)[0]["path"].endswith(".owned/bad.py") or json.loads(output)[0]["path"].endswith(".owned\\bad.py"))

    def test_invalid_config_and_explicit_policy_requirements(self):
        Path("example.py").write_text("x = 1", encoding="utf-8")
        for content in [
            '[tool.anti-slop.python]\nselect = "ASPY003"',
            '[tool.anti-slop.python]\nselct = ["ASPY003"]',
            '[tool.anti-slop.python]\nextend-select = ["ASPY101"]',
            '[tool.anti-slop.python]\ninternal-modules = [""]',
            '[tool.anti-slop.python]\nignore = ["ASPY999"]',
            '[tool]\nanti-slop = false',
            '[tool.anti-slop]\npython = false',
        ]:
            with self.subTest(content=content):
                Path("pyproject.toml").write_text(content, encoding="utf-8")
                self.assertEqual(self.run_cli("example.py")[0], 2)
        Path("pyproject.toml").write_text('[tool.anti-slop.python]\nextend-select = ["ASPY101"]\ninternal-modules = ["owned"]', encoding="utf-8")
        Path("example.py").write_text("from unittest.mock import patch\npatch('owned.store.read')", encoding="utf-8")
        self.assertEqual(self.run_cli("example.py")[0], 1)

    def test_duplicate_files_source_encoding_and_subprocess(self):
        Path("example.py").write_bytes(b"# coding: latin-1\ntext = '\xe9'\n")
        status, output, _ = self.run_cli(".", "example.py")
        self.assertEqual(status, 0)
        self.assertIn("1 Python file", output)
        result = subprocess.run([sys.executable, str(ROOT / "anti_slop.py"), "example.py"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_does_not_recurse_into_symlink_cycles(self):
        Path("source").mkdir()
        Path("source/example.py").write_text("x = 1", encoding="utf-8")
        try:
            Path("source/cycle").symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        self.assertEqual(self.run_cli(".")[0], 0)


if __name__ == "__main__":
    unittest.main()
