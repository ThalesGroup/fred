import assert from "node:assert/strict";
import { lstat, readdir } from "node:fs/promises";
import path from "node:path";

export function assertArchiveEntriesSafe(listing) {
  for (const entry of listing.trim().split("\n").filter(Boolean)) {
    assert(
      entry === "package" || entry.startsWith("package/"),
      `archive entry escapes package/: ${entry}`,
    );
    assert(
      !entry.split("/").includes(".."),
      `archive entry contains traversal: ${entry}`,
    );
  }
}

export async function listArchiveFiles(root, relative = "") {
  const files = [];
  for (const entry of await readdir(path.join(root, relative), {
    withFileTypes: true,
  })) {
    const entryPath = path.posix.join(relative, entry.name);
    if (entry.isDirectory())
      files.push(...(await listArchiveFiles(root, entryPath)));
    else files.push(entryPath);
  }
  return files.sort();
}

export async function assertNoArchiveLinks(root, files) {
  for (const file of files) {
    assert.equal(
      (await lstat(path.join(root, file))).isSymbolicLink(),
      false,
      `archive contains a symbolic link: ${file}`,
    );
  }
}

export function dependencyEntries(manifest) {
  return [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
    "overrides",
  ].flatMap((field) =>
    Object.entries(manifest[field] ?? {}).map(([name, version]) => ({
      field,
      name,
      version,
    })),
  );
}
