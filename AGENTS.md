# Repository guidance

- `src/` is the canonical TypeScript/Oxlint implementation; `python/` and `rust/` are the native-language packs.
- Keep reusable rules generic. Never add application-specific names, paths or exceptions.
- For TypeScript, use Oxlint's ESTree API; do not add another production parser. Preserve the existing RuleTester coverage and installation workflow.
- Python uses standard-library AST/token analysis with documented local scope. Add positive and close negative fixtures; never import analyzed application modules.
- Rust policies use actual compiler/Clippy diagnostics, not method-name matching. Test aliases, similar-looking valid methods and reasoned/stale exceptions against a real compiler.
- After TypeScript production edits, run `pnpm sync:skill-assets`. After Python/Rust production edits, run `node scripts/sync-native-assets.mjs`.
- Run `pnpm check`, Python tests/checker, Rust tests/policy, native asset consistency and installer tests before committing when the required tools are available. Report checks that could not run; never imply unrun checks passed.
- Preserve formatter ownership, local configuration, licenses and provenance. Avoid blanket bans, speculative abstractions and semantic autofixes without sufficient evidence.
