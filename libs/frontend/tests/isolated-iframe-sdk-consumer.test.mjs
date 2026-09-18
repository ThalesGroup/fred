import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertIframeSdkConsumerFixture,
  stageIsolatedIframeSdkConsumer,
} from "../scripts/isolated-iframe-sdk-consumer.mjs";
import { iframeSdkConsumerCache } from "../scripts/provision-iframe-sdk-consumer.mjs";

// Populating that cache needs network access, which `make test` does not have.
// Without this the suite reports a red test on a clean checkout, which reads as
// a regression rather than "you have not provisioned yet" — and the skip
// message says exactly what to run.
const cacheReady = await stat(path.join(iframeSdkConsumerCache, "_cacache")).then(
  () => true,
  () => false,
);
const skipWithoutCache = cacheReady
  ? false
  : `iframe SDK consumer cache absent — run 'make consumer-provision-iframe-sdk' (needs network)`;

test("the iframe SDK consumer is neutral and lockfile-pinned", async () => {
  await assertIframeSdkConsumerFixture();
});

test("the actual iframe SDK archive installs and builds outside FRED", { skip: skipWithoutCache }, async () => {
  const evidence = await stageIsolatedIframeSdkConsumer();
  const sdkManifest = JSON.parse(
    await readFile(
      new URL("../iframe-sdk/package.json", import.meta.url),
      "utf8",
    ),
  );
  assert.deepEqual(evidence.dependencyGraph, {
    [sdkManifest.name]: sdkManifest.version,
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
