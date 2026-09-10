import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const script = join(root, "skills/install-anti-slop/scripts/install-native.mjs");

for (const language of ["python", "rust"]) {
  test(`${language}: complete installation, provenance, and no overwriting local changes`, () => {
    const directory = realpathSync(mkdtempSync(join(tmpdir(), "anti-slop-install-")));
    try {
      const result = spawnSync(process.execPath, [script, language], { cwd: directory, encoding: "utf8" });
      assert.equal(result.status, 0, result.stderr);
      const target = join(directory, "tools/anti-slop", language);
      const entry = language === "python" ? "anti_slop.py" : "src/main.rs";
      assert.equal(readFileSync(join(target, entry), "utf8"), readFileSync(join(root, language, entry), "utf8"));
      assert.match(readFileSync(join(target, "LICENSE"), "utf8"), /MIT License/);
      assert.match(readFileSync(join(target, "UPSTREAM.md"), "utf8"), /Source revision: unknown/);
      assert.match(readFileSync(join(target, "UPSTREAM.md"), "utf8"), /[a-f0-9]{64}/);
      writeFileSync(join(target, entry), "local customization");
      const repeat = spawnSync(process.execPath, [script, language], { cwd: directory, encoding: "utf8" });
      assert.notEqual(repeat.status, 0);
      assert.equal(readFileSync(join(target, entry), "utf8"), "local customization");
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
}

test("custom destinations work and existing empty directories are not replaced", () => {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), "anti-slop-install-")));
  try {
    let result = spawnSync(process.execPath, [script, "python", "custom tools"], { cwd: directory, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    mkdirSync(join(directory, "existing"));
    result = spawnSync(process.execPath, [script, "rust", "existing"], { cwd: directory, encoding: "utf8" });
    assert.notEqual(result.status, 0);
    result = spawnSync(process.execPath, [script, "rust", "--force"], { cwd: directory, encoding: "utf8" });
    assert.equal(result.status, 2);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("relative destinations cannot escape through a symlinked ancestor", (t) => {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), "anti-slop-install-")));
  try {
    const worktree = join(directory, "worktree");
    const outside = join(directory, "outside");
    mkdirSync(worktree);
    mkdirSync(outside);
    try {
      symlinkSync(outside, join(worktree, "linked"), process.platform === "win32" ? "junction" : "dir");
    } catch (error) {
      if (error.code !== "EPERM" && error.code !== "EACCES") throw error;
      t.skip("The host does not permit directory symlinks/junctions");
      return;
    }
    for (const destination of ["linked/copied", "linked/missing-parent/copied"]) {
      const result = spawnSync(process.execPath, [script, "python", destination], { cwd: worktree, encoding: "utf8" });
      assert.equal(result.status, 1, result.stderr);
      assert.match(result.stderr, /symlinked destination ancestor/);
      assert.equal(existsSync(join(outside, "copied")), false);
      assert.equal(existsSync(join(outside, "missing-parent")), false);
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("a dangling destination ancestor is rejected without creating its target", (t) => {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), "anti-slop-install-")));
  try {
    const missing = join(directory, "missing");
    try {
      symlinkSync(missing, join(directory, "linked"), process.platform === "win32" ? "junction" : "dir");
    } catch (error) {
      if (error.code !== "EPERM" && error.code !== "EACCES") throw error;
      t.skip("The host does not permit directory symlinks/junctions");
      return;
    }
    const result = spawnSync(process.execPath, [script, "rust", "linked/copied"], { cwd: directory, encoding: "utf8" });
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /symlinked destination ancestor/);
    assert.equal(existsSync(missing), false);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("an explicitly selected physical absolute destination remains supported", () => {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), "anti-slop-install-")));
  try {
    const worktree = join(directory, "worktree");
    const target = join(directory, "explicit destination");
    mkdirSync(worktree);
    const result = spawnSync(process.execPath, [script, "python", target], { cwd: worktree, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(join(target, "anti_slop.py")), true);
    assert.equal(existsSync(join(target, "UPSTREAM.md")), true);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
