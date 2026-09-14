import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { publishBootstrapRelease } from "../scripts/bootstrap-publish.mjs";
import { archiveTransferArtifactName } from "../scripts/fixture-transfer.mjs";
import {
  loadReleaseContract,
  packageRoles,
  workspaceRoot,
} from "../scripts/release-contract.mjs";
import { createCandidateEvidence } from "../scripts/release-evidence.mjs";

const sourceCommit = "b".repeat(40);
const producerToolchain = { node: "24.21.0", npm: "11.19.0" };
const applicationToolchain = {
  source: "apps/frontend/package-lock.json",
  isolation: "application-owned",
  node: "22.13.0",
  npm: "10.9.2",
};
const gates = {
  archives: { validated: true, reusedPackedBytes: true },
  consumers: { designTokens: {}, ui: {}, iframeSdk: {} },
  browser: {
    dependencyInstallations: 0,
    browserProvisioning: 0,
    externalRequests: 0,
  },
  host: { test: "bootstrap-fixture-host" },
};

async function fixture(context) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-bootstrap-publish-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const contract = await loadReleaseContract(
    path.join(workspaceRoot, "release/development-fixture-contract.json"),
  );
  contract.state = "maintainer-confirmed";
  contract.maintainerApproval = {
    scopeOwner: "fred-oss",
    owners: {
      packageApi: "test-package-api-owner",
      sdkProtocol: "test-sdk-protocol-owner",
      release: "test-release-owner",
      npmPublishing: "test-npm-publishing-owner",
    },
    bootstrapIdentity: "marc.fawaz",
    bootstrapAuthorityVerified: true,
    registryAccess: "public",
    publishingPolicy: "direct",
  };
  contract.expectedProvenance = {
    repository: "https://github.com/ThalesGroup/fred",
    workflow:
      "https://github.com/ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift",
    certificateIssuer: "https://token.actions.githubusercontent.com",
  };
  const archives = [];
  for (const role of packageRoles) {
    const archivePath = path.join(root, `${role}.tgz`);
    await writeFile(archivePath, `${role} approved bytes`);
    archives.push({ role, path: archivePath });
  }
  const evidence = await createCandidateEvidence({
    contract,
    archives,
    sourceCommit,
    producerToolchain,
    applicationToolchain,
    gates,
    approved: true,
  });
  const execution = {
    provider: "github-actions",
    repository: "ThalesGroup/fred",
    workflow: "Publish frontend packages",
    runId: "12345",
    runAttempt: "1",
  };
  evidence.transfer = {
    kind: "release-candidate-archive-transfer",
    artifactName: archiveTransferArtifactName({
      contractState: contract.state,
      sourceCommit,
      ...execution,
    }),
    metadataFilename: "candidate-transfer.json",
    metadataDigest: `sha256-${Buffer.alloc(32, 1).toString("base64")}`,
    sourceTreeClean: true,
    execution,
  };
  const github = {
    actions: "true",
    repository: "ThalesGroup/fred",
    ref: "refs/heads/swift",
    sha: sourceCommit,
    workflowRef:
      "ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift",
    workflow: execution.workflow,
    runId: execution.runId,
    runAttempt: execution.runAttempt,
  };
  return { root, contract, evidence, github };
}

test("bootstrap publication uses validated bytes in dependency order", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  const published = [];
  const registry = new Map();
  const result = await publishBootstrapRelease({
    contract,
    evidence,
    archiveRoot: root,
    github,
    identifyPublisher: async () => "marc.fawaz",
    inspectRegistry: async ({ coordinate }) => registry.get(coordinate) ?? null,
    publishArchive: async ({ role, candidate }) => {
      published.push(role);
      registry.set(candidate.coordinate, {
        dist: { integrity: candidate.integrity },
      });
    },
  });
  assert.deepEqual(published, ["designTokens", "ui", "iframeSdk"]);
  assert.deepEqual(
    result.published,
    published.map((role) => evidence.packages[role].coordinate),
  );
});

test("an existing or partial version stops before any publication", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  let publishes = 0;
  await assert.rejects(
    publishBootstrapRelease({
      contract,
      evidence,
      archiveRoot: root,
      github,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        coordinate === evidence.packages.designTokens.coordinate
          ? { version: "existing" }
          : null,
      publishArchive: async () => {
        publishes += 1;
      },
    }),
    /partial release/,
  );
  assert.equal(publishes, 0);
});

test("workflow, commit, and bootstrap identity mismatches fail closed", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  for (const input of [
    {
      github: { ...github, ref: "refs/heads/feature" },
      identity: "marc.fawaz",
    },
    {
      github: { ...github, sha: "c".repeat(40) },
      identity: "marc.fawaz",
    },
    {
      github: {
        ...github,
        workflowRef:
          "ThalesGroup/fred/.github/workflows/Other.yml@refs/heads/swift",
      },
      identity: "marc.fawaz",
    },
    {
      github: { ...github, runAttempt: "2" },
      identity: "marc.fawaz",
    },
    { github, identity: "another-account" },
  ])
    await assert.rejects(
      publishBootstrapRelease({
        contract,
        evidence,
        archiveRoot: root,
        github: input.github,
        identifyPublisher: async () => input.identity,
        inspectRegistry: async () => null,
        publishArchive: async () => assert.fail("must not publish"),
      }),
    );
});

test("a failure after publication reports the exact partial sequence", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  const registry = new Map();
  await assert.rejects(
    publishBootstrapRelease({
      contract,
      evidence,
      archiveRoot: root,
      github,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        registry.get(coordinate) ?? null,
      publishArchive: async ({ role, candidate }) => {
        if (role === "ui") throw new Error("controlled publish failure");
        registry.set(candidate.coordinate, {
          dist: { integrity: candidate.integrity },
        });
      },
    }),
    /outcome is indeterminate.*previously confirmed from this evidence: @fred-oss\/design-tokens@0\.1\.0-alpha\.1/,
  );
});

test("a post-publish registry failure still reports the package as published", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  let published = false;
  await assert.rejects(
    publishBootstrapRelease({
      contract,
      evidence,
      archiveRoot: root,
      github,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async () => null,
      publishArchive: async () => {
        published = true;
      },
    }),
    /publication completed.*registry verification failed.*confirmed publish commands from this evidence: @fred-oss\/design-tokens@0\.1\.0-alpha\.1/,
  );
  assert.equal(published, true);
});

test("an ambiguous publish failure reconciles registry state before reporting", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  const registry = new Map();
  await assert.rejects(
    publishBootstrapRelease({
      contract,
      evidence,
      archiveRoot: root,
      github,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        registry.get(coordinate) ?? null,
      publishArchive: async ({ candidate }) => {
        registry.set(candidate.coordinate, {
          dist: { integrity: candidate.integrity },
        });
        throw new Error("connection lost after registry accepted bytes");
      },
    }),
    /publish command failed.*registry reconciliation confirmed the expected archive bytes.*confirmed published from this evidence: @fred-oss\/design-tokens@0\.1\.0-alpha\.1/,
  );
});
