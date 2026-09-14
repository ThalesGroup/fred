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

function registryMetadata(contract, evidence, role) {
  return {
    name: contract.packages[role].name,
    version: contract.packages[role].version,
    dist: { integrity: evidence.packages[role].integrity },
  };
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
      registry.set(
        candidate.coordinate,
        registryMetadata(contract, evidence, role),
      );
    },
  });
  assert.deepEqual(published, ["designTokens", "ui", "iframeSdk"]);
  assert.deepEqual(
    result.published,
    published.map((role) => evidence.packages[role].coordinate),
  );
});

test("post-publication visibility retries an exact 404 without republishing", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  const registry = new Map();
  const inspections = new Map();
  const publishes = [];
  const result = await publishBootstrapRelease({
    contract,
    evidence,
    archiveRoot: root,
    github,
    identifyPublisher: async () => "marc.fawaz",
    inspectRegistry: async ({ coordinate }) => {
      const count = (inspections.get(coordinate) ?? 0) + 1;
      inspections.set(coordinate, count);
      if (!registry.has(coordinate) || count === 2) return null;
      return registry.get(coordinate);
    },
    publishArchive: async ({ role, candidate }) => {
      publishes.push(role);
      registry.set(candidate.coordinate, {
        name: contract.packages[role].name,
        version: contract.packages[role].version,
        dist: { integrity: candidate.integrity },
      });
    },
    visibilityAttempts: 3,
    waitForVisibility: async () => {},
  });
  assert.deepEqual(publishes, ["designTokens", "ui", "iframeSdk"]);
  assert.deepEqual(result.published, [
    evidence.packages.designTokens.coordinate,
    evidence.packages.ui.coordinate,
    evidence.packages.iframeSdk.coordinate,
  ]);
});

test("exhausted visibility retries stop before the next package and never republish", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  const publishes = [];
  await assert.rejects(
    publishBootstrapRelease({
      contract,
      evidence,
      archiveRoot: root,
      github,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async () => null,
      publishArchive: async ({ role }) => publishes.push(role),
      visibilityAttempts: 3,
      waitForVisibility: async () => {},
    }),
    /visibility retries exhausted.*stop before continuing/,
  );
  assert.deepEqual(publishes, ["designTokens"]);
});

test("malformed or mismatched post-publication metadata fails without retrying or progressing", async (context) => {
  const variants = [
    null,
    {},
    { name: "@fred-oss/wrong", version: "0.1.0-alpha.1" },
    { name: "@fred-oss/design-tokens", version: "9.9.9" },
    {
      name: "@fred-oss/design-tokens",
      version: "0.1.0-alpha.1",
      dist: { integrity: "sha512-wrong" },
    },
  ];
  for (const [index, metadata] of variants.entries()) {
    const { root, contract, evidence, github } = await fixture(context);
    let inspections = 0;
    const publishes = [];
    await assert.rejects(
      publishBootstrapRelease({
        contract,
        evidence,
        archiveRoot: root,
        github,
        identifyPublisher: async () => "marc.fawaz",
        inspectRegistry: async () => {
          inspections += 1;
          return inspections <= 3 ? null : metadata;
        },
        publishArchive: async ({ role }) => publishes.push(role),
        visibilityAttempts: metadata === null ? 2 : 3,
        waitForVisibility: async () => {},
      }),
      metadata === null
        ? /visibility retries exhausted/
        : /metadata name differs|metadata version differs|registry integrity differs/,
      `variant ${index}`,
    );
    assert.deepEqual(publishes, ["designTokens"]);
  }
});

test("an authentication failure is not retried and stops before the next package", async (context) => {
  const { root, contract, evidence, github } = await fixture(context);
  let inspections = 0;
  const publishes = [];
  await assert.rejects(
    publishBootstrapRelease({
      contract,
      evidence,
      archiveRoot: root,
      github,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async () => {
        inspections += 1;
        if (inspections <= 3) return null;
        throw new Error("E401 registry authentication failed");
      },
      publishArchive: async ({ role }) => publishes.push(role),
      visibilityAttempts: 3,
      waitForVisibility: async () => assert.fail("must not retry E401"),
    }),
    /registry verification failed.*E401 registry authentication failed/,
  );
  assert.equal(inspections, 4);
  assert.deepEqual(publishes, ["designTokens"]);
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
          ? registryMetadata(contract, evidence, "designTokens")
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
        registry.set(
          candidate.coordinate,
          registryMetadata(contract, evidence, role),
        );
      },
      visibilityAttempts: 1,
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
      visibilityAttempts: 1,
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
      publishArchive: async ({ role, candidate }) => {
        registry.set(
          candidate.coordinate,
          registryMetadata(contract, evidence, role),
        );
        throw new Error("connection lost after registry accepted bytes");
      },
    }),
    /publish command failed.*registry reconciliation confirmed the expected archive bytes.*confirmed published from this evidence: @fred-oss\/design-tokens@0\.1\.0-alpha\.1/,
  );
});
