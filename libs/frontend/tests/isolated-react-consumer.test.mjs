import assert from "node:assert/strict";
import {
  cp,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertReactConsumerFixture,
  assertNoLinks,
  stageIsolatedReactConsumer,
  workspaceRoot,
} from "../scripts/isolated-react-consumer.mjs";

const fixtureRoot = path.join(workspaceRoot, "fixtures/react-consumer");

test("the React consumer has pinned registry dependencies and explicit package CSS", async () => {
  await assertReactConsumerFixture();
});

test("missing explicit UI CSS fails before installation", async (context) => {
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-consumer-fixture-"),
  );
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await cp(fixtureRoot, temporary, { recursive: true });
  const sourcePath = path.join(temporary, "src/main.tsx");
  const source = await readFile(sourcePath, "utf8");
  await writeFile(
    sourcePath,
    source.replace('import "@fred/ui/styles.css";\n', ""),
  );
  await assert.rejects(
    assertReactConsumerFixture(temporary),
    /must explicitly import.*@fred\/ui\/styles\.css/,
  );
});

test("an absent dependency cache fails actionably without provisioning", async () => {
  const missingCache = path.join(os.tmpdir(), "fred-cache-that-does-not-exist");
  await assert.rejects(
    stageIsolatedReactConsumer({ cachePath: missingCache }),
    new RegExp(`cache is missing at ${missingCache}.*consumer:provision`),
  );
});

test("local dependency fallbacks are rejected", async (context) => {
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-consumer-local-"),
  );
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await cp(fixtureRoot, temporary, { recursive: true });
  const manifestPath = path.join(temporary, "package.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  manifest.dependencies.react = "file:../../node_modules/react";
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  await assert.rejects(assertReactConsumerFixture(temporary));
});

test("consumer package symlinks are rejected", async (context) => {
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-linked-package-"),
  );
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await writeFile(path.join(temporary, "source.js"), "fixture");
  await symlink("source.js", path.join(temporary, "index.js"));
  await assert.rejects(assertNoLinks(temporary), /contains a link/);
});

test("missing React peer prerequisites are rejected", async (context) => {
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-consumer-peer-"),
  );
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await cp(fixtureRoot, temporary, { recursive: true });
  const manifestPath = path.join(temporary, "package.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  delete manifest.dependencies.react;
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  await assert.rejects(assertReactConsumerFixture(temporary));
});

test("an incomplete cache fails actionably without a network fallback", async (context) => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-empty-cache-"));
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await mkdir(path.join(temporary, "_cacache"));
  await assert.rejects(
    stageIsolatedReactConsumer({ cachePath: temporary }),
    /lockfile-pinned cache may be incomplete.*consumer:provision/s,
  );
});
