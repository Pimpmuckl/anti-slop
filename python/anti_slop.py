"""Small, vendorable Python checks that complement Ruff and a type checker.

Analysis is lexical and deliberately local. Application modules are never imported.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import json
import os
import re
import sys
import tokenize
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

RULES = {
    "ASPY001": "no-unchecked-json-cast",
    "ASPY002": "no-widen-then-cast",
    "ASPY003": "require-cast-justification",
    "ASPY004": "no-growing-accumulator-copy",
    "ASPY101": "no-internal-module-patching",
}
DEFAULT_RULES = frozenset({"ASPY001", "ASPY002", "ASPY003", "ASPY004"})
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "target",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".nox",
    }
)
CASTS = {"typing.cast", "typing_extensions.cast"}
BROAD = {"typing.Any", "typing_extensions.Any", "builtins.object"}


@dataclass(frozen=True)
class Diagnostic:
    path: str
    line: int
    column: int
    code: str
    message: str


@dataclass
class Ignore:
    line: int
    column: int
    target: int
    codes: set[str]
    used: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Definition:
    node: ast.AST
    qualified: str | None = None
    annotation: ast.expr | None = None


@dataclass(frozen=True)
class AssignedValue:
    node: ast.Assign | ast.AnnAssign
    value: ast.expr
    annotation: ast.expr | None


class Bindings(ast.NodeVisitor):
    """Collect writes in one lexical scope, including otherwise easy-to-miss shadows."""

    def __init__(self) -> None:
        self.names: dict[str, list[Definition]] = {}
        self.modified_roots: set[str] = set()
        self.star_import = False

    def add(
        self,
        name: str,
        node: ast.AST,
        qualified: str | None = None,
        annotation: ast.expr | None = None,
    ) -> None:
        self.names.setdefault(name, []).append(Definition(node, qualified, annotation))

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.add(node.id, node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            root = node.value
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if isinstance(root, ast.Name):
                self.modified_roots.add(root.id)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.add(
                alias.asname or alias.name.split(".")[0],
                node,
                alias.name if alias.asname else alias.name.split(".")[0],
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.star_import = True
            else:
                qualified = f"{node.module}.{alias.name}" if node.level == 0 else None
                self.add(alias.asname or alias.name, node, qualified)

    def function_header(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
    ) -> None:
        if not isinstance(node, ast.Lambda):
            for decorator in node.decorator_list:
                self.visit(decorator)
        for value in [*node.args.defaults, *node.args.kw_defaults]:
            if value is not None:
                self.visit(value)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.add(node.name, node)
        self.function_header(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.function_header(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.add(node.name, node)
        for value in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(value)

    def visit_Global(self, node: ast.Global | ast.Nonlocal) -> None:
        for name in node.names:
            self.add(name, node)  # Do not infer mutable nonlocal/global bindings.

    visit_Nonlocal = visit_Global

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name is not None:
            self.add(node.name, node)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name is not None:
            self.add(node.name, node)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name is not None:
            self.add(node.name, node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest is not None:
            self.add(node.rest, node)
        self.generic_visit(node)

    def comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        self.visit(node.generators[0].iter)
        # A walrus can bind in the enclosing scope. Conservatively invalidate it.
        for child in ast.walk(node):
            if isinstance(child, ast.NamedExpr):
                self.visit(child.target)

    visit_ListComp = comprehension
    visit_SetComp = comprehension
    visit_DictComp = comprehension
    visit_GeneratorExp = comprehension


@dataclass
class Scope:
    node: ast.AST
    parent: Scope | None
    bindings: Bindings


class Checker(ast.NodeVisitor):
    def __init__(
        self,
        source: str,
        path: str,
        tree: ast.Module,
        selected: frozenset[str],
        internal_modules: tuple[str, ...],
    ) -> None:
        self.source = source
        self.lines = source.split("\n")
        self.path = path
        self.selected = selected
        self.internal_modules = internal_modules
        self.diagnostics: list[Diagnostic] = []
        self.parents = {
            child: node
            for node in ast.walk(tree)
            for child in ast.iter_child_nodes(node)
        }
        self.locations: dict[ast.AST, tuple[int, int]] = {}
        for node in ast.walk(tree):
            for _, value in ast.iter_fields(node):
                if isinstance(value, list):
                    for index, child in enumerate(value):
                        if isinstance(child, ast.stmt):
                            self.locations[child] = (id(value), index)
        self.comments: dict[int, tokenize.TokenInfo] = {}
        self.ignores: list[Ignore] = []
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                self.comments[token.start[0]] = token
                self.read_ignore(token)
        self.scope = self.make_scope(tree, None, tree.body)

    def make_scope(
        self, node: ast.AST, parent: Scope | None, body: Sequence[ast.AST]
    ) -> Scope:
        bindings = Bindings()
        arguments = getattr(node, "args", None)
        if isinstance(arguments, ast.arguments):
            for argument in [
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                arguments.vararg,
                arguments.kwarg,
            ]:
                if argument is not None:
                    bindings.add(argument.arg, argument, annotation=argument.annotation)
        for item in body:
            bindings.visit(item)
        return Scope(node, parent, bindings)

    def raw(self, line: int, column: int, code: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(self.path, line, column, code, message))

    def read_ignore(self, token: tokenize.TokenInfo) -> None:
        if not re.match(r"#\s*anti-slop:", token.string):
            return
        match = re.fullmatch(
            r"#\s*anti-slop:\s*ignore\[([A-Z0-9, \t]+)\]\s*--\s*(\S.*)", token.string
        )
        codes = {part.strip() for part in match[1].split(",")} if match else set()
        if not match or not codes or not codes <= RULES.keys():
            self.raw(
                token.start[0],
                token.start[1] + 1,
                "ASPY900",
                "Use ignore[known-rule-codes] -- a nonempty reason; blanket ignores are not supported.",
            )
            return
        line, column = token.start
        standalone = not self.lines[line - 1][:column].strip()
        self.ignores.append(Ignore(line, column + 1, line + int(standalone), codes))

    def statement(self, node: ast.AST) -> ast.AST:
        while not isinstance(node, ast.stmt) and node in self.parents:
            node = self.parents[node]
        return node

    def anchors(self, node: ast.expr | ast.stmt) -> set[int]:
        statement = self.statement(node)
        anchors = {node.lineno, node.end_lineno or node.lineno}
        if isinstance(statement, ast.stmt):
            anchors.update({statement.lineno, statement.end_lineno or statement.lineno})
        return anchors

    def emit(self, node: ast.expr | ast.stmt, code: str, message: str) -> None:
        if code not in self.selected:
            return
        matching = [
            ignore
            for ignore in self.ignores
            if ignore.target in self.anchors(node) and code in ignore.codes
        ]
        if matching:
            for ignore in matching:
                ignore.used.add(code)
            return
        # AST columns are UTF-8 byte offsets; diagnostics use one-based character columns.
        prefix = self.lines[node.lineno - 1].encode("utf-8")[: node.col_offset]
        self.raw(node.lineno, len(prefix.decode("utf-8")) + 1, code, message)

    def justified(self, node: ast.expr | ast.stmt) -> bool:
        for line in self.anchors(node):
            token = self.comments.get(line)
            if token is not None and re.match(r"#\s*SAFETY:\s*\S", token.string):
                return True
            previous = line - 1
            while previous in self.comments:
                token = self.comments[previous]
                if self.lines[previous - 1][: token.start[1]].strip():
                    break
                if re.match(r"#\s*SAFETY:\s*\S", token.string):
                    return True
                previous -= 1
        return False

    def precedes(self, definition: ast.AST, use: ast.AST) -> bool:
        left = self.locations.get(self.statement(definition))
        right = self.locations.get(self.statement(use))
        return (
            left is not None
            and right is not None
            and left[0] == right[0]
            and left[1] < right[1]
        )

    def qualified(
        self,
        node: ast.AST,
        scope: Scope | None = None,
        seen: frozenset[tuple[int, str]] = frozenset(),
    ) -> str | None:
        scope = scope or self.scope
        if isinstance(node, ast.Attribute):
            owner = self.qualified(node.value, scope, seen)
            return f"{owner}.{node.attr}" if owner else None
        if not isinstance(node, ast.Name):
            return None
        current: Scope | None = scope
        while current is not None:
            if (
                current.bindings.star_import
                or node.id in current.bindings.modified_roots
            ):
                return None
            definitions = current.bindings.names.get(node.id)
            if definitions is not None:
                key = (id(current), node.id)
                if len(definitions) != 1 or key in seen:
                    return None
                definition = definitions[0]
                if definition.qualified is not None:
                    return definition.qualified
                assignment = self.parents.get(definition.node)
                if (
                    isinstance(assignment, ast.Assign)
                    and len(assignment.targets) == 1
                    and self.precedes(assignment, node)
                ):
                    return self.qualified(assignment.value, current, seen | {key})
                return None
            current = current.parent
        return f"builtins.{node.id}" if node.id in {"object", "dict", "list"} else None

    def broad(self, annotation: ast.AST) -> bool:
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                annotation = ast.parse(annotation.value, mode="eval").body
            except SyntaxError:
                return False
        return self.qualified(annotation) in BROAD

    def local_assignment(self, node: ast.AST, use: ast.AST) -> AssignedValue | None:
        if not isinstance(node, ast.Name):
            return None
        definitions = self.scope.bindings.names.get(node.id, [])
        if len(definitions) != 1:
            return None
        assignment = self.parents.get(definitions[0].node)
        if (
            isinstance(assignment, (ast.Assign, ast.AnnAssign))
            and assignment.value is not None
            and self.precedes(assignment, use)
        ):
            if isinstance(assignment, ast.Assign) and len(assignment.targets) != 1:
                return None
            return AssignedValue(
                assignment,
                assignment.value,
                assignment.annotation
                if isinstance(assignment, ast.AnnAssign)
                else None,
            )
        return None

    def known_annotation(self, node: ast.AST, use: ast.AST) -> ast.expr | None:
        if not isinstance(node, ast.Name):
            return None
        definitions = self.scope.bindings.names.get(node.id, [])
        if len(definitions) != 1:
            return None
        annotation = definitions[0].annotation
        assignment = self.local_assignment(node, use)
        if assignment is not None and assignment.annotation is not None:
            annotation = assignment.annotation
        return (
            annotation
            if annotation is not None and not self.broad(annotation)
            else None
        )

    def cast_arguments(self, node: ast.AST) -> tuple[ast.expr, ast.expr] | None:
        if not isinstance(node, ast.Call) or self.qualified(node.func) not in CASTS:
            return None
        if len(node.args) > 2 or any(isinstance(arg, ast.Starred) for arg in node.args):
            return None
        values = dict(zip(("typ", "val"), node.args))
        for keyword in node.keywords:
            if (
                keyword.arg is None
                or keyword.arg not in {"typ", "val"}
                or keyword.arg in values
            ):
                return None
            values[keyword.arg] = keyword.value
        return (
            (values["typ"], values["val"]) if values.keys() == {"typ", "val"} else None
        )

    def json_boundary(
        self, node: ast.AST, use: ast.AST, seen: frozenset[str] = frozenset()
    ) -> bool:
        if isinstance(node, ast.Call):
            return self.qualified(node.func) in {"json.load", "json.loads"}
        if isinstance(node, ast.Name) and node.id not in seen:
            assignment = self.local_assignment(node, use)
            if assignment is not None:
                return self.json_boundary(
                    assignment.value, assignment.node, seen | {node.id}
                )
        return False

    def visit_Call(self, node: ast.Call) -> None:
        arguments = self.cast_arguments(node)
        if arguments is not None:
            target, value = arguments
            if not self.broad(target) and self.json_boundary(value, node):
                self.emit(
                    node,
                    "ASPY001",
                    "typing.cast does not validate JSON. Parse the boundary value before claiming this type.",
                )
            inner = self.cast_arguments(value)
            if inner is not None and self.broad(inner[0]) and not self.broad(target):
                self.emit(
                    node,
                    "ASPY002",
                    "This nested cast erases type evidence before asserting a narrower type. Keep the original contract.",
                )
            else:
                assignment = self.local_assignment(value, node)
                if assignment is not None:
                    broad = assignment.annotation is not None and self.broad(
                        assignment.annotation
                    )
                    original = assignment.value
                    erased = self.cast_arguments(original)
                    if erased is not None and self.broad(erased[0]):
                        broad, original = True, erased[1]
                    annotation = self.known_annotation(original, assignment.node)
                    if broad and annotation is not None and not self.broad(target):
                        self.emit(
                            node,
                            "ASPY002",
                            f"This binding discarded {ast.unparse(annotation)} and recreates type evidence with a cast. Preserve the original type.",
                        )
            if not self.justified(node):
                self.emit(
                    node,
                    "ASPY003",
                    "Explain the invariant in a nearby nonempty # SAFETY: comment. A cast does not check it.",
                )
        qualified = self.qualified(node.func)
        module = None
        if qualified == "unittest.mock.patch" and node.args:
            target = node.args[0]
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                module = target.value.rpartition(".")[0]
        elif qualified == "unittest.mock.patch.object" and node.args:
            module = self.qualified(node.args[0])
        if module and any(
            module == prefix or module.startswith(prefix + ".")
            for prefix in self.internal_modules
        ):
            self.emit(
                node,
                "ASPY101",
                "Replace patching application-owned dependencies with an explicit seam or faithful fake. Environment fixtures are not banned.",
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value = node.value
            list_copy = (
                isinstance(value, ast.BinOp)
                and isinstance(value.op, ast.Add)
                and isinstance(value.left, ast.Name)
                and value.left.id == name
                and isinstance(value.right, ast.List)
            )
            dict_copy = isinstance(value, ast.Dict) and any(
                key is None and isinstance(item, ast.Name) and item.id == name
                for key, item in zip(value.keys, value.values)
            )
            loop = self.parents.get(node)
            while loop is not None and not isinstance(
                loop, (ast.For, ast.AsyncFor, ast.While)
            ):
                if loop is self.scope.node:
                    loop = None
                    break
                loop = self.parents.get(loop)
            definitions = self.scope.bindings.names.get(name, [])
            if loop is not None and len(definitions) == 2 and (list_copy or dict_copy):
                for definition in definitions:
                    initial = self.parents.get(definition.node)
                    if isinstance(
                        initial, (ast.Assign, ast.AnnAssign)
                    ) and self.precedes(initial, loop):
                        literal = ast.List if list_copy else ast.Dict
                        if isinstance(initial.value, literal):
                            self.emit(
                                node,
                                "ASPY004",
                                "This loop copies its growing local accumulator. Build it directly when ownership permits; mutation is not an automatic safe rewrite.",
                            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for value in [*node.args.defaults, *node.args.kw_defaults]:
            if value is not None:
                self.visit(value)
        old = self.scope
        parent = old.parent if isinstance(old.node, ast.ClassDef) else old
        self.scope = self.make_scope(node, parent, node.body)
        for item in node.body:
            self.visit(item)
        self.scope = old

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for value in [*node.args.defaults, *node.args.kw_defaults]:
            if value is not None:
                self.visit(value)
        old = self.scope
        parent = old.parent if isinstance(old.node, ast.ClassDef) else old
        self.scope = self.make_scope(node, parent, [node.body])
        self.visit(node.body)
        self.scope = old

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for value in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(value)
        old = self.scope
        parent = old.parent if isinstance(old.node, ast.ClassDef) else old
        self.scope = self.make_scope(node, parent, node.body)
        for item in node.body:
            self.visit(item)
        self.scope = old

    def comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        self.visit(node.generators[0].iter)
        old = self.scope
        parent = old.parent if isinstance(old.node, ast.ClassDef) else old
        bindings = Bindings()
        for generator in node.generators:
            bindings.visit(generator.target)
        self.scope = Scope(node, parent, bindings)
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        for expression in (
            [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        ):
            self.visit(expression)
        self.scope = old

    visit_ListComp = comprehension
    visit_SetComp = comprehension
    visit_DictComp = comprehension
    visit_GeneratorExp = comprehension

    def finish(self) -> list[Diagnostic]:
        for ignore in self.ignores:
            unused = (ignore.codes & self.selected) - ignore.used
            if unused:
                self.raw(
                    ignore.line,
                    ignore.column,
                    "ASPY901",
                    "Unused suppression: " + ", ".join(sorted(unused)),
                )
        return sorted(
            self.diagnostics,
            key=lambda item: (item.path, item.line, item.column, item.code),
        )


def check_source(
    source: str,
    path: str = "<string>",
    *,
    selected: frozenset[str] = DEFAULT_RULES,
    internal_modules: tuple[str, ...] = (),
) -> list[Diagnostic]:
    """Check source without importing or executing it; positions are one-based."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [
            Diagnostic(path, error.lineno or 1, error.offset or 1, "ASPY000", error.msg)
        ]
    checker = Checker(source, path, tree, selected, internal_modules)
    checker.visit(tree)
    return checker.finish()


def string_list(settings: dict[str, object], key: str) -> list[str]:
    value = settings.get(key, [])
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list of nonempty strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{key} must be a list of nonempty strings")
        if not item.strip():
            raise ValueError(f"{key} must be a list of nonempty strings")
        result.append(item)
    return result


def table(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key, {})
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a TOML table")
    return value


def configuration(explicit: str | None) -> tuple[dict[str, object], Path]:
    candidates = (
        [Path(explicit)]
        if explicit
        else [parent / "pyproject.toml" for parent in [Path.cwd(), *Path.cwd().parents]]
    )
    for path in candidates:
        if explicit or path.is_file():
            with path.open("rb") as file:
                document = tomllib.load(file)
            settings = table(table(table(document, "tool"), "anti-slop"), "python")
            unknown = settings.keys() - {
                "select",
                "extend-select",
                "ignore",
                "exclude",
                "internal-modules",
            }
            if unknown:
                raise ValueError(
                    "Unknown Python anti-slop settings: " + ", ".join(sorted(unknown))
                )
            return settings, path.resolve().parent
    return {}, Path.cwd().resolve()


def discover(paths: list[str], root: Path, exclude: list[str]) -> list[Path]:
    found: set[Path] = set()

    def excluded(path: Path) -> bool:
        relative = Path(os.path.relpath(path, root)).as_posix()
        return any(fnmatch.fnmatchcase(relative, pattern) for pattern in exclude)

    def fail(error: OSError) -> None:
        raise error

    for argument in paths:
        path = Path(argument).resolve()
        if not path.exists():
            raise ValueError(f"Path does not exist: {argument}")
        if path.is_file():
            if path.suffix not in {".py", ".pyi"}:
                raise ValueError(f"Not a Python source file: {argument}")
            if not excluded(path):
                found.add(path)
        elif path.is_dir():
            for directory, dirs, files in os.walk(
                path, onerror=fail, followlinks=False
            ):
                dirs[:] = sorted(
                    name
                    for name in dirs
                    if name not in SKIP_DIRS
                    and not (Path(directory) / name).is_symlink()
                    and not excluded(Path(directory) / name)
                )
                for name in files:
                    file = Path(directory) / name
                    if (
                        file.suffix in {".py", ".pyi"}
                        and not file.is_symlink()
                        and not excluded(file)
                    ):
                        found.add(file)
        else:
            raise ValueError(f"Not a regular file or directory: {argument}")
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument(
        "--config", help="pyproject.toml containing [tool.anti-slop.python]"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--select", help="comma-separated exact rule codes; replaces the selection"
    )
    parser.add_argument("--ignore", help="comma-separated exact rule codes")
    parser.add_argument("--internal-module", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        settings, root = configuration(args.config)
        selected = (
            set(string_list(settings, "select"))
            if "select" in settings
            else set(DEFAULT_RULES)
        )
        selected.update(string_list(settings, "extend-select"))
        ignored = set(string_list(settings, "ignore"))
        if args.select is not None:
            selected = {item.strip() for item in args.select.split(",")}
        if args.ignore is not None:
            ignored.update(item.strip() for item in args.ignore.split(","))
        unknown = (selected | ignored) - RULES.keys()
        if unknown:
            raise ValueError("Unknown rule codes: " + ", ".join(sorted(unknown)))
        selected -= ignored
        modules = (*string_list(settings, "internal-modules"), *args.internal_module)
        if any(
            not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module)
            for module in modules
        ):
            raise ValueError("internal-modules must contain dotted Python module names")
        if "ASPY101" in selected and not modules:
            raise ValueError(
                "ASPY101 requires explicit internal-modules; no application ownership is guessed"
            )
        files = discover(args.paths or ["."], root, string_list(settings, "exclude"))
        diagnostics = []
        for file in files:
            with tokenize.open(file) as stream:
                source = stream.read()
            diagnostics.extend(
                check_source(
                    source,
                    str(file),
                    selected=frozenset(selected),
                    internal_modules=modules,
                )
            )
    except (
        OSError,
        TypeError,
        ValueError,
        UnicodeError,
        SyntaxError,
        tokenize.TokenError,
    ) as error:
        print(f"anti-slop: {error}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps([asdict(item) for item in diagnostics], ensure_ascii=False))
    elif diagnostics:
        for item in diagnostics:
            print(f"{item.path}:{item.line}:{item.column}: {item.code} {item.message}")
    else:
        print(f"Checked {len(files)} Python file(s); no anti-slop findings.")
    return (
        2
        if any(item.code == "ASPY000" for item in diagnostics)
        else int(bool(diagnostics))
    )


if __name__ == "__main__":
    sys.exit(main())
