# Install or update the native packs

Read instructions, worktree status, manifests, toolchain selection, CI and existing
lint settings first. Use only requested/applicable languages. Existing installations
take the update path. The consuming repository owns copied policy and diagnostics.

## Fresh install

From the target repository:

```sh
node <skill-directory>/scripts/install-native.mjs python
node <skill-directory>/scripts/install-native.mjs rust
```

An optional second argument changes the destination; defaults are
`tools/anti-slop/python/` and `tools/anti-slop/rust/`. Existing paths and symlinked destination ancestors are refused. Use a physical
destination path. This preflight assumes the worktree is not being maliciously
modified concurrently.
Preserve README, LICENSE, presets and the generated UPSTREAM.md hash record.

Python requires 3.11+ and an interpreter capable of the project's syntax. Merge
Ruff checks without replacing target versions, excludes, ignores or extend chains.
Keep mypy/pyright/ty already selected; the mypy preset is only a starter for projects
choosing mypy. Use existing dependency/lock tooling. Add the checker to lint/CI.
Owned-module patching is opt-in and requires agreed module namespaces.

Rust requires 1.85+ with Clippy. Preserve the project toolchain/workspace and its
supported package/feature/target combinations. Install the vendored command or run
it via cargo run, alongside cargo fmt --check. Optional explicit-error restrictions
must be deliberately merged into existing Clippy settings, not replace them or set
a CLIPPY_CONF_DIR that hides them. Rebuild the command after changing policy source.

Run lint, type checks and meaningful tests. Report application findings and only
fix them when authorized; never silently lower severity, add blanket ignores, fake
safety justifications or gratuitous frameworks to make checks pass. Keep formatter
changes separate from semantic changes. Exclude tool/generated directories
explicitly, not every dot-directory.

## Update

Inspect existing customization. Identify and stage the actual incoming upstream
revision separately. Never force-copy over the installed directory. Three-way merge
only with a recoverable pristine base; a hash record alone is not that base. Without
a base, port selected reviewed changes conservatively. Preserve local rules/settings
and resolve conflicting policy/new optional rules explicitly.

Record verified source identity, installed paths, retained deviations and validation.
An installed skill does not prove latest upstream. Unknown revision stays unknown;
never substitute the consuming repository HEAD or an unrelated upstream HEAD.
Review the final diff and report remaining findings and checks that could not run.
