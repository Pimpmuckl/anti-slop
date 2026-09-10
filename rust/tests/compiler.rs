//! Exercise real compiler diagnostics, including aliases and look-alike methods.
use std::fs;
use std::path::PathBuf;
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_ID: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new(source: &str, explicit_errors: bool) -> Self {
        let path = std::env::temp_dir().join(format!(
            "anti-slop-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).expect("create isolated fixture");
        fs::create_dir(path.join("src")).expect("create fixture source directory");
        fs::write(
            path.join("Cargo.toml"),
            "[package]\nname = \"anti-slop-fixture\"\nversion = \"0.0.0\"\nedition = \"2021\"\n[workspace]\n",
        )
        .expect("write fixture manifest");
        fs::write(path.join("src/lib.rs"), source).expect("write fixture source");
        fs::write(
            path.join("clippy.toml"),
            if explicit_errors {
                include_str!("../policies/explicit-errors.clippy.toml")
            } else {
                ""
            },
        )
        .expect("write fixture configuration");
        Self(path)
    }

    fn check(&self) -> Output {
        Command::new(env!("CARGO_BIN_EXE_cargo-anti-slop"))
            .args(["--offline", "--message-format=json"])
            .current_dir(&self.0)
            .env("CLIPPY_CONF_DIR", &self.0)
            .env("CARGO_TARGET_DIR", self.0.join("target"))
            .env_remove("RUSTFLAGS")
            .env_remove("CARGO_ENCODED_RUSTFLAGS")
            .output()
            .expect("run anti-slop with the installed compiler")
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if let Err(error) = fs::remove_dir_all(&self.0) {
            eprintln!("Could not clean fixture {}: {error}", self.0.display());
        }
    }
}

fn text(output: &Output) -> String {
    format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    )
}

#[test]
fn discarded_result_and_future_are_detected() {
    let fixture = Fixture::new(
        r#"
        pub fn ignore_result(text: &str) { let _ = text.parse::<u32>(); }
        pub async fn work() {}
        pub fn ignore_future() { let _ = work(); }
        "#,
        false,
    );
    let output = fixture.check();
    assert!(!output.status.success(), "{}", text(&output));
    assert!(text(&output).contains("clippy::let_underscore_must_use"), "{}", text(&output));
    assert!(text(&output).contains("clippy::let_underscore_future"), "{}", text(&output));
}

#[test]
fn result_aliases_and_ufcs_are_resolved_by_the_compiler() {
    let fixture = Fixture::new(
        r#"
        pub type Parsed = Result<u32, std::num::ParseIntError>;
        pub fn default(value: Parsed) -> u32 { value.unwrap_or_default() }
        pub fn fallback(value: Parsed) -> u32 { value.unwrap_or(0) }
        pub fn erase(value: Parsed) -> Option<u32> { value.ok() }
        pub fn ufcs(value: Parsed) -> Option<u32> { Result::ok(value) }
        "#,
        true,
    );
    let output = fixture.check();
    assert!(!output.status.success(), "{}", text(&output));
    assert!(text(&output).contains("clippy::disallowed_methods"), "{}", text(&output));
    assert!(text(&output).contains("unwrap_or_default"), "{}", text(&output));
    assert!(text(&output).contains("Result::ok"), "{}", text(&output));
}

#[test]
fn option_defaults_custom_methods_trait_objects_and_lazy_iterators_are_valid() {
    let fixture = Fixture::new(
        r#"
        pub struct Custom;
        impl Custom {
            pub fn ok(self) -> bool { true }
            pub fn unwrap_or_default(self) -> u32 { 0 }
            pub fn unwrap_or(self, value: u32) -> u32 { value }
        }
        pub fn optional(value: Option<u32>) -> u32 { value.unwrap_or_default() }
        pub fn display(value: &dyn std::fmt::Display) -> String { value.to_string() }
        pub fn lazy(values: impl Iterator<Item = i32>) -> Vec<i32> {
            values.filter(|value| *value > 0).map(|value| value + 1).collect()
        }
        "#,
        true,
    );
    let output = fixture.check();
    assert!(output.status.success(), "{}", text(&output));
}

#[test]
fn core_does_not_ban_result_fallbacks_or_invariant_panics() {
    let fixture = Fixture::new(
        r#"
        pub fn default(value: Result<u32, std::num::ParseIntError>) -> u32 {
            value.unwrap_or_default()
        }
        pub fn invariant(value: Option<u32>) -> u32 {
            value.expect("caller established this invariant")
        }
        "#,
        false,
    );
    let output = fixture.check();
    assert!(output.status.success(), "{}", text(&output));
}

#[test]
fn reasoned_expectation_is_allowed_but_stale_expectation_fails() {
    let justified = Fixture::new(
        r#"
        #[expect(clippy::disallowed_methods, reason = "best-effort diagnostic probe intentionally reports absence")]
        pub fn probe(value: Result<u32, std::num::ParseIntError>) -> Option<u32> { value.ok() }
        "#,
        true,
    );
    let output = justified.check();
    assert!(output.status.success(), "{}", text(&output));
    let stale = Fixture::new(
        r#"
        #[expect(clippy::disallowed_methods, reason = "obsolete exception")]
        pub fn clean() -> u32 { 42 }
        "#,
        true,
    );
    let output = stale.check();
    assert!(!output.status.success(), "{}", text(&output));
    assert!(text(&output).contains("unfulfilled_lint_expectations"), "{}", text(&output));
}

#[test]
fn undocumented_unsafe_is_rejected() {
    let fixture = Fixture::new(
        r#"
        pub fn read() -> u32 {
            let value = 42;
            let pointer = &value as *const u32;
            unsafe { *pointer }
        }
        "#,
        false,
    );
    let output = fixture.check();
    assert!(!output.status.success(), "{}", text(&output));
    assert!(text(&output).contains("clippy::undocumented_unsafe_blocks"), "{}", text(&output));
}
