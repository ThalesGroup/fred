import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { assertBrowserPrerequisites } from "../scripts/browser-smoke.mjs";

async function prerequisiteFixture(context) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-browser-prereqs-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const tokenOutput = path.join(root, "tokens");
  const reactOutput = path.join(root, "react");
  const browserPath = path.join(root, "chromium");
  await Promise.all([
    mkdir(tokenOutput),
    mkdir(reactOutput),
    writeFile(browserPath, "fixture"),
  ]);
  await Promise.all([
    writeFile(path.join(tokenOutput, "tokens-only.html"), "fixture"),
    writeFile(path.join(reactOutput, "index.html"), "fixture"),
  ]);
  return { browserPath, tokenOutput, reactOutput };
}

test("accepts fully provisioned browser smoke prerequisites", async (context) => {
  const prerequisites = await prerequisiteFixture(context);
  await assert.doesNotReject(assertBrowserPrerequisites(prerequisites));
});

test("missing browser fails with the provisioning command", async (context) => {
  const prerequisites = await prerequisiteFixture(context);
  await rm(prerequisites.browserPath);
  await assert.rejects(
    assertBrowserPrerequisites(prerequisites),
    /Playwright Chromium is missing; run npm run browser:install during provisioning/,
  );
});

test("browser smoke does not bootstrap missing staged consumers", async (context) => {
  const prerequisites = await prerequisiteFixture(context);
  await rm(path.join(prerequisites.reactOutput, "index.html"));
  await assert.rejects(
    assertBrowserPrerequisites(prerequisites),
    /staged React consumer is missing; run npm run test:consumer first/,
  );
  await assert.rejects(
    stat(path.join(prerequisites.reactOutput, "index.html")),
    (error) => {
      assert.equal(error.code, "ENOENT");
      return true;
    },
  );
});
