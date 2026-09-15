import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  cp,
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
import {
  prepareRegistryVerificationContinuation,
  registryVerificationContinuationPlanDigest,
  validateRegistryVerificationInputs,
  verifyRegistryVerificationContinuation,
} from "../scripts/registry-verification-continuation.mjs";

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

async function continuationFixture(context) {
  const input = await preparedFixture(context);
  const recoveryRoot = path.join(input.root, "recovery-artifact");
  await mkdir(recoveryRoot);
  const candidateFiles = [
    "candidate-evidence.json",
    "candidate-transfer.json",
    ...packageRoles.map((role) => input.evidence.packages[role].filename),
  ];
  for (const filename of candidateFiles)
    await cp(
      path.join(input.root, filename),
      path.join(recoveryRoot, filename),
    );
  await cp(
    input.artifactZipPath,
    path.join(recoveryRoot, "original-release-artifact.zip"),
  );
  await writeFile(
    path.join(recoveryRoot, "original-artifact-metadata.json"),
    `${JSON.stringify(input.artifactMetadata, null, 2)}\n`,
  );
  await writeFile(
    path.join(recoveryRoot, "bootstrap-recovery-evidence.json"),
    `${JSON.stringify(input.recoveryEvidence, null, 2)}\n`,
  );
  const recoveryArtifactZip = path.join(input.root, "recovery-artifact.zip");
  const recoveryFiles = [
    "bootstrap-recovery-evidence.json",
    "original-artifact-metadata.json",
    "original-release-artifact.zip",
    ...candidateFiles,
  ];
  await run("zip", ["-q", recoveryArtifactZip, ...recoveryFiles], {
    cwd: recoveryRoot,
  });
  const recoveryArtifact = {
    sourceCommit: input.github.sha,
    workflowRunId: input.github.runId,
    workflowRunAttempt: input.github.runAttempt,
    artifactId: 90000000001,
    artifactName: `frontend-packages-bootstrap-recovery-${input.github.sha}-${input.github.runId}-${input.github.runAttempt}`,
    artifactZipSha256: createHash("sha256")
      .update(await readFile(recoveryArtifactZip))
      .digest("hex"),
  };
  const recoveryArtifactMetadata = {
    id: recoveryArtifact.artifactId,
    name: recoveryArtifact.artifactName,
    expired: false,
    digest: `sha256:${recoveryArtifact.artifactZipSha256}`,
    workflow_run: {
      id: Number(recoveryArtifact.workflowRunId),
      head_sha: recoveryArtifact.sourceCommit,
      head_branch: "swift",
    },
  };
  const continuationPlan = {
    schemaVersion: 1,
    kind: "frontend-registry-verification-continuation",
    state: "reviewed",
    recoveryArtifact,
    originalCandidate: structuredClone(input.plan.incident),
    publicationExecution: {
      repository: input.github.repository,
      ref: input.github.ref,
      sourceCommit: input.github.sha,
      workflowRef: input.github.workflowRef,
      workflow: input.github.workflow,
      runId: input.github.runId,
      runAttempt: input.github.runAttempt,
    },
    publicationSourceCommits: {
      designTokens: input.plan.incident.sourceCommit,
      ui: input.github.sha,
      iframeSdk: input.github.sha,
    },
    verificationExecution: structuredClone(input.plan.recoveryExecution),
  };
  const verificationGithub = {
    ...input.github,
    sha: "d".repeat(40),
    runId: "50000000000",
    runAttempt: "1",
  };
  return {
    ...input,
    continuationPlan,
    recoveryArtifactZip,
    recoveryArtifactMetadata,
    recoveryArtifactMetadataPath: path.join(
      input.root,
      "recovery-artifact-metadata.json",
    ),
    verificationGithub,
  };
}

async function prepareContinuation(input, outputRoot) {
  await writeFile(
    input.recoveryArtifactMetadataPath,
    `${JSON.stringify(input.recoveryArtifactMetadata, null, 2)}\n`,
  );
  const result = await prepareRegistryVerificationContinuation({
    contract: input.contract,
    recoveryPlan: input.plan,
    plan: input.continuationPlan,
    artifactZipPath: input.recoveryArtifactZip,
    artifactMetadataPath: input.recoveryArtifactMetadataPath,
    artifactMetadata: input.recoveryArtifactMetadata,
    github: input.verificationGithub,
    outputRoot,
    createdAt: "2026-09-14T20:00:00.000Z",
  });
  await writeFile(
    path.join(outputRoot, "registry-verification-inputs.json"),
    `${JSON.stringify(result.inputs, null, 2)}\n`,
  );
  return result;
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

test("verification continuation preserves historical publication identity and is rerunnable", async (context) => {
  const input = await continuationFixture(context);
  const outputRoot = path.join(input.root, "verification-transfer");
  const prepared = await prepareContinuation(input, outputRoot);
  assert.equal(
    prepared.inputs.planDigest,
    registryVerificationContinuationPlanDigest(input.continuationPlan),
  );
  assert.equal(
    prepared.inputs.publicationExecution.sourceCommit,
    input.github.sha,
  );
  assert.equal(
    prepared.inputs.verificationExecution.sourceCommit,
    input.verificationGithub.sha,
  );
  assert.notEqual(
    prepared.inputs.publicationExecution.runId,
    prepared.inputs.verificationExecution.runId,
  );
  validateRegistryVerificationInputs({
    contract: input.contract,
    plan: input.continuationPlan,
    inputs: prepared.inputs,
    github: input.verificationGithub,
  });

  const verify = () =>
    verifyRegistryVerificationContinuation({
      contract: input.contract,
      recoveryPlan: input.plan,
      plan: input.continuationPlan,
      inputs: prepared.inputs,
      artifactZipPath: path.join(outputRoot, "bootstrap-recovery-artifact.zip"),
      artifactMetadata: input.recoveryArtifactMetadata,
      transferredRoot: outputRoot,
      github: input.verificationGithub,
    });
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const verified = await verify();
    assert.deepEqual(
      verified.provenanceExpectations,
      input.recoveryEvidence.expectedProvenance,
    );
    assert.equal(
      verified.verificationExecution.sourceCommit,
      input.verificationGithub.sha,
    );
  }
});

test("verification continuation rejects artifact and execution drift", async (context) => {
  const input = await continuationFixture(context);
  const outputRoot = path.join(input.root, "verification-transfer");
  const prepared = await prepareContinuation(input, outputRoot);
  const zipPath = path.join(outputRoot, "bootstrap-recovery-artifact.zip");
  await writeFile(zipPath, "changed recovery artifact");
  await assert.rejects(
    verifyRegistryVerificationContinuation({
      contract: input.contract,
      recoveryPlan: input.plan,
      plan: input.continuationPlan,
      inputs: prepared.inputs,
      artifactZipPath: zipPath,
      artifactMetadata: input.recoveryArtifactMetadata,
      transferredRoot: outputRoot,
      github: input.verificationGithub,
    }),
    /bootstrap recovery artifact ZIP digest differs/,
  );
  assert.throws(
    () =>
      validateRegistryVerificationInputs({
        contract: input.contract,
        plan: input.continuationPlan,
        inputs: prepared.inputs,
        github: { ...input.verificationGithub, runAttempt: "2" },
      }),
    /verification execution differs/,
  );
});

test("the verification continuation CLI materializes only pinned inputs", async (context) => {
  const input = await continuationFixture(context);
  const contractPath = path.join(input.root, "contract.json");
  const recoveryPlanPath = path.join(input.root, "recovery-plan.json");
  const continuationPlanPath = path.join(input.root, "continuation-plan.json");
  await Promise.all([
    writeFile(contractPath, `${JSON.stringify(input.contract, null, 2)}\n`),
    writeFile(recoveryPlanPath, `${JSON.stringify(input.plan, null, 2)}\n`),
    writeFile(
      continuationPlanPath,
      `${JSON.stringify(input.continuationPlan, null, 2)}\n`,
    ),
    writeFile(
      input.recoveryArtifactMetadataPath,
      `${JSON.stringify(input.recoveryArtifactMetadata, null, 2)}\n`,
    ),
  ]);
  const outputRoot = path.join(input.root, "cli-verification-transfer");
  const output = path.join(outputRoot, "registry-verification-inputs.json");
  const result = await run(
    process.execPath,
    [
      path.join(
        workspaceRoot,
        "scripts/registry-verification-continuation.mjs",
      ),
      "--contract",
      contractPath,
      "--recovery-plan",
      recoveryPlanPath,
      "--plan",
      continuationPlanPath,
      "--artifact-zip",
      input.recoveryArtifactZip,
      "--artifact-metadata",
      input.recoveryArtifactMetadataPath,
      "--output-root",
      outputRoot,
      "--output",
      output,
    ],
    {
      cwd: workspaceRoot,
      env: {
        ...process.env,
        GITHUB_ACTIONS: "true",
        GITHUB_REPOSITORY: input.verificationGithub.repository,
        GITHUB_REF: input.verificationGithub.ref,
        GITHUB_SHA: input.verificationGithub.sha,
        GITHUB_WORKFLOW_REF: input.verificationGithub.workflowRef,
        GITHUB_WORKFLOW: input.verificationGithub.workflow,
        GITHUB_RUN_ID: input.verificationGithub.runId,
        GITHUB_RUN_ATTEMPT: input.verificationGithub.runAttempt,
      },
    },
  );
  assert.match(result.stdout, /prepared registry verification inputs/);
  assert.equal(
    JSON.parse(await readFile(output, "utf8")).kind,
    "frontend-registry-verification-inputs",
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
      /original recovery artifact ZIP file set differs/,
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
