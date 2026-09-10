# Rust anti-slop

A dependency-free Cargo command selecting compiler/Clippy policies. Real compiler
resolution, not method-name matching. Rust 1.85+ with Clippy; no nightly coupling.

## Install and run

```sh
node <skill-directory>/scripts/install-native.mjs rust
rustup component add clippy
cargo install --path tools/anti-slop/rust --locked
cargo anti-slop --workspace
cargo fmt --check
```

Alternatively run the vendored source without a global installation:

```sh
cargo run --manifest-path tools/anti-slop/rust/Cargo.toml -- --manifest-path Cargo.toml --workspace
```

Rebuild/reinstall after changing policy source. The tool's own workspace keeps it
independently buildable when vendored within another workspace. Cargo options go
before `--`, rustc options after it. `--all-targets` is the default unless an
explicit Cargo target selector is supplied. Select supported workspace/features/
platform combinations deliberately; mutually exclusive features make an automatic
`--all-features` choice inappropriate.

```sh
cargo anti-slop --manifest-path crates/worker/Cargo.toml --lib
cargo anti-slop --workspace --message-format=json
cargo anti-slop --print-lints
```

Cargo configuration, Clippy configuration, local attributes and toolchain selection
are preserved. Explicit trailing rustc options can override policy, as with Clippy.
Cargo's normal exit code is retained; nonnumeric/out-of-byte-range termination maps
to 1, inability to launch Cargo to 2. Nothing silently rewrites application code.

## Core rules

Selected checks are passed with `-D`. Other Clippy defaults retain their normal
severity. Entire `restriction`, `pedantic` and `nursery` groups are not enabled.

| Concern | Compiler/Clippy checks |
| --- | --- |
| Discarded obligations | `unused_must_use`, `let_underscore_must_use`, `let_underscore_future` |
| Correctness and I/O | `correctness`, `unused_io_amount` |
| Unsafe obligations | `unsafe_op_in_unsafe_fn`, `undocumented_unsafe_blocks`, `missing_safety_doc` |
| Explain/retire exceptions | `allow_attributes_without_reason`, `unfulfilled_lint_expectations` |
| Async guard ownership | `await_holding_lock`, `await_holding_refcell_ref` |
| Avoid needless copies | `clone_on_copy`, `needless_collect` |
| Retain error context | `map_err_ignore` |
| Honor project policies | `disallowed_methods`, `disallowed_types`, `disallowed_macros` |

Clippy lint names in the table take the `clippy::` prefix. `map_err_ignore` covers
supported ignored-error closures, not every possible loss of an error cause.
Unsafe documentation records an obligation, not a machine-checked proof.

## Optional explicit-error policy

Merge `policies/explicit-errors.clippy.toml` entries into the existing project's
`disallowed-methods` list in `clippy.toml`/`.clippy.toml`. Preserve other settings.
For a new project without Clippy configuration, copy the policy to root
`clippy.toml`. Do not set `CLIPPY_CONF_DIR` to the bundle in an established project,
as that would hide its existing configuration.

This opt-in policy rejects `Result::ok`, `Result::unwrap_or` and
`Result::unwrap_or_default`, with reasons explaining what is discarded:

```rust
let configuration = parse_configuration(text).unwrap_or_default();
```

Malformed input need not mean absent input. Propagate the error, explicitly handle
the intended failure category, or justify replacing it with a default. No automatic
rewrite to `?`: propagation can change both contracts and product behavior.

```rust
#[expect(clippy::disallowed_methods, reason = "best-effort diagnostics intentionally treat failed probes as absence")]
fn probe(value: Result<u32, std::num::ParseIntError>) -> Option<u32> {
    value.ok()
}
```

A stale expectation fails. Keep exceptions local and review their reasoning.
The compiler resolves aliases and UFCS. Ordinary `Option` defaults, unrelated
custom `.ok()` methods, typed trait objects, lazy iterator chains, and invariant
`expect` calls are not globally banned. This policy is stricter than universal Rust
correctness and does not catch arbitrary closure-based or string-based error loss.

## Why reuse native checks?

Stable Clippy already meets this selected scope. A new parser or nightly plugin
would add maintenance without improving these checks. Genuinely new semantic
rules may justify a compiler extension later; none is represented here by an
unimplemented placeholder or a misleading textual approximation.

Tests compile isolated crates and verify the intended diagnostics rather than just
any compiler failure. Run from the source repository:

```sh
cargo test --manifest-path rust/Cargo.toml --locked
cargo run --manifest-path rust/Cargo.toml -- --manifest-path rust/Cargo.toml --locked
```
