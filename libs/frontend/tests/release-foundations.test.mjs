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
import { createHash } from "node:crypto";
import {
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
import semver from "semver";

import { assertChangelogVersion } from "../scripts/release-changelog.mjs";
import { buildReleaseCandidate } from "../scripts/release-candidate.mjs";
import {
  checkTransferChangelogs,
  createReleaseCandidateTransfer,
  fixtureExecution,
} from "../scripts/fixture-transfer.mjs";
import { run } from "../scripts/process.mjs";
import {
  assertInventoryWorkspaces,
  validatePackageInventory,
} from "../scripts/release-inventory.mjs";
import {
  loadReleaseContract,
  workspaceRoot,
} from "../scripts/release-contract.mjs";
import {
  baselineDigest,
  loadCompatibilityLedger,
  validateCompatibilityLedger,
  verifyBaselineAgainstRegistry,
  verifyBaselineImport,
} from "../scripts/compatibility-baselines.mjs";
import {
  assertRecordAuthorizesPublication,
  assertRecordAuthorizesRegistrySuccess,
  candidateRecordFromEvidence,
  publicationOutcomeModel,
  publishingAttemptModel,
  releaseRecordDigest,
  validateReleaseRecord,
  verificationModel,
} from "../scripts/release-record.mjs";

const inventory = JSON.parse(
  await readFile(
    path.join(workspaceRoot, "release/package-inventory.json"),
    "utf8",
  ),
);
const rootManifest = JSON.parse(
  await readFile(path.join(workspaceRoot, "package.json"), "utf8"),
);
const selectedPolicy = path.join(
  workspaceRoot,
  "release/proposed-release-contract.json",
);
const sourceCommit = "f".repeat(40);

async function disposableProducer(context) {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "fred-release-foundations-"),
  );
  context.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, "release"));
  await writeFile(
    path.join(root, "package.json"),
    JSON.stringify(rootManifest),
  );
  await writeFile(
    path.join(root, "release/package-inventory.json"),
    JSON.stringify(inventory),
  );
  for (const { workspace } of inventory.members) {
    await mkdir(path.join(root, workspace));
    await writeFile(
      path.join(root, workspace, "package.json"),
      await readFile(path.join(workspaceRoot, workspace, "package.json")),
    );
    await writeFile(
      path.join(root, workspace, "CHANGELOG.md"),
      await readFile(path.join(workspaceRoot, workspace, "CHANGELOG.md")),
    );
  }
  return root;
}

test("inventory rejects unknown fields, duplicate IDs/workspaces, root, and escaping paths", async (context) => {
  assert.doesNotThrow(() => validatePackageInventory(inventory));
  for (const mutate of [
    (changed) => changed.members.push({ ...changed.members[0] }),
    (changed) => (changed.members[1].workspace = changed.members[0].workspace),
    (changed) => (changed.members[1].workspace = "../outside"),
    (changed) => (changed.members[1].workspace = "."),
    (changed) => (changed.members[1].builder = "unknown-builder"),
    (changed) => (changed.members[1].validator = "unknown-validator"),
    (changed) => (changed.members[1].consumer = "unknown-consumer"),
    (changed) => (changed.members[1].consumer = "tokens"),
    (changed) => (changed.members[1].builder = "pack-design-tokens"),
    (changed) => (changed.members[1].id = "root"),
    (changed) => (changed.members[0].unknown = true),
  ]) {
    const changed = structuredClone(inventory);
    mutate(changed);
    if (
      changed.members[1].id === "root" &&
      changed.members[1].workspace === "ui"
    ) {
      // A syntactically valid ID cannot register a member missing from the producer root.
      await assert.rejects(
        assertInventoryWorkspaces(
          changed,
          {
            ...rootManifest,
            workspaces: ["design-tokens", "root", "iframe-sdk"],
          },
          workspaceRoot,
        ),
      );
    } else assert.throws(() => validatePackageInventory(changed));
  }
  const root = await disposableProducer(context);
  const outside = await mkdtemp(
    path.join(os.tmpdir(), "fred-release-outside-"),
  );
  context.after(() => rm(outside, { recursive: true, force: true }));
  await rm(path.join(root, "ui"), { recursive: true });
  await symlink(outside, path.join(root, "ui"));
  await assert.rejects(
    assertInventoryWorkspaces(inventory, rootManifest, root),
    /escapes/,
  );
});

test("authoritative manifests permit a future SDK-only fixture coordinate without UI/token drift", async (context) => {
  const root = await disposableProducer(context);
  const sdkPath = path.join(root, "iframe-sdk/package.json");
  const sdk = JSON.parse(await readFile(sdkPath, "utf8"));
  const fixtureVersion = semver.inc(sdk.version, "prerelease", "alpha");
  assert(fixtureVersion && fixtureVersion !== sdk.version);
  sdk.version = fixtureVersion;
  await writeFile(sdkPath, JSON.stringify(sdk));
  const contract = await loadReleaseContract(selectedPolicy, { root });
  assert.equal(contract.packages.iframeSdk.version, fixtureVersion);
  assert.equal(
    contract.packages.ui.version,
    JSON.parse(await readFile(path.join(root, "ui/package.json"), "utf8"))
      .version,
  );
  assert.equal(contract.packages.designTokens.version, "0.1.0-alpha.1");
  await assert.rejects(
    buildReleaseCandidate({
      contract,
      root,
      approved: true,
      sourceCommit,
      clean: true,
      producerToolchain: contract.releaseToolchain,
      applicationToolchain: {
        ...contract.applicationToolchain,
        source: "apps/frontend/package-lock.json",
        isolation: "application-owned",
      },
    }),
    /disposable producer root/,
  );
  const calls = [];
  await assert.rejects(
    buildReleaseCandidate({
      contract,
      root,
      sourceCommit,
      clean: true,
      producerToolchain: contract.releaseToolchain,
      applicationToolchain: {
        ...contract.applicationToolchain,
        source: "apps/frontend/package-lock.json",
        isolation: "application-owned",
      },
      packers: {
        designTokens: async () => calls.push("tokens"),
        ui: async () => calls.push("ui"),
        iframeSdk: async () => calls.push("sdk"),
      },
    }),
    /changelog/,
  );
  assert.deepEqual(calls, []);
  await writeFile(
    path.join(root, "iframe-sdk/CHANGELOG.md"),
    `## ${fixtureVersion}\n\nReview: approved\nChanges: Fixture-only SDK version.\n`,
  );
  assert.doesNotThrow(() =>
    assertChangelogVersion(
      `## ${fixtureVersion}\n\nReview: approved\nChanges: Fixture-only SDK version.\n`,
      fixtureVersion,
    ),
  );
  sdk.exports["./protocol"].import = "../missing.js";
  await writeFile(sdkPath, JSON.stringify(sdk));
  await assert.rejects(
    loadReleaseContract(selectedPolicy, { root }),
    /export target escapes/,
  );
});

test("selected policy rejects conflicting manifest metadata and copied coordinates", async (context) => {
  const root = await disposableProducer(context);
  const uiPath = path.join(root, "ui/package.json");
  const ui = JSON.parse(await readFile(uiPath, "utf8"));
  ui.publishConfig.tag = "latest";
  await writeFile(uiPath, JSON.stringify(ui));
  await assert.rejects(
    loadReleaseContract(selectedPolicy, { root }),
    /publishConfig differs/,
  );
  ui.publishConfig.tag = "next";
  ui.name = "@another/ui";
  await writeFile(uiPath, JSON.stringify(ui));
  await assert.rejects(
    loadReleaseContract(selectedPolicy, { root }),
    /verified npm scope/,
  );
  ui.name = "@fred-oss/ui";
  ui.private = true;
  await writeFile(uiPath, JSON.stringify(ui));
  await assert.rejects(
    loadReleaseContract(selectedPolicy, { root }),
    /registered release member must not be private/,
  );
});

test("version review requires one exact reviewed, nonempty changelog entry", () => {
  const valid =
    "# SDK\n\n## 0.1.0-alpha.2\n\nReview: approved\nChanges: Protocol compatibility fixes.\n";
  assert.deepEqual(assertChangelogVersion(valid, "0.1.0-alpha.2"), {
    version: "0.1.0-alpha.2",
    reviewed: true,
  });
  for (const bad of [
    valid.replace("alpha.2", "alpha.3"),
    valid.replace("Review: approved", "Review: pending"),
    valid.replace("Changes: Protocol compatibility fixes.", ""),
    valid + "\n## 0.1.0-alpha.2\nReview: approved\nChanges: duplicate\n",
  ])
    assert.throws(() => assertChangelogVersion(bad, "0.1.0-alpha.2"));
});

test("approved preparation rejects an unreviewed changelog from a disposable producer", async (context) => {
  const root = await disposableProducer(context);
  await writeFile(
    path.join(root, "ui/CHANGELOG.md"),
    "## 0.1.0-alpha.1\n\nReview: pending\nChanges: Fixture-only review failure.\n",
  );
  const contract = await loadReleaseContract(selectedPolicy, { root });
  await assert.rejects(checkTransferChangelogs(contract, root), /changelog/);
  const execution = fixtureExecution({
    provider: "local-rehearsal",
    repository: "ThalesGroup/fred",
    workflow: "preparation-test",
    runId: "test-1",
    runAttempt: "1",
  });
  await assert.rejects(
    createReleaseCandidateTransfer({
      outputRoot: path.join(root, "transfer"),
      contract,
      sourceCommit,
      sourceTreeClean: true,
      producerToolchain: contract.releaseToolchain,
      execution,
      producerRoot: root,
    }),
    /disposable producer root/,
  );
  const canonicalContract = await loadReleaseContract(selectedPolicy);
  await assert.rejects(
    createReleaseCandidateTransfer({
      outputRoot: path.join(root, "transfer"),
      contract: canonicalContract,
      sourceCommit,
      sourceTreeClean: true,
      producerToolchain: canonicalContract.releaseToolchain,
      execution,
      packers: {
        ui: async () => {
          throw new Error("fixture packer");
        },
      },
    }),
    /approved transfer packers/,
  );
  const alteredPolicy = structuredClone(canonicalContract);
  alteredPolicy.maintainerApproval.owners.release = "different-reviewed-owner";
  await assert.rejects(
    createReleaseCandidateTransfer({
      outputRoot: path.join(root, "transfer"),
      contract: alteredPolicy,
      sourceCommit,
      sourceTreeClean: true,
      producerToolchain: alteredPolicy.releaseToolchain,
      execution,
    }),
    /canonical reviewed policy and manifests/,
  );
});

function syntheticAttestation(expected, mutate = () => {}) {
  const statement = {
    _type: "https://in-toto.io/Statement/v1",
    predicateType: "https://slsa.dev/provenance/v1",
    subject: [{ digest: { sha512: expected.integrity.slice(7) } }],
    predicate: {
      buildDefinition: {
        externalParameters: {
          workflow: {
            repository: expected.repository,
            path: ".github/workflows/Publish-frontend-packages.yml",
            ref: "refs/heads/swift",
          },
        },
        resolvedDependencies: [
          {
            uri: expected.repository,
            digest: { gitCommit: expected.sourceCommit },
          },
        ],
      },
    },
  };
  mutate(statement);
  return {
    attestations: [
      {
        predicateType: "https://slsa.dev/provenance/v1",
        bundle: {
          dsseEnvelope: {
            payloadType: "application/vnd.in-toto+json",
            payload: Buffer.from(JSON.stringify(statement)).toString("base64"),
          },
        },
      },
    ],
  };
}

test("fixture import checks historical artifact, exact bytes, and independent attested identity", async (context) => {
  const ledger = await loadCompatibilityLedger();
  const baseline = structuredClone(ledger.baselines[0]);
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-baseline-fixture-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const tarballPath = path.join(root, "fixture.tgz");
  await writeFile(tarballPath, "disposable baseline bytes");
  const integrity = `sha512-${createHash("sha512").update("disposable baseline bytes").digest("base64")}`;
  baseline.expected.integrity = integrity;
  baseline.expected.artifactDigest = integrity;
  const historicalEvidence = {
    packages: {
      designTokens: {
        coordinate: baseline.coordinate,
        integrity,
        provenance: {
          artifactDigest: integrity,
          repository: baseline.expected.repository,
          sourceCommit: baseline.expected.sourceCommit,
          workflow: baseline.expected.workflow,
        },
      },
    },
    gates: Object.fromEntries(
      baseline.verificationTrace.historicalGates.map((gate) => [gate, true]),
    ),
    verificationExecution: {
      runId: baseline.verificationTrace.runId,
      runAttempt: baseline.verificationTrace.runAttempt,
      sourceCommit: baseline.verificationTrace.sourceCommit,
    },
  };
  const evidencePath = path.join(root, "final-evidence.json");
  const evidenceText = JSON.stringify(historicalEvidence);
  await writeFile(evidencePath, evidenceText);
  const zipPath = path.join(root, "verification.zip");
  await run("zip", ["-j", zipPath, evidencePath]);
  const zipSha256 = createHash("sha256")
    .update(await readFile(zipPath))
    .digest("hex");
  baseline.verificationTrace.artifactZipSha256 = zipSha256;
  baseline.verificationTrace.artifactApiDigest = `sha256:${zipSha256}`;
  baseline.verificationTrace.historicalEvidenceSha256 = createHash("sha256")
    .update(evidenceText)
    .digest("hex");
  const historicalArtifact = {
    id: baseline.verificationTrace.artifactId,
    name: baseline.verificationTrace.artifactName,
    digest: baseline.verificationTrace.artifactApiDigest,
    zipPath,
  };
  const metadata = {
    name: "@fred-oss/design-tokens",
    version: "0.1.0-alpha.1",
    dist: { integrity },
  };
  const args = {
    baseline,
    historicalEvidence,
    historicalArtifact,
    metadata,
    tarballPath,
    attestation: syntheticAttestation(baseline.expected),
    verifyBundle: async () => {},
  }; // Controlled structure test, not real Sigstore proof.
  assert.equal((await verifyBaselineImport(args)).integrity, integrity);
  await writeFile(path.join(root, "bad.zip"), "not the approved ZIP");
  await assert.rejects(
    verifyBaselineImport({
      ...args,
      historicalArtifact: {
        ...historicalArtifact,
        zipPath: path.join(root, "bad.zip"),
      },
    }),
    /ZIP digest/,
  );
  await assert.rejects(
    verifyBaselineImport({
      ...args,
      metadata: {
        ...metadata,
        dist: { integrity: `sha512-${"A".repeat(86)}==` },
      },
    }),
    /integrity/,
  );
  await assert.rejects(
    verifyBaselineImport({
      ...args,
      attestation: syntheticAttestation(
        baseline.expected,
        (statement) =>
          (statement.predicate.buildDefinition.resolvedDependencies[0].digest.gitCommit =
            "0".repeat(40)),
      ),
    }),
    /sourceCommit/,
  );
  await assert.rejects(
    verifyBaselineImport({
      ...args,
      verifyBundle: async () => {
        throw new Error("invalid signature");
      },
    }),
    /invalid signature/,
  );
  await rm(zipPath);
  assert.equal(
    (
      await verifyBaselineAgainstRegistry({
        baseline,
        metadata,
        tarballPath,
        attestation: args.attestation,
        verifyBundle: args.verifyBundle,
      })
    ).integrity,
    integrity,
  ); // Controlled verifier still checks exact bytes/identity after the ZIP disappears.
});

test("committed baseline remains locally usable without its expiring CI ZIP", async () => {
  const ledger = await loadCompatibilityLedger();
  assert.equal(baselineDigest(ledger).length, 64);
  const mutated = structuredClone(ledger);
  mutated.baselines[0].verificationTrace.oneTimeSigstoreVerified = false;
  assert.throws(() => validateCompatibilityLedger(mutated), /Sigstore/);
  mutated.baselines[0].verificationTrace.oneTimeSigstoreVerified = true;
  mutated.baselines[0].expected.sourceCommit = "0".repeat(40);
  assert.notEqual(baselineDigest(mutated), baselineDigest(ledger));
  mutated.baselines[0].coordinate = "@fred-oss/other@0.1.0-alpha.1";
  assert.throws(
    () => validateCompatibilityLedger(mutated),
    /package name differs/,
  );
  // Neither load nor digest traverses the historical artifact ID/ZIP path.
});

test("records support SDK-only fixture selection but never authorize publish or registry success", async () => {
  const contract = await loadReleaseContract();
  const ledger = await loadCompatibilityLedger();
  const sdk = contract.packages.iframeSdk;
  const integrity = `sha512-${"A".repeat(86)}==`;
  const evidence = {
    kind: "fixture-candidate-evidence",
    sourceCommit,
    producerToolchain: contract.releaseToolchain,
    applicationToolchain: {
      ...contract.applicationToolchain,
      source: "apps/frontend/package-lock.json",
      isolation: "application-owned",
    },
    gates: { archives: { validated: true } },
    packages: {
      iframeSdk: {
        coordinate: `${sdk.name}@${sdk.version}`,
        filename: "iframe-sdk-fixture.tgz",
        bytes: 12,
        integrity,
      },
    },
  };
  const candidate = await candidateRecordFromEvidence({
    evidence,
    contract,
    ledger,
    selectedIds: ["iframeSdk"],
  });
  assert.deepEqual(
    candidate.selected.map(({ id }) => id),
    ["iframeSdk"],
  );
  assert.deepEqual(candidate.compatibilityOnly, []);
  assert.equal(candidate.readiness, "fixture");
  await assert.rejects(
    candidateRecordFromEvidence({
      evidence,
      contract,
      ledger,
      selectedIds: ["designTokens"],
    }),
    /selection differs from packed evidence/,
  );
  const forgedUiEvidence = structuredClone(evidence);
  forgedUiEvidence.packages = {
    ui: {
      ...evidence.packages.iframeSdk,
      coordinate: `${contract.packages.ui.name}@${contract.packages.ui.version}`,
      filename: "ui-fixture.tgz",
    },
  };
  forgedUiEvidence.selectedIds = ["ui"];
  await assert.rejects(
    candidateRecordFromEvidence({
      evidence: forgedUiEvidence,
      contract,
      ledger,
      selectedIds: ["ui"],
    }),
    /compatibility selection differs/,
  );
  const uiOnly = await candidateRecordFromEvidence({
    evidence: forgedUiEvidence,
    contract,
    ledger,
    selectedIds: ["ui"],
    compatibilityOnly: ["designTokens"],
  });
  assert.deepEqual(
    uiOnly.compatibilityOnly.map(({ id }) => id),
    ["designTokens"],
  );
  await assert.rejects(
    candidateRecordFromEvidence({
      evidence: forgedUiEvidence,
      contract,
      ledger,
      selectedIds: ["iframeSdk"],
      compatibilityOnly: ["designTokens"],
    }),
    /selection differs/,
  );
  const selectedContract = await loadReleaseContract(selectedPolicy);
  const forgedSdkEvidence = structuredClone(evidence);
  forgedSdkEvidence.kind = "release-candidate-evidence";
  const unverified = await candidateRecordFromEvidence({
    evidence: forgedSdkEvidence,
    contract: selectedContract,
    ledger,
    selectedIds: ["iframeSdk"],
  });
  assert.equal(unverified.readiness, "incomplete");
  const execution = {
    repository: "ThalesGroup/fred",
    workflow: "Publish-frontend-packages.yml",
    sourceCommit,
    runId: "1",
    runAttempt: "1",
    signerIssuer: "https://token.actions.githubusercontent.com",
  };
  const attempt = publishingAttemptModel({ candidate, execution });
  assert.throws(
    () => assertRecordAuthorizesPublication(attempt),
    /unpersisted/,
  );
  const outcome = publicationOutcomeModel({
    attempt,
    memberId: "iframeSdk",
    coordinate: candidate.selected[0].coordinate,
    integrity,
    provenance: { cryptographicallyVerified: false },
  });
  const verification = verificationModel({
    candidate,
    execution,
    outcomes: [outcome],
    gates: {},
  });
  assert.throws(
    () => assertRecordAuthorizesRegistrySuccess(verification),
    /controlled/,
  );
  assert(/^sha256-/.test(releaseRecordDigest(candidate)));
  for (const mutate of [
    (record) => (record.archives.iframeSdk.bytes = 0),
    (record) => record.selected.push({ ...record.selected[0] }),
    (record) => (record.policyDigest = null),
    (record) => (record.archives.iframeSdk.integrity = "bad"),
    (record) => (record.compatibilityOnly = [{ id: "designTokens" }]),
    (record) => (record.selected[0].consumer = null),
    (record) =>
      (record.transferOrigin = {
        artifactName: "candidate-fixture",
        metadataDigest: "sha256-invalid",
        execution: {},
      }),
    (record) =>
      (record.manifestRanges.iframeSdk.peerDependencies.local = "workspace:*"),
  ]) {
    const changed = structuredClone(candidate);
    mutate(changed);
    assert.throws(() => validateReleaseRecord(changed));
  }
  const inventedLedger = structuredClone(ledger);
  inventedLedger.baselines[0].expected.sourceCommit = "0".repeat(40);
  await assert.rejects(
    candidateRecordFromEvidence({
      evidence,
      contract,
      ledger: inventedLedger,
      selectedIds: ["iframeSdk"],
    }),
    /approved policy digest/,
  );
});
