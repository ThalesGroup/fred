import assert from "node:assert/strict";
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { clean, provisionedCaches } from "../scripts/clean.mjs";
import { compatibilityRoot } from "../scripts/provision-compatible-token.mjs";
import { iframeSdkConsumerCache } from "../scripts/provision-iframe-sdk-consumer.mjs";
import { consumerCache } from "../scripts/provision-react-consumer.mjs";

const workspaceRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const disposableOutput = ["archives", "review-evidence", "staged-consumers"];

async function seedWorkspace(context, extraTargetEntries = []) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-frontend-clean-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  for (const entry of [
    ...provisionedCaches,
    ...disposableOutput,
    ...extraTargetEntries,
  ])
    await mkdir(path.join(root, "target", entry), { recursive: true });
  await mkdir(path.join(root, "ui/dist"), { recursive: true });
  await writeFile(path.join(root, "ui/build-evidence.json"), "{}\n");
  return root;
}

test("cleaning removes producer output but keeps the provisioned caches", async (context) => {
  const root = await seedWorkspace(context);
  const result = await clean({ root });
  assert.deepEqual(
    (await readdir(path.join(root, "target"))).sort(),
    [...provisionedCaches].sort(),
  );
  assert.deepEqual(result.removed, [...disposableOutput].sort());
  assert.deepEqual(result.keptCaches, [...provisionedCaches].sort());
  await assert.rejects(readdir(path.join(root, "ui/dist")));
});

test("an unrecognised target entry is treated as disposable output", async (context) => {
  const root = await seedWorkspace(context, ["a-future-evidence-directory"]);
  await clean({ root });
  assert.deepEqual(
    (await readdir(path.join(root, "target"))).sort(),
    [...provisionedCaches].sort(),
  );
});

test("a cold clean drops the provisioned caches too", async (context) => {
  const root = await seedWorkspace(context);
  const result = await clean({ root, caches: true });
  await assert.rejects(readdir(path.join(root, "target")));
  assert.deepEqual(result.keptCaches, []);
  assert.deepEqual(
    result.removed,
    [...provisionedCaches, ...disposableOutput].sort(),
  );
});

test("every cache the tooling provisions survives a clean", async () => {
  const manifest = JSON.parse(
    await readFile(path.join(workspaceRoot, "package.json"), "utf8"),
  );
  const npmrc = await readFile(path.join(workspaceRoot, ".npmrc"), "utf8");
  const declared = {
    "provision-react-consumer.mjs": consumerCache,
    "provision-iframe-sdk-consumer.mjs": iframeSdkConsumerCache,
    "provision-compatible-token.mjs": compatibilityRoot,
    ".npmrc": /^cache=(.+)$/m.exec(npmrc)?.[1].trim(),
    "package.json browser:install": /PLAYWRIGHT_BROWSERS_PATH=(\S+)/.exec(
      manifest.scripts["browser:install"],
    )?.[1],
  };
  for (const [source, location] of Object.entries(declared)) {
    assert(location, `${source} no longer declares a cache location`);
    assert.equal(
      path.dirname(path.resolve(workspaceRoot, location)),
      path.join(workspaceRoot, "target"),
      `${source} caches outside target/`,
    );
    assert(
      provisionedCaches.includes(path.basename(location)),
      `${source} provisions ${path.basename(location)}, which clean would delete`,
    );
  }
});

test("cleaning an already clean workspace is a no-op", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-frontend-clean-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  assert.deepEqual(await clean({ root }), {
    target: path.join(root, "target"),
    removed: [],
    keptCaches: [],
  });
});
