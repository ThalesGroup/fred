import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { buildReleaseCandidate } from "../scripts/release-candidate.mjs";
import { loadReleaseContract } from "../scripts/release-contract.mjs";

const expectedToolchain = { node: "24.21.0", npm: "11.19.0" };
const gates = {
  archives: { validated: true, reusedPackedBytes: true },
  consumers: { designTokens: {}, ui: {}, iframeSdk: {} },
  browser: {
    dependencyInstallations: 0,
    browserProvisioning: 0,
    externalRequests: 0,
  },
  host: { test: "fixture-host-test" },
};
const applicationToolchain = {
  source: "fixture",
  isolation: "application-owned",
  node: "22.13.0",
  npm: "10.9.2",
};

async function packerFixture(context, calls) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-release-candidate-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  return Object.fromEntries(
    ["designTokens", "ui", "iframeSdk"].map((role) => [
      role,
      async ({ validate, contract }) => {
        calls.push(role);
        assert.equal(validate, true);
        assert(contract);
        const archivePath = path.join(root, `${role}.tgz`);
        await writeFile(archivePath, `${role} candidate bytes`);
        return { archivePath };
      },
    ]),
  );
}

test("candidate generation packs and verifies each selected archive once", async (context) => {
  const contract = await loadReleaseContract();
  const calls = [];
  const result = await buildReleaseCandidate({
    contract,
    sourceCommit: "fixture-commit",
    clean: true,
    producerToolchain: expectedToolchain,
    applicationToolchain,
    runGates: async () => gates,
    packers: await packerFixture(context, calls),
  });
  assert.deepEqual(calls, ["designTokens", "iframeSdk", "ui"]);
  assert.equal(result.archives.length, 3);
  assert.equal(result.evidence.kind, "fixture-candidate-evidence");
});

test("candidate generation fails before packing for dirty, drifted, or unconfirmed input", async (context) => {
  const contract = await loadReleaseContract();
  for (const input of [
    { clean: false, producerToolchain: expectedToolchain, approved: false },
    {
      clean: true,
      producerToolchain: { node: "24.21.1", npm: "11.19.0" },
      approved: false,
    },
    { clean: true, producerToolchain: expectedToolchain, approved: true },
  ]) {
    const calls = [];
    await assert.rejects(
      buildReleaseCandidate({
        contract,
        sourceCommit: "fixture-commit",
        applicationToolchain,
        runGates: async () => gates,
        packers: await packerFixture(context, calls),
        ...input,
      }),
    );
    assert.deepEqual(calls, []);
  }
});

test("changing only a fixture contract state cannot authorize a candidate", async (context) => {
  const contract = await loadReleaseContract();
  contract.state = "maintainer-confirmed";
  const calls = [];
  await assert.rejects(
    buildReleaseCandidate({
      contract,
      sourceCommit: "fixture-commit",
      clean: true,
      producerToolchain: expectedToolchain,
      applicationToolchain,
      approved: true,
      runGates: async () => gates,
      packers: await packerFixture(context, calls),
    }),
    /confirmed source repository|bootstrap authority|fixture/,
  );
  assert.deepEqual(calls, []);
});

test("a failed package gate prevents candidate evidence", async () => {
  const contract = await loadReleaseContract();
  const packers = {
    designTokens: async () => {
      throw new Error("archive validation failed");
    },
    ui: async () => assert.fail("UI packer must not run"),
    iframeSdk: async () => assert.fail("SDK packer must not run"),
  };
  await assert.rejects(
    buildReleaseCandidate({
      contract,
      sourceCommit: "fixture-commit",
      clean: true,
      producerToolchain: expectedToolchain,
      applicationToolchain,
      runGates: async () => gates,
      packers,
    }),
    /archive validation failed/,
  );
});

test("an incomplete archive prevents candidate evidence", async (context) => {
  const contract = await loadReleaseContract();
  const packers = await packerFixture(context, []);
  packers.iframeSdk = async () => ({
    archivePath: path.join(os.tmpdir(), "missing-iframe-sdk.tgz"),
  });
  await assert.rejects(
    buildReleaseCandidate({
      contract,
      sourceCommit: "fixture-commit",
      clean: true,
      producerToolchain: expectedToolchain,
      applicationToolchain,
      packers,
      runGates: async () => gates,
    }),
    /ENOENT/,
  );
});

test("candidate generation rejects archives changed by a later gate", async (context) => {
  const contract = await loadReleaseContract();
  const calls = [];
  await assert.rejects(
    buildReleaseCandidate({
      contract,
      sourceCommit: "fixture-commit",
      clean: true,
      producerToolchain: expectedToolchain,
      applicationToolchain,
      packers: await packerFixture(context, calls),
      runGates: async ({ archivePaths }) => {
        await writeFile(archivePaths.ui, "changed after consumer validation");
        return gates;
      },
    }),
    /archive changed during candidate validation/,
  );
});
