import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertIframeSdkConsumerFixture,
  stageIsolatedIframeSdkConsumer,
} from "../scripts/isolated-iframe-sdk-consumer.mjs";

test("the iframe SDK consumer is neutral and lockfile-pinned", async () => {
  await assertIframeSdkConsumerFixture();
});

test("the actual iframe SDK archive installs and builds outside FRED", async () => {
  const evidence = await stageIsolatedIframeSdkConsumer();
  assert.deepEqual(evidence.dependencyGraph, {
    "@fred/iframe-sdk": "0.0.0-development",
    typescript: "5.9.3",
    vite: "6.4.3",
  });
  assert.equal(evidence.network, "npm offline mode");
  assert(evidence.outputFiles.includes("child.html"));
});

test("an absent SDK consumer cache fails actionably", async () => {
  const missingCache = path.join(
    os.tmpdir(),
    "fred-iframe-sdk-cache-that-does-not-exist",
  );
  await assert.rejects(
    stageIsolatedIframeSdkConsumer({ cachePath: missingCache }),
    /cache is missing.*consumer:provision:iframe-sdk/,
  );
});

test("an incomplete SDK consumer cache does not fall back to the network", async (context) => {
  const emptyCache = await mkdtemp(
    path.join(os.tmpdir(), "fred-iframe-sdk-empty-cache-"),
  );
  context.after(() => rm(emptyCache, { recursive: true, force: true }));
  await mkdir(path.join(emptyCache, "_cacache"));
  await assert.rejects(
    stageIsolatedIframeSdkConsumer({ cachePath: emptyCache }),
    /Offline iframe SDK consumer installation failed.*consumer:provision:iframe-sdk/s,
  );
});
