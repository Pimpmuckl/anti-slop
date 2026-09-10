# anti-slop

Opinionated, **vendored** lint policies for TypeScript/JavaScript, Python, and Rust.
Preserve useful type/error information, make escape hatches explainable, and reject
low-evidence shortcuts without fighting each language's idioms.

This is a team-owned engineering policy, not an AI-generated-code detector or a
universal coding standard. The same rules apply to humans and coding agents.

| Language | Implementation | Guide |
| --- | --- | --- |
| TypeScript / JavaScript | Original Oxlint plugins: 18 generic rules and an optional Effect pack | [TypeScript guide](TYPESCRIPT.md) |
| Python | Standard-library-only lexical checker, plus Ruff and type-checker presets | [Python guide](python/README.md) |
| Rust | Dependency-free Cargo command using compiler/Clippy diagnostics, plus optional error-loss policy | [Rust guide](rust/README.md) |

[Design and standards reconciliation](docs/native-design.md) explains which ideas
transfer, which are already native lints, and which are intentionally not enforced.
The existing TypeScript implementation and installation commands are unchanged;
its full former README is preserved in `TYPESCRIPT.md`.

## Install with an agent

```sh
npx skills add Pimpmuckl/anti-slop --skill install-anti-slop
```

Ask the agent to install Python, Rust, TypeScript, or the applicable combination.
It should preserve existing tooling, merge configuration, record provenance, and
run the project's checks. Installation is not permission to rewrite application
code or silently suppress findings.

For native-language packs, the skill's copy-only installer is:

```sh
node <skill-directory>/scripts/install-native.mjs python
node <skill-directory>/scripts/install-native.mjs rust
```

These create `tools/anti-slop/python/` and `tools/anti-slop/rust/`, refuse to replace
existing copies, and include license, documentation, presets, and a pristine-file
hash record. The target repository owns subsequent changes. Updates are staged
and reviewed, not forced over local customization.

## Run the native packs

Python needs Python 3.11+ and no third-party runtime packages:

```sh
python tools/anti-slop/python/anti_slop.py src tests
```

Use it alongside the existing formatter, Ruff, and a type checker. Ruff is not a
type checker; anti-slop is not a replacement for either tool.

Rust needs Rust 1.85+ and Clippy. The command has no Cargo dependencies:

```sh
rustup component add clippy
cargo install --path tools/anti-slop/rust --locked
cargo anti-slop --workspace
```

It preserves native Cargo options, project configuration, toolchain selection,
and diagnostics. Run `cargo fmt --check` separately. No blanket `unwrap`, `clone`,
trait-object, or iterator-chain bans are enabled.

## Develop

```sh
pnpm check                                      # existing TypeScript checks
python -m unittest discover -s python/tests -v
python python/anti_slop.py python/anti_slop.py python/tests
cargo test --manifest-path rust/Cargo.toml --locked
cargo run --manifest-path rust/Cargo.toml -- --manifest-path rust/Cargo.toml --locked
node scripts/sync-native-assets.mjs
node scripts/sync-native-assets.mjs --check
node --test scripts/install-native.test.mjs
```

Native CI also checks Ruff, mypy, formatting, minimum/current Rust toolchains, and
Python runtime/platform fixtures. Never claim that a textual fixture establishes
compiler semantics: the Rust tests actually invoke Clippy on isolated crates.

MIT licensed. Keep bundled licenses and provenance when copying files.
