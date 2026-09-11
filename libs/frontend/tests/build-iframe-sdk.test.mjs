import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  assertIframeSdkBuildSourceGraph,
  buildIframeSdk,
  packageRoot,
} from "../scripts/build-iframe-sdk.mjs";

async function hash(relativePath) {
  return createHash("sha256")
    .update(await readFile(path.join(packageRoot, relativePath)))
    .digest("hex");
}

test("iframe SDK output is deterministic, closed, and framework-independent", async () => {
  const outputs = [
    "dist/index.js",
    "dist/protocol.js",
    "dist/types/src/index.d.ts",
    "dist/types/.generated/applicationProtocol.d.ts",
  ];
  const firstEvidence = await buildIframeSdk();
  const firstHashes = await Promise.all(outputs.map(hash));
  const secondEvidence = await buildIframeSdk();
  assert.deepEqual(await Promise.all(outputs.map(hash)), firstHashes);
  assert.deepEqual(secondEvidence, firstEvidence);
  assertIframeSdkBuildSourceGraph(secondEvidence);

  const runtime = await import(
    `${pathToFileURL(path.join(packageRoot, "dist/index.js")).href}?test=${Date.now()}`
  );
  assert.deepEqual(Object.keys(runtime).sort(), [
    "FredApplicationClientError",
    "createFredApplicationClient",
  ]);
  const protocol = await import(
    `${pathToFileURL(path.join(packageRoot, "dist/protocol.js")).href}?test=${Date.now()}`
  );
  assert.equal(protocol.FRED_APP_PROTOCOL_VERSION, "1");
  for (const publicValue of [
    "ACCEPTED_APP_PROTOCOL_VERSIONS",
    "APPLICATION_REQUEST_METHODS",
    "MAX_APPLICATION_REQUEST_HEADERS",
    "MAX_APPLICATION_REQUEST_ID_LENGTH",
    "MAX_PENDING_APPLICATION_REQUESTS",
    "PROTECTED_APPLICATION_HEADERS",
    "isProtectedApplicationHeader",
    "normalizeApplicationRelativePath",
    "parseApplicationFrameMessage",
    "parseApplicationHostMessage",
  ]) {
    assert(publicValue in protocol, publicValue);
  }
  const combined = await Promise.all(
    outputs.map((file) => readFile(path.join(packageRoot, file), "utf8")),
  );
  assert.doesNotMatch(
    combined.join("\n"),
    /react|keycloak|apps\/frontend|node_modules|@fred\/(?:ui|design-tokens)/i,
  );
});

test("iframe SDK source-graph evidence rejects missing and unexpected modules", () => {
  const evidence = {
    sourceAllowlist: [
      "apps/frontend/src/rework/features/applications/applicationProtocol.ts",
      "libs/frontend/iframe-sdk/src/index.ts",
    ],
    builds: {
      index: {
        modules: [
          "libs/frontend/iframe-sdk/.generated/applicationProtocol.ts",
          "libs/frontend/iframe-sdk/src/index.ts",
        ],
        outputs: ["index.js"],
      },
      protocol: {
        modules: ["libs/frontend/iframe-sdk/.generated/applicationProtocol.ts"],
        outputs: ["protocol.js"],
      },
    },
  };
  assert.doesNotThrow(() => assertIframeSdkBuildSourceGraph(evidence));
  assert.throws(
    () =>
      assertIframeSdkBuildSourceGraph({
        ...evidence,
        builds: {
          ...evidence.builds,
          index: { ...evidence.builds.index, modules: [] },
        },
      }),
    /deep-equal/,
  );
  assert.throws(
    () =>
      assertIframeSdkBuildSourceGraph({
        ...evidence,
        builds: {
          ...evidence.builds,
          index: {
            ...evidence.builds.index,
            modules: [...evidence.builds.index.modules, "../outside.ts"],
          },
        },
      }),
    /deep-equal/,
  );
});
