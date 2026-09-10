# Python anti-slop

A vendorable companion to Ruff and a type checker. Python 3.11+; no third-party
runtime dependencies. Use an interpreter that understands the source syntax.
Analyzed application modules are never imported or executed.

## Install and run

Copy this directory without tests/caches, or use the installation skill:

```sh
node <skill-directory>/scripts/install-native.mjs python
python tools/anti-slop/python/anti_slop.py src tests
python tools/anti-slop/python/anti_slop.py src --format json
```

Exit status: **0** clean, **1** findings, **2** invalid configuration, unreadable
input, or unparseable syntax. JSON is an array of objects with `path`, `line`,
`column`, `code`, and `message`; positions are one-based character positions.
There are no semantic autofixes. A missing explicit path is an error.

Directory discovery includes `.py` and `.pyi`, skips dependency/cache directories
and symlinks, and preserves other hidden owned source. Explicit symlink paths are
accepted. Notebooks and per-file nested configuration discovery are not supported.

## Rules

| Code | Rule | Policy and analysis boundary |
| --- | --- | --- |
| ASPY001 | no-unchecked-json-cast | Resolved `typing.cast` / `typing_extensions.cast` on `json.load` / `json.loads`, including supported single-write local aliases. A cast is not validation. |
| ASPY002 | no-widen-then-cast | Nested casts through `Any`/`object`, or same-block widening of explicitly annotated values followed by a narrower cast. No imported-type or cross-file inference. |
| ASPY003 | require-cast-justification | A resolved cast needs a nearby nonempty `# SAFETY:` explanation. Presence is checked; its truth requires review. |
| ASPY004 | no-growing-accumulator-copy | Rebuilding a local literal-initialized list/dict inside a loop. Unknown custom collections are allowed; ownership is not established for an automatic mutation rewrite. |
| ASPY101 | no-internal-module-patching | **Opt-in.** Resolved `unittest.mock.patch` literal targets or `patch.object` on configured owned modules. No ownership guessing or general mocking ban. |

ASPY001–004 are enabled by default. ASPY000 reports syntax errors; ASPY900 reports
invalid suppression directives; ASPY901 reports stale suppressions. These diagnostic
checks cannot themselves be suppressed.

### Preserve evidence, validate real boundaries

```python
from typing import Any, cast
import json

user = cast(User, json.loads(payload))  # ASPY001: no validation took place.


def save(user: User) -> None:
    erased: Any = user
    persist(cast(User, erased))  # ASPY002: we already had the useful type.
```

Use a real parser/validator appropriate to the existing project. For a Pydantic
model, `User.model_validate_json(payload)` is an option, not a required dependency.
A handwritten parser is also valid. `TypedDict` alone is not runtime validation.
Keep an already-known `User` typed throughout the operation instead of erasing it.

Normal `isinstance`, protocols, typed mappings, `object`, `Any`, `**kwargs`, lazy
`map`/`filter` and dynamic integration boundaries are not globally prohibited.

### Explain genuine escape hatches

```python
# SAFETY: This SDK returns User instances; its shipped stub says object.
user = cast(User, sdk_result)
```

Put the comment on the opening or closing line of the cast or containing statement,
or in an immediately preceding comment block. Blank lines or another statement
break attachment. A comment does not silence ASPY001/002. Never manufacture
meaningless justifications as fixes.

An intentional exception needs exact rule codes and a reason, on the opening or
closing line of the cast or containing statement, or immediately before it:

```python
user = cast(
    User, sdk_result
)  # anti-slop: ignore[ASPY003] -- contract documented in the SDK issue
```

Multiple codes are comma-separated. Deselected rules are not counted as stale.
There are no blanket or file-wide suppression directives.

## Configuration

Use the nearest `pyproject.toml` above the current working directory, or
`--config path/to/pyproject.toml`. Input paths are working-directory-relative;
case-sensitive slash-separated `fnmatch` exclusions are config-directory-relative
and also apply to explicit files. Invoke separately per project in a monorepo.

```toml
[tool.anti-slop.python]
select = ["ASPY001", "ASPY002", "ASPY003", "ASPY004"] # defaults
exclude = ["tools/anti-slop/**", "generated/**"]
# Optional architecture preference; agree ownership explicitly:
extend-select = ["ASPY101"]
internal-modules = ["your_application"]
```

`--select ASPY001,ASPY003` replaces the selection. `--ignore ASPY003` removes a rule.
Unknown rules/settings or malformed configuration fail explicitly.

Merge `ruff.toml` checks into existing settings without replacing ignores, target
versions or extend chains. Ruff handles mutable defaults, exception chaining,
reflection, unused suppressions, quadratic list summation and dangling async tasks.
Use Ruff format or Black; this checker does not impose competing spacing rules.
Keep the project's existing mypy/pyright/ty choice. `mypy.ini` is a starter for
projects choosing mypy, not a mandate to replace another type checker.

## Limitations and testing

Analysis uses AST, comment tokens, lexical scopes and limited local evidence, not
a full type checker/interpreter. Alias ambiguity, reassignment and star imports
abandon inference. Runtime patching through other aliases, arbitrary decorators,
imported type aliases, custom JSON decoders and mutation through external calls
are not fully modeled. A JSON cast with a custom decoder that actually validates
its contract can require an explicit exception. Local flow is limited to earlier
assignments in the same statement block. Accumulator copying does not necessarily
imply quadratic complexity when the accumulator is bounded.

Test rejected patterns and close legitimate alternatives:

```sh
python -m unittest discover -s python/tests -v
```
