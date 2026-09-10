#!/usr/bin/env node
import { createHash } from "node:crypto";
import { cpSync, lstatSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const [language, destination, ...extra] = process.argv.slice(2);
if (!["python", "rust"].includes(language) || extra.length || destination?.startsWith("--")) {
  console.error("Usage: node install-native.mjs <python|rust> [destination]");
  process.exit(2);
}
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "assets", `anti-slop-${language}`);
const target = resolve(destination ?? `tools/anti-slop/${language}`);

function inside(parent, child) {
  const path = relative(parent, child);
  return path === "" || (!isAbsolute(path) && path !== ".." && !path.startsWith(`..${sep}`));
}

function hashes(directory) {
  return readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name)).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Refusing bundled symlink: ${path}`);
    if (entry.isDirectory()) return hashes(path);
    return [[relative(source, path).split(sep).join("/"), createHash("sha256").update(readFileSync(path)).digest("hex")]];
  });
}

try {
  if (lstatSync(target, { throwIfNoEntry: false })) throw new Error(`Refusing to overwrite ${target}; stage and review updates separately.`);
  if (inside(source, target) || inside(target, source)) throw new Error("Source and destination must not contain each other.");
  const snapshot = hashes(source);
  mkdirSync(dirname(target), { recursive: true });
  cpSync(source, target, { recursive: true, force: false, errorOnExist: true });
  const provenance = [
    "# Vendored anti-slop provenance", "",
    "Source repository: https://github.com/Pimpmuckl/anti-slop",
    `Source directory: ${language}/`,
    "Source revision: unknown (installed skill bundle; do not infer it from the target repository HEAD).",
    "The SHA-256 values below identify the actual pristine files copied by this installation.",
    "Record a verified upstream revision when available and describe intentional local deviations here.",
    "Preserve local changes during updates; hashes identify bytes, not a recoverable three-way merge base.",
    "", "| File | Pristine SHA-256 |", "| --- | --- |",
    ...snapshot.map(([path, hash]) => `| ${path} | ${hash} |`), "",
  ].join("\n");
  writeFileSync(join(target, "UPSTREAM.md"), provenance, { flag: "wx" });
  console.log(`Copied ${language} anti-slop to ${target}`);
  console.log("Read README.md in that directory; merge settings and run the existing project checks.");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
