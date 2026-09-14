import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  cp,
  mkdtemp,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertOriginalArtifactMetadata,
  prepareBootstrapRecovery,
  publishBootstrapRecovery,
  validateBootstrapRecoveryEvidence,
  validateBootstrapRecoveryPlan,
} from "../scripts/bootstrap-recovery.mjs";
import {
  archiveTransferArtifactName,
  fixtureArchiveFilename,
} from "../scripts/fixture-transfer.mjs";
import {
  loadReleaseContract,
  packageRoles,
  workspaceRoot,
} from "../scripts/release-contract.mjs";
import {
  createCandidateEvidence,
  releaseContractDigest,
  sha512Integrity,
} from "../scripts/release-evidence.mjs";
import { run } from "../scripts/process.mjs";

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
  host: { test: "recovery-fixture-host" },
};

function metadata(contract, evidence, role) {
  return {
    name: contract.packages[role].name,
    version: contract.packages[role].version,
    dist: { integrity: evidence.packages[role].integrity },
  };
}

async function fixture(context) {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "fred-bootstrap-recovery-"),
  );
  context.after(() => rm(root, { recursive: true, force: true }));
  const [contract, plan] = await Promise.all([
    loadReleaseContract(
      path.join(workspaceRoot, "release/development-fixture-contract.json"),
    ),
    readFile(
      path.join(workspaceRoot, "release/bootstrap-recovery.json"),
      "utf8",
    ).then(JSON.parse),
  ]);
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
    workflow: plan.recoveryExecution.workflow,
    certificateIssuer: "https://token.actions.githubusercontent.com",
  };
  const archives = [];
  for (const role of packageRoles) {
    const selected = contract.packages[role];
    const archivePath = path.join(
      root,
      fixtureArchiveFilename(selected.name, selected.version),
    );
    await writeFile(archivePath, `${role} original approved bytes`);
    archives.push({ role, path: archivePath });
  }
  const evidence = await createCandidateEvidence({
    contract,
    archives,
    sourceCommit: plan.incident.sourceCommit,
    producerToolchain,
    applicationToolchain,
    gates,
    approved: true,
  });
  const execution = {
    provider: "github-actions",
    repository: "ThalesGroup/fred",
    workflow: "Publish frontend packages",
    runId: plan.incident.workflowRunId,
    runAttempt: plan.incident.workflowRunAttempt,
  };
  const artifactName = archiveTransferArtifactName({
    contractState: contract.state,
    sourceCommit: plan.incident.sourceCommit,
    ...execution,
  });
  const transfer = {
    schemaVersion: 1,
    kind: "release-candidate-archive-transfer",
    artifactName,
    createdAt: "2026-09-14T14:09:00.000Z",
    sourceCommit: plan.incident.sourceCommit,
    sourceTreeClean: true,
    contract: {
      state: contract.state,
      digest: releaseContractDigest(contract),
    },
    producerToolchain,
    execution,
    producerValidation: {
      archives: true,
      consumers: false,
      browser: false,
      host: false,
    },
    packages: Object.fromEntries(
      packageRoles.map((role) => {
        const selected = contract.packages[role];
        const candidate = evidence.packages[role];
        return [
          role,
          {
            role,
            name: selected.name,
            version: selected.version,
            coordinate: candidate.coordinate,
            filename: candidate.filename,
            bytes: candidate.bytes,
            integrity: candidate.integrity,
          },
        ];
      }),
    ),
  };
  const transferPath = path.join(root, "candidate-transfer.json");
  await writeFile(transferPath, `${JSON.stringify(transfer, null, 2)}\n`);
  evidence.transfer = {
    kind: transfer.kind,
    artifactName,
    metadataFilename: "candidate-transfer.json",
    metadataDigest: `sha256-${createHash("sha256")
      .update(await readFile(transferPath))
      .digest("base64")}`,
    sourceTreeClean: true,
    execution,
  };
  await writeFile(
    path.join(root, "candidate-evidence.json"),
    `${JSON.stringify(evidence, null, 2)}\n`,
  );
  const artifactZipPath = path.join(
    path.dirname(root),
    "original-artifact.zip",
  );
  await run(
    "zip",
    [
      "-q",
      artifactZipPath,
      "candidate-evidence.json",
      "candidate-transfer.json",
      ...packageRoles.map((role) => evidence.packages[role].filename),
    ],
    { cwd: root },
  );
  plan.incident.artifactZipSha256 = createHash("sha256")
    .update(await readFile(artifactZipPath))
    .digest("hex");
  const github = {
    actions: "true",
    repository: "ThalesGroup/fred",
    ref: "refs/heads/swift",
    sha: "c".repeat(40),
    workflowRef:
      "ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift",
    workflow: "Publish frontend packages",
    runId: "40000000000",
    runAttempt: "2",
  };
  const artifactMetadata = {
    id: plan.incident.artifactId,
    name: plan.incident.artifactName,
    expired: false,
    digest: `sha256:${plan.incident.artifactZipSha256}`,
    workflow_run: {
      id: Number(plan.incident.workflowRunId),
      head_sha: plan.incident.sourceCommit,
      head_branch: "swift",
    },
  };
  artifactMetadata.digest = `sha256:${plan.incident.artifactZipSha256}`;
  return {
    root,
    contract,
    plan,
    evidence,
    github,
    artifactMetadata,
    artifactZipPath,
  };
}

async function replaceLooseUiCandidate(input) {
  const candidate = input.evidence.packages.ui;
  const archivePath = path.join(input.root, candidate.filename);
  await writeFile(archivePath, "replacement UI bytes");
  candidate.bytes = (await readFile(archivePath)).byteLength;
  candidate.integrity = await sha512Integrity(archivePath);
  candidate.expectedProvenance.artifactDigest = candidate.integrity;
  await writeFile(
    path.join(input.root, "candidate-evidence.json"),
    `${JSON.stringify(input.evidence, null, 2)}\n`,
  );
}

async function updateArtifactZipPin(input, artifactZipPath) {
  input.artifactZipPath = artifactZipPath;
  input.plan.incident.artifactZipSha256 = createHash("sha256")
    .update(await readFile(artifactZipPath))
    .digest("hex");
  input.artifactMetadata.digest = `sha256:${input.plan.incident.artifactZipSha256}`;
}

async function preparedFixture(context) {
  const input = await fixture(context);
  const registry = new Map([
    [
      input.evidence.packages.designTokens.coordinate,
      metadata(input.contract, input.evidence, "designTokens"),
    ],
  ]);
  const recoveryEvidence = await prepareBootstrapRecovery({
    ...input,
    archiveRoot: input.root,
    inspectRegistry: async ({ coordinate }) => registry.get(coordinate) ?? null,
    verifyExistingPackage: async () => true,
  });
  return { ...input, recoveryEvidence, registry };
}

test("reviewed recovery binds the original artifact and actual recovery identity", async (context) => {
  const input = await preparedFixture(context);
  validateBootstrapRecoveryPlan(input.plan);
  assertOriginalArtifactMetadata(input.plan, input.artifactMetadata);
  validateBootstrapRecoveryEvidence(input);
  assert.equal(
    input.recoveryEvidence.expectedProvenance.designTokens.sourceCommit,
    input.plan.incident.sourceCommit,
  );
  assert.equal(
    input.recoveryEvidence.expectedProvenance.ui.sourceCommit,
    input.github.sha,
  );
  assert.equal(
    input.recoveryEvidence.expectedProvenance.iframeSdk.sourceCommit,
    input.github.sha,
  );
});

test("recovery preparation verifies the existing package and requires the others absent", async (context) => {
  const input = await fixture(context);
  const verified = [];
  const registry = new Map([
    [
      input.evidence.packages.designTokens.coordinate,
      metadata(input.contract, input.evidence, "designTokens"),
    ],
  ]);
  await prepareBootstrapRecovery({
    ...input,
    archiveRoot: input.root,
    inspectRegistry: async ({ coordinate }) => registry.get(coordinate) ?? null,
    verifyExistingPackage: async ({ role, expected }) => {
      verified.push({ role, expected });
    },
  });
  assert.deepEqual(
    verified.map(({ role }) => role),
    ["designTokens"],
  );

  registry.set(
    input.evidence.packages.ui.coordinate,
    metadata(input.contract, input.evidence, "ui"),
  );
  await assert.rejects(
    prepareBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      inspectRegistry: async ({ coordinate }) =>
        registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => true,
    }),
    /unexpectedly exists; stop recovery/,
  );
});

test("recovery preparation materializes only files derived from the verified ZIP", async (context) => {
  const input = await fixture(context);
  const materializeRoot = path.join(input.root, "materialized");
  await prepareBootstrapRecovery({
    contract: input.contract,
    plan: input.plan,
    artifactZipPath: input.artifactZipPath,
    artifactMetadata: input.artifactMetadata,
    github: input.github,
    materializeRoot,
    inspectRegistry: async ({ coordinate }) =>
      coordinate === input.evidence.packages.designTokens.coordinate
        ? metadata(input.contract, input.evidence, "designTokens")
        : null,
    verifyExistingPackage: async () => true,
  });
  for (const filename of [
    "candidate-evidence.json",
    "candidate-transfer.json",
    ...packageRoles.map((role) => input.evidence.packages[role].filename),
  ])
    assert.deepEqual(
      await readFile(path.join(materializeRoot, filename)),
      await readFile(path.join(input.root, filename)),
    );
  assert.deepEqual(
    JSON.parse(
      await readFile(
        path.join(materializeRoot, "original-artifact-metadata.json"),
        "utf8",
      ),
    ),
    input.artifactMetadata,
  );
  assert.deepEqual(
    await readFile(path.join(materializeRoot, "original-release-artifact.zip")),
    await readFile(input.artifactZipPath),
  );
});

test("recovery publishes only the missing packages in dependency-safe order", async (context) => {
  const input = await preparedFixture(context);
  const published = [];
  const result = await publishBootstrapRecovery({
    ...input,
    archiveRoot: input.root,
    identifyPublisher: async () => "marc.fawaz",
    inspectRegistry: async ({ coordinate }) =>
      input.registry.get(coordinate) ?? null,
    verifyExistingPackage: async ({ role }) =>
      assert.equal(role, "designTokens"),
    publishArchive: async ({ role, candidate, archivePath }) => {
      published.push(role);
      assert.notEqual(path.dirname(archivePath), input.root);
      assert.equal(
        await readFile(archivePath, "utf8"),
        `${role} original approved bytes`,
      );
      input.registry.set(
        candidate.coordinate,
        metadata(input.contract, input.evidence, role),
      );
    },
    waitForVisibility: async () => {},
  });
  assert.deepEqual(published, ["ui", "iframeSdk"]);
  assert.deepEqual(result.published, [
    input.evidence.packages.ui.coordinate,
    input.evidence.packages.iframeSdk.coordinate,
  ]);
});

test("unresolved recovery verification stops before the next package without republishing", async (context) => {
  const input = await preparedFixture(context);
  const published = [];
  await assert.rejects(
    publishBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) => {
        if (coordinate === input.evidence.packages.designTokens.coordinate)
          return input.registry.get(coordinate);
        return null;
      },
      verifyExistingPackage: async () => true,
      publishArchive: async ({ role }) => published.push(role),
      visibilityAttempts: 2,
      waitForVisibility: async () => {},
    }),
    /visibility retries exhausted.*stop before continuing/,
  );
  assert.deepEqual(published, ["ui"]);
});

test("ambiguous recovery publication reconciles once and never advances", async (context) => {
  const input = await preparedFixture(context);
  const published = [];
  await assert.rejects(
    publishBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        input.registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => true,
      publishArchive: async ({ role, candidate }) => {
        published.push(role);
        input.registry.set(
          candidate.coordinate,
          metadata(input.contract, input.evidence, role),
        );
        throw new Error("connection lost after registry accepted bytes");
      },
      waitForVisibility: async () => {},
    }),
    /publish command failed.*reconciliation confirmed.*stop before continuing/,
  );
  assert.deepEqual(published, ["ui"]);
});

test("a missing recovery coordinate appearing after preparation stops all publication", async (context) => {
  const input = await preparedFixture(context);
  input.registry.set(
    input.evidence.packages.ui.coordinate,
    metadata(input.contract, input.evidence, "ui"),
  );
  await assert.rejects(
    publishBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        input.registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => true,
      publishArchive: async () => assert.fail("must not publish"),
    }),
    /unexpectedly exists; stop recovery without publishing/,
  );
});

test("recovery rejects artifact, execution, and existing-package drift before publication", async (context) => {
  const input = await preparedFixture(context);
  await assert.rejects(
    prepareBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      artifactMetadata: { ...input.artifactMetadata, digest: "sha256:wrong" },
      inspectRegistry: async ({ coordinate }) =>
        input.registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => true,
    }),
    /artifact ZIP digest differs/,
  );
  await assert.rejects(
    publishBootstrapRecovery({
      ...input,
      github: { ...input.github, sha: "d".repeat(40) },
      archiveRoot: input.root,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        input.registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => true,
      publishArchive: async () => assert.fail("must not publish"),
    }),
    /recovery provenance expectations differ/,
  );
  input.registry.set(input.evidence.packages.designTokens.coordinate, null);
  await assert.rejects(
    publishBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        input.registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => true,
      publishArchive: async () => assert.fail("must not publish"),
    }),
    /registry metadata is malformed/,
  );
});

test("recovery refuses publication when existing-package provenance cannot be verified", async (context) => {
  const input = await preparedFixture(context);
  await assert.rejects(
    publishBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        input.registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => {
        throw new Error("design-token provenance differs");
      },
      publishArchive: async () => assert.fail("must not publish"),
    }),
    /design-token provenance differs/,
  );
});

test("recovery preparation rejects candidate copies that differ from the pinned ZIP", async (context) => {
  const input = await fixture(context);
  await replaceLooseUiCandidate(input);
  await assert.rejects(
    prepareBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      inspectRegistry: async ({ coordinate }) =>
        coordinate === input.evidence.packages.designTokens.coordinate
          ? metadata(input.contract, input.evidence, "designTokens")
          : null,
      verifyExistingPackage: async () => true,
    }),
    /candidate copy differs from the pinned original artifact/,
  );
});

test("protected recovery publishes nothing when transferred copies differ from the pinned ZIP", async (context) => {
  const input = await preparedFixture(context);
  await replaceLooseUiCandidate(input);
  input.recoveryEvidence.expectedProvenance.ui.artifactDigest =
    input.evidence.packages.ui.integrity;
  const published = [];
  await assert.rejects(
    publishBootstrapRecovery({
      ...input,
      archiveRoot: input.root,
      identifyPublisher: async () => "marc.fawaz",
      inspectRegistry: async ({ coordinate }) =>
        input.registry.get(coordinate) ?? null,
      verifyExistingPackage: async () => true,
      publishArchive: async ({ role, candidate }) => {
        published.push(role);
        input.registry.set(
          candidate.coordinate,
          metadata(input.contract, input.evidence, role),
        );
      },
    }),
    /candidate copy differs from the pinned original artifact/,
  );
  assert.deepEqual(published, []);
});

test("recovery rejects traversal and link entries before extraction", async (context) => {
  await context.test("traversal", async (subcontext) => {
    const input = await fixture(subcontext);
    const outsidePath = path.join(path.dirname(input.root), "outside.txt");
    await writeFile(outsidePath, "outside");
    const artifactZipPath = path.join(
      path.dirname(input.root),
      "traversal-artifact.zip",
    );
    await run(
      "zip",
      [
        "-q",
        artifactZipPath,
        "candidate-evidence.json",
        "candidate-transfer.json",
        ...packageRoles.map((role) => input.evidence.packages[role].filename),
        "../outside.txt",
      ],
      { cwd: input.root },
    );
    await updateArtifactZipPin(input, artifactZipPath);
    await assert.rejects(
      prepareBootstrapRecovery({
        ...input,
        inspectRegistry: async () => assert.fail("must reject before registry"),
        verifyExistingPackage: async () => assert.fail("must not verify"),
      }),
      /recovery ZIP candidate file set differs/,
    );
  });

  await context.test("symbolic link", async (subcontext) => {
    const input = await fixture(subcontext);
    const linkedRoot = await mkdtemp(
      path.join(path.dirname(input.root), "linked-candidate-"),
    );
    await cp(input.root, linkedRoot, { recursive: true });
    const transferPath = path.join(linkedRoot, "candidate-transfer.json");
    const transferTarget = path.join(linkedRoot, "transfer-target.json");
    await cp(transferPath, transferTarget);
    await rm(transferPath);
    await symlink("transfer-target.json", transferPath);
    const artifactZipPath = path.join(
      path.dirname(input.root),
      "linked-artifact.zip",
    );
    await run(
      "zip",
      [
        "-q",
        "-y",
        artifactZipPath,
        "candidate-evidence.json",
        "candidate-transfer.json",
        ...packageRoles.map((role) => input.evidence.packages[role].filename),
      ],
      { cwd: linkedRoot },
    );
    await updateArtifactZipPin(input, artifactZipPath);
    await assert.rejects(
      prepareBootstrapRecovery({
        ...input,
        inspectRegistry: async () => assert.fail("must reject before registry"),
        verifyExistingPackage: async () => assert.fail("must not verify"),
      }),
      /must not be a link or special file/,
    );
  });
});
