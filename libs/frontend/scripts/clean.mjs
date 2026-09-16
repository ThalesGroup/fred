import { fileURLToPath } from "node:url";
import { readdir, rm } from "node:fs/promises";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(scriptDirectory, "..");

// Caches under target/ are network-provisioned inputs pinned by fixture
// lockfiles, .npmrc and package.json, not build output. Cleaning them strands
// the offline commands, so they survive unless a cold bootstrap is asked for.
// tests/clean.test.mjs fails if a provisioning source names one not listed here.
export const provisionedCaches = [
  "compatible-token",
  "iframe-sdk-consumer-cache",
  "npm-cache",
  "playwright",
  "react-consumer-cache",
];

const generatedPackageOutput = [
  "design-tokens/dist",
  "design-tokens/LICENSE",
  "design-tokens/licenses",
  "ui/.generated",
  "ui/dist",
  "ui/LICENSE",
  "ui/build-evidence.json",
  "ui/licenses",
  "iframe-sdk/.generated",
  "iframe-sdk/dist",
  "iframe-sdk/LICENSE",
  "iframe-sdk/build-evidence.json",
];

export async function clean({ root = workspaceRoot, caches = false } = {}) {
  const target = path.join(root, "target");
  const entries = await readdir(target).catch((error) => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  const removed = caches
    ? entries
    : entries.filter((entry) => !provisionedCaches.includes(entry));
  await Promise.all([
    caches
      ? rm(target, { recursive: true, force: true })
      : Promise.all(
          removed.map((entry) =>
            rm(path.join(target, entry), { recursive: true, force: true }),
          ),
        ),
    ...generatedPackageOutput.map((relative) =>
      rm(path.join(root, relative), { recursive: true, force: true }),
    ),
  ]);
  return {
    target,
    removed: removed.sort(),
    keptCaches: caches
      ? []
      : entries.filter((entry) => provisionedCaches.includes(entry)).sort(),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { keptCaches } = await clean({
    caches: process.argv.includes("--caches"),
  });
  process.stdout.write(
    keptCaches.length
      ? `Kept provisioned caches: ${keptCaches.join(", ")} (make clean-all drops them).\n`
      : "Removed all producer output.\n",
  );
}
