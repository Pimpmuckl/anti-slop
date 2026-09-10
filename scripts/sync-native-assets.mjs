import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const excluded = new Set(["tests", "target", "__pycache__", ".ruff_cache", ".mypy_cache"]);
const args = process.argv.slice(2);
if (args.some((arg) => arg !== "--check")) throw new Error("Usage: sync-native-assets.mjs [--check]");
const check = args.includes("--check");

function files(directory, source = false) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (source && excluded.has(entry.name)) return [];
    if (entry.isSymbolicLink()) throw new Error(`Distribution contains a symlink: ${entry.name}`);
    const path = join(directory, entry.name);
    return entry.isDirectory() ? files(path, source) : [path];
  });
}

for (const language of ["python", "rust"]) {
  const source = join(root, language);
  const destination = join(root, "skills/install-anti-slop/assets", `anti-slop-${language}`);
  const expected = files(source, true).map((path) => relative(source, path)).sort();
  if (check) {
    const actual = existsSync(destination)
      ? files(destination).map((path) => relative(destination, path)).sort()
      : [];
    if (JSON.stringify(expected) !== JSON.stringify(actual)) {
      throw new Error(`${language} skill assets differ; run node scripts/sync-native-assets.mjs`);
    }
    for (const path of expected) {
      if (!readFileSync(join(source, path)).equals(readFileSync(join(destination, path)))) {
        throw new Error(`${language}/${path} differs from its skill asset`);
      }
    }
  } else {
    rmSync(destination, { recursive: true, force: true });
    for (const path of expected) {
      mkdirSync(dirname(join(destination, path)), { recursive: true });
      cpSync(join(source, path), join(destination, path));
    }
  }
}
console.log(check ? "Native skill assets match their sources." : "Synced Python and Rust skill assets.");
