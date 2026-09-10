//! A policy runner, not another Rust parser. Clippy owns type and method resolution.
use std::env;
use std::ffi::{OsStr, OsString};
use std::process::{Command, ExitCode};

const LINTS: &[&str] = &[
    "unused_must_use",
    "unsafe_op_in_unsafe_fn",
    "unfulfilled_lint_expectations",
    "clippy::correctness",
    "clippy::undocumented_unsafe_blocks",
    "clippy::missing_safety_doc",
    "clippy::allow_attributes_without_reason",
    "clippy::let_underscore_future",
    "clippy::let_underscore_must_use",
    "clippy::await_holding_lock",
    "clippy::await_holding_refcell_ref",
    "clippy::unused_io_amount",
    "clippy::clone_on_copy",
    "clippy::needless_collect",
    "clippy::map_err_ignore",
    "clippy::disallowed_methods",
    "clippy::disallowed_types",
    "clippy::disallowed_macros",
];

const HELP: &str = "cargo anti-slop [CARGO CLIPPY OPTIONS] [-- RUSTC OPTIONS]

Runs a curated set of compiler/Clippy checks as errors, without rewriting source.
Defaults to --all-targets unless an explicit Cargo target selector is supplied.
Pass --workspace and feature/target options explicitly for your project.
Existing clippy.toml, Cargo configuration, toolchain, and lint attributes apply.
Trailing rustc options can explicitly override the policy, as with cargo clippy.

  cargo anti-slop --workspace --all-features
  cargo anti-slop --manifest-path crates/service/Cargo.toml --lib
  cargo anti-slop --print-lints

Install Clippy with: rustup component add clippy
Optional error-loss restrictions: merge policies/explicit-errors.clippy.toml
into your existing Clippy configuration; do not replace project settings.
";

fn has_target_selector(args: &[OsString]) -> bool {
    const FLAGS: &[&str] = &[
        "--lib", "--bin", "--bins", "--example", "--examples", "--test", "--tests",
        "--bench", "--benches", "--all-targets",
    ];
    args.iter().any(|arg| {
        let value = arg.to_string_lossy();
        FLAGS.iter().any(|flag| value == *flag || value.starts_with(&format!("{flag}=")))
    })
}

fn clippy_args(args: &[OsString]) -> Vec<OsString> {
    let separator = args.iter().position(|arg| arg == OsStr::new("--"));
    let cargo_args = &args[..separator.unwrap_or(args.len())];
    let mut result = vec![OsString::from("clippy")];
    if !has_target_selector(cargo_args) {
        result.push(OsString::from("--all-targets"));
    }
    result.extend_from_slice(cargo_args);
    result.push(OsString::from("--"));
    result.extend(LINTS.iter().map(|lint| OsString::from(format!("-D{lint}"))));
    if let Some(index) = separator {
        result.extend_from_slice(&args[index + 1..]);
    }
    result
}

fn main() -> ExitCode {
    let mut args: Vec<OsString> = env::args_os().skip(1).collect();
    // Cargo subcommands receive their subcommand name as the first argument.
    if args.first().is_some_and(|arg| arg == OsStr::new("anti-slop")) {
        args.remove(0);
    }
    if args.len() == 1 {
        if args[0] == OsStr::new("--help") || args[0] == OsStr::new("-h") {
            print!("{HELP}");
            return ExitCode::SUCCESS;
        }
        if args[0] == OsStr::new("--print-lints") {
            println!("{}", LINTS.join("\n"));
            return ExitCode::SUCCESS;
        }
        if args[0] == OsStr::new("--version") || args[0] == OsStr::new("-V") {
            println!("cargo-anti-slop {}", env!("CARGO_PKG_VERSION"));
            return ExitCode::SUCCESS;
        }
    }
    let cargo = env::var_os("CARGO").unwrap_or_else(|| OsString::from("cargo"));
    match Command::new(cargo).args(clippy_args(&args)).status() {
        Ok(status) => ExitCode::from(status.code().and_then(|code| u8::try_from(code).ok()).unwrap_or(1)),
        Err(error) => {
            eprintln!("anti-slop: could not run Cargo: {error}. Install Rust and the Clippy component.");
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn arguments(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    #[test]
    fn defaults_to_all_targets_without_choosing_features_or_workspace() {
        let args = clippy_args(&[]);
        assert_eq!(args[0], "clippy");
        assert_eq!(args[1], "--all-targets");
        assert_eq!(args[2], "--");
        assert!(!args.contains(&OsString::from("--all-features")));
        assert!(!args.contains(&OsString::from("--workspace")));
        assert!(args.contains(&OsString::from("-Dclippy::let_underscore_must_use")));
    }

    #[test]
    fn preserves_cargo_options_and_trailing_rustc_overrides() {
        let args = clippy_args(&arguments(&[
            "--manifest-path", "a path/Cargo.toml", "--lib", "--", "-Adead_code",
        ]));
        assert_eq!(&args[..4], &arguments(&["clippy", "--manifest-path", "a path/Cargo.toml", "--lib"]));
        assert!(!args.contains(&OsString::from("--all-targets")));
        assert_eq!(args.last(), Some(&OsString::from("-Adead_code")));
    }

    #[test]
    fn recognizes_equals_target_selectors_and_does_not_parse_rustc_options() {
        let args = clippy_args(&arguments(&["--bin=worker"]));
        assert!(!args.contains(&OsString::from("--all-targets")));
        let args = clippy_args(&arguments(&["--", "--test"]));
        assert_eq!(args[1], "--all-targets");
    }
}
