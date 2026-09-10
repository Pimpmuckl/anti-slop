# Native anti-slop: principles and standards

Reconciled against primary language/tool documentation on 2026-09-10. There is no
single industry-wide agentic-coding standard: use ordinary language semantics and
established tooling, then label additional team taste honestly. The same definition
of correctness applies to human and agent-authored code.

Preserve known types, error causes and ownership information. Validate untrusted
boundaries without repeatedly reparsing known domain values. Explain unchecked
assumptions. Use simple dependency seams, not speculative frameworks. Require tests
for meaningful behavior and negative fixtures for each lint's legitimate neighbors.

| Original TS concern | Python adaptation | Rust adaptation |
| --- | --- | --- |
| Erase types and assert them back | Local JSON casts and widen-then-cast checks | Retain error causes, must-use obligations and unsafe invariants |
| Eager array pipelines / repeated copies | Preserve lazy map/filter; detect supported accumulator copies and reuse Ruff RUF017 | Preserve lazy iterators; use Clippy needless_collect/clone_on_copy |
| Module mocking | Optional explicitly owned-module policy | Do not invent a universal equivalent or mandate abstraction layers |
| Opaque contracts | Existing type checker; no global Any/object/dictionary ban | Typed structs/enums and optional project disallowed_types; no trait-object/HashMap ban |
| Justify escape hatches | Cast explanations and narrow, nonstale suppressions | Native unsafe documentation and reasoned, nonstale lint expectations |
| Personal style | Defer to Ruff/Black, no shape substring ban | Defer to rustfmt, no name/trait-count/line-count rules |

Python is a standard-library AST/token companion because Ruff does not expose a
third-party plugin API. Reuse Ruff and the existing mypy/pyright/ty workflow rather
than writing another type checker. Scope/alias resolution is deliberately local and
its limits are documented. Rust uses a zero-dependency Cargo policy runner and
actual Clippy configuration, which already provides compiler-resolved method bans.
This avoids nightly toolchain coupling for requirements stable tooling can meet.

Optional module-patching and explicit-error policies are team preferences, not proof
that every patch/default is defective. Serialization round-trip redundancy, error
string branching and supposedly unnecessary classes/traits are not claimed as
implemented. The stronger versions require evidence this implementation lacks.

## Agent integration

Copy/configure/validate is not permission for unrelated application cleanup. Keep
existing tools, lock policies, features, local rules, licenses and provenance. Stage
updates; merge from a recoverable pristine base or conservatively port reviewed
changes. A hash list identifies bytes, not a recoverable merge base or known commit.

For a finding, verify reachability and fix its cause. Do not mechanically insert a
cast, mutation, `?`, validation dependency, DI framework, blanket ignore or meaningless
safety comment. Separate formatting from behavior changes and test the result.

## Primary references

- [PEP 8](https://peps.python.org/pep-0008/): ordinary Python conventions, project consistency, exception handling and runtime type checks.
- [Python typing](https://docs.python.org/3/library/typing.html): cast/annotations are not runtime validation; Any differs from object.
- [Typing library guidelines](https://typing.python.org/en/latest/guides/libraries.html): useful typed public contracts.
- [Ruff FAQ](https://docs.astral.sh/ruff/faq/) and [rules](https://docs.astral.sh/ruff/rules/): complement type checkers, reuse existing checks, no custom plugin API.
- [mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html): deliberately selected type policy.
- [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/): typed APIs, errors and documentation.
- [Clippy usage](https://doc.rust-lang.org/clippy/usage.html) and [lint reference](https://rust-lang.github.io/rust-clippy/stable/index.html): select restrictions individually and rely on resolved diagnostics.
- [Result](https://doc.rust-lang.org/std/result/enum.Result.html) and [iterators](https://doc.rust-lang.org/std/iter/): error-loss semantics and lazy adapters.
- [Dylint limitations](https://github.com/trailofbits/dylint/blob/master/docs/how_dylint_works.md#limitations): compiler coupling avoided for this scope.
