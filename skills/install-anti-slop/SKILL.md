---
name: install-anti-slop
description: Install, configure, or update vendored anti-slop policies for TypeScript/JavaScript, Python, and Rust, preserving repository-owned customizations.
---

# Install or update anti-slop

Read the target repository's agent instructions and worktree status first. Identify
its languages, existing anti-slop installation, toolchains and lint configuration.
Do not replace existing work, infer the latest upstream revision from an installed
skill, or treat installation as permission for application cleanup.

For **TypeScript/JavaScript**, follow [the original TypeScript procedure](TYPESCRIPT.md).
Its existing Oxlint source, optional Effect plugin and copy script are unchanged.

For **Python or Rust**, follow [the native-language procedure](references/native.md).
In mixed repositories, apply the relevant procedures separately and preserve each
language's existing tools. Do not install a runtime or framework only to silence a
rule, or enable optional architecture policies without an explicit project choice.

An existing installation always takes the update path: stage incoming source,
preserve local rules/settings, establish provenance, then validate. Never run a
force-copy over an existing vendored native pack.
