// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  loadCompatibilityLedger,
  resolveUiTokenDependency,
} from "../scripts/compatibility-baselines.mjs";
import { loadReleaseContract } from "../scripts/release-contract.mjs";
import {
  provisionCompatibleToken,
  assertCompatibleTokenProvision,
} from "../scripts/provision-compatible-token.mjs";

const contract = await loadReleaseContract();
const ledger = await loadCompatibilityLedger();

test("UI-only provisioning verifies exact bytes and provenance without historical CI ZIP", async (context) => {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "fred-compatible-token-test-"),
  );
  context.after(() => rm(root, { recursive: true, force: true }));
  const archivePath = path.join(root, "registry.tgz");
  // This fixture stands for independently fetched registry bytes, not approved evidence.
  await writeFile(archivePath, "controlled registry bytes");
  const fixtureLedger = structuredClone(ledger);
  const { sha512Integrity } = await import("../scripts/release-evidence.mjs");
  fixtureLedger.baselines[0].expected.integrity =
    await sha512Integrity(archivePath);
  fixtureLedger.baselines[0].expected.artifactDigest =
    fixtureLedger.baselines[0].expected.integrity;
  const fixtureContract = structuredClone(contract);
  const { baselineDigest } =
    await import("../scripts/compatibility-baselines.mjs");
  fixtureContract.approvedBaselineDigest = baselineDigest(fixtureLedger);
  // The currently registered token member may advance independently of a UI-only release.
  fixtureContract.packages.designTokens.version = "0.1.1-alpha.1";
  const expected = fixtureLedger.baselines[0].expected;
  const calls = [];
  const outputRoot = path.join(root, "prepared");
  await assert.rejects(
    assertCompatibleTokenProvision({
      contract: fixtureContract,
      ledger: fixtureLedger,
      outputRoot,
    }),
    /run make compatibility-provision/,
  );
  const validRegistryPackage = {
    metadata: {
      name: fixtureContract.packages.designTokens.name,
      version: "0.1.0-alpha.1",
      dist: { integrity: expected.integrity },
    },
    archivePath,
  };
  for (const [registryPackage, failure] of [
    [
      {
        ...validRegistryPackage,
        metadata: {
          ...validRegistryPackage.metadata,
          version: "0.1.1-alpha.1",
        },
      },
      /baseline registry identity differs/,
    ],
    [
      {
        ...validRegistryPackage,
        metadata: {
          ...validRegistryPackage.metadata,
          dist: { integrity: "sha512-incorrect" },
        },
      },
      /baseline registry metadata integrity differs/,
    ],
  ]) {
    await assert.rejects(
      provisionCompatibleToken({
        contract: fixtureContract,
        ledger: fixtureLedger,
        outputRoot,
        resolvePackage: async () => registryPackage,
        verifyProvenance: async () =>
          assert.fail("invalid metadata must stop before provenance"),
        runCommand: async () =>
          assert.fail("invalid metadata must not warm the cache"),
      }),
      failure,
    );
  }
  await assert.rejects(
    provisionCompatibleToken({
      contract: fixtureContract,
      ledger: fixtureLedger,
      outputRoot,
      resolvePackage: async () => validRegistryPackage,
      verifyProvenance: async () => ({
        cryptographicallyVerified: true,
        identity: {
          artifactDigest: expected.artifactDigest,
          repository: "unexpected/repository",
          sourceCommit: expected.sourceCommit,
          workflow: expected.workflow,
        },
      }),
      runCommand: async () =>
        assert.fail("wrong provenance must not warm the cache"),
    }),
    /provenance repository differs/,
  );
  await provisionCompatibleToken({
    contract: fixtureContract,
    ledger: fixtureLedger,
    outputRoot,
    cachePath: path.join(root, "cache"),
    resolvePackage: async ({
      coordinate,
      candidate,
      expectedPackage,
      contract: registryContract,
    }) => {
      calls.push("exact-registry");
      assert.equal(coordinate, fixtureLedger.baselines[0].coordinate);
      assert.equal(candidate.integrity, expected.integrity);
      assert.equal(expectedPackage.version, "0.1.0-alpha.1");
      assert.equal(
        registryContract.packages.designTokens.version,
        "0.1.0-alpha.1",
      );
      return validRegistryPackage;
    },
    verifyProvenance: async () => {
      calls.push("cryptographic-provenance-fixture");
      return {
        cryptographicallyVerified: true,
        identity: {
          artifactDigest: expected.artifactDigest,
          repository: expected.repository,
          sourceCommit: expected.sourceCommit,
          workflow: expected.workflow,
          invocationRepository: expected.repository,
          runId: "12345",
          runAttempt: "1",
        },
      };
    },
    runCommand: async (command, args) => {
      calls.push("cache-add");
      assert.equal(command, "npm");
      assert.deepEqual(args.slice(0, 3), [
        "cache",
        "add",
        fixtureLedger.baselines[0].coordinate,
      ]);
    },
  });
  assert.deepEqual(calls, [
    "exact-registry",
    "cryptographic-provenance-fixture",
    "cache-add",
  ]);
  const prepared = await assertCompatibleTokenProvision({
    contract: fixtureContract,
    ledger: fixtureLedger,
    outputRoot,
  });
  assert.equal(
    prepared.receipt.coordinate,
    fixtureLedger.baselines[0].coordinate,
  );
  await writeFile(prepared.archivePath, "modified after provisioning");
  await assert.rejects(
    assertCompatibleTokenProvision({
      contract: fixtureContract,
      ledger: fixtureLedger,
      outputRoot,
    }),
    /prepared token bytes differ/,
  );
  await cp(archivePath, prepared.archivePath);
  const receiptPath = path.join(outputRoot, "receipt.json");
  const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
  receipt.provenance.sourceCommit = "0".repeat(40);
  await writeFile(receiptPath, `${JSON.stringify(receipt)}\n`);
  await assert.rejects(
    assertCompatibleTokenProvision({
      contract: fixtureContract,
      ledger: fixtureLedger,
      outputRoot,
    }),
    /prepared token provenance differs/,
  );
});

test("UI peer resolution rejects missing and incompatible reviewed baselines", () => {
  assert.equal(
    resolveUiTokenDependency({ contract, ledger, selectedIds: ["ui"] }).kind,
    "compatibility",
  );
  assert.equal(
    resolveUiTokenDependency({
      contract,
      ledger,
      selectedIds: ["designTokens", "ui"],
    }).kind,
    "selected",
  );
  const noBaseline = structuredClone(ledger);
  noBaseline.baselines = [];
  assert.throws(() =>
    resolveUiTokenDependency({
      contract,
      ledger: noBaseline,
      selectedIds: ["ui"],
    }),
  );
  const incompatible = structuredClone(contract);
  incompatible.packages.ui.expectedManifest.peerDependencies[
    incompatible.packages.designTokens.name
  ] = "^9.0.0";
  assert.throws(
    () =>
      resolveUiTokenDependency({
        contract: incompatible,
        ledger,
        selectedIds: ["ui"],
      }),
    /do not satisfy UI peer/,
  );
});
