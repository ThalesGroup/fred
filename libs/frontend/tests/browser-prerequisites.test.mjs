import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, stat, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertBrowserPrerequisites,
  assertProvisionedChromium,
} from "../scripts/browser-smoke.mjs";

async function prerequisiteFixture(context) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-browser-prereqs-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const tokenOutput = path.join(root, "tokens");
  const reactOutput = path.join(root, "react");
  const iframeSdkOutput = path.join(root, "iframe-sdk");
  const browserPath = path.join(root, "chromium");
  await Promise.all([
    mkdir(tokenOutput),
    mkdir(reactOutput),
    mkdir(iframeSdkOutput),
    writeFile(browserPath, "fixture"),
  ]);
  await Promise.all([
    writeFile(path.join(tokenOutput, "tokens-only.html"), "fixture"),
    writeFile(path.join(reactOutput, "index.html"), "fixture"),
    ...["index.html", "child.html", "attacker.html"].map((file) =>
      writeFile(path.join(iframeSdkOutput, file), "fixture"),
    ),
  ]);
  return { browserPath, tokenOutput, reactOutput, iframeSdkOutput };
}

test("accepts fully provisioned browser smoke prerequisites", async (context) => {
  const prerequisites = await prerequisiteFixture(context);
  await assert.doesNotReject(assertBrowserPrerequisites(prerequisites));
});

test("SDK-only browser checks require no token or React output and reject unknown checks", async (context) => {
  const prerequisites = await prerequisiteFixture(context);
  await rm(prerequisites.tokenOutput, { recursive: true });
  await rm(prerequisites.reactOutput, { recursive: true });
  await assert.doesNotReject(
    assertBrowserPrerequisites({ ...prerequisites, checks: ["iframeSdk"] }),
  );
  await assert.rejects(
    assertBrowserPrerequisites({ ...prerequisites, checks: ["not-a-gate"] }),
    /unknown browser check/,
  );
  await assert.rejects(
    assertBrowserPrerequisites({
      ...prerequisites,
      checks: ["iframeSdk", "iframeSdk"],
    }),
    /duplicate browser check/,
  );
  await assert.rejects(
    assertBrowserPrerequisites({ ...prerequisites, checks: ["ui"] }),
    /staged React consumer is missing/,
  );
});

test("registry verification requires Chromium inside the explicit provisioned path", async (context) => {
  const prerequisites = await prerequisiteFixture(context);
  await assert.doesNotReject(
    assertProvisionedChromium({
      browsersPath: path.dirname(prerequisites.browserPath),
      browserPath: prerequisites.browserPath,
    }),
  );
  await assert.rejects(
    assertProvisionedChromium({
      browsersPath: "",
      browserPath: prerequisites.browserPath,
    }),
    /PLAYWRIGHT_BROWSERS_PATH is required/,
  );
  const otherRoot = path.join(path.dirname(prerequisites.browserPath), "other");
  await mkdir(otherRoot);
  await assert.rejects(
    assertProvisionedChromium({
      browsersPath: otherRoot,
      browserPath: prerequisites.browserPath,
    }),
    /does not resolve from PLAYWRIGHT_BROWSERS_PATH/,
  );
  const linkedRoot = path.join(
    path.dirname(prerequisites.browserPath),
    "linked-cache",
  );
  const linkedBrowser = path.join(linkedRoot, "chromium");
  await mkdir(linkedRoot);
  await symlink(prerequisites.browserPath, linkedBrowser);
  await assert.rejects(
    assertProvisionedChromium({
      browsersPath: linkedRoot,
      browserPath: linkedBrowser,
    }),
    /does not resolve from PLAYWRIGHT_BROWSERS_PATH/,
  );
});

test("browser smoke does not build a missing iframe SDK consumer", async (context) => {
  const prerequisites = await prerequisiteFixture(context);
  await rm(path.join(prerequisites.iframeSdkOutput, "child.html"));
  await assert.rejects(
    assertBrowserPrerequisites(prerequisites),
    /staged iframe SDK consumer is missing; run npm run test:consumer first/,
  );
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
