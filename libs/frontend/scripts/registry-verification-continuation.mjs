import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  constants,
  copyFile,
  lstat,
  mkdir,
  readFile,
  readdir,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertOriginalArtifactMetadata,
  validateBootstrapRecoveryEvidence,
  validateBootstrapRecoveryPlan,
} from "./bootstrap-recovery-contract.mjs";
import { fixtureArchiveFilename } from "./fixture-transfer.mjs";
import { loadReleaseContract, packageRoles } from "./release-contract.mjs";
import {
  recoveryArtifactMetadataFilename,
  recoveryArtifactZipFilename,
  recoveryCandidateEvidenceFilename,
  recoveryTransferMetadataFilename,
  sha256Hex,
  verifyOriginalRecoveryArtifact,
  verifyPinnedArtifactZip,
} from "./recovery-artifact.mjs";
import { releaseContractDigest } from "./release-evidence.mjs";

export const verificationArtifactZipFilename =
  "bootstrap-recovery-artifact.zip";
export const verificationArtifactMetadataFilename =
  "bootstrap-recovery-artifact-metadata.json";
export const verificationInputsFilename = "registry-verification-inputs.json";

export function registryVerificationContinuationPlanDigest(value) {
  return `sha256-${createHash("sha256")
    .update(JSON.stringify(value))
    .digest("base64")}`;
}

function expectedWorkflowRef(contract) {
  const workflow = new URL(contract.expectedProvenance.workflow);
  return `${workflow.pathname.slice(1)}${workflow.hash}`;
}

function assertArtifactIdentity(value, label, prefix) {
  assert.deepEqual(Object.keys(value ?? {}).sort(), [
    "artifactId",
    "artifactName",
    "artifactZipSha256",
    "sourceCommit",
    "workflowRunAttempt",
    "workflowRunId",
  ]);
  assert.match(
    value.sourceCommit,
    /^[0-9a-f]{40}$/,
    `${label} commit is invalid`,
  );
  assert.match(value.workflowRunId, /^\d+$/, `${label} run ID is invalid`);
  assert.match(
    value.workflowRunAttempt,
    /^\d+$/,
    `${label} run attempt is invalid`,
  );
  assert(Number.isSafeInteger(value.artifactId), `${label} ID is invalid`);
  assert.equal(
    value.artifactName,
    `${prefix}-${value.sourceCommit}-${value.workflowRunId}-${value.workflowRunAttempt}`,
    `${label} name differs`,
  );
  assert.match(
    value.artifactZipSha256,
    /^[0-9a-f]{64}$/,
    `${label} ZIP digest is invalid`,
  );
}

export function validateRegistryVerificationContinuationPlan({
  plan,
  contract,
  recoveryPlan,
}) {
  assert.deepEqual(Object.keys(plan ?? {}).sort(), [
    "kind",
    "originalCandidate",
    "publicationExecution",
    "publicationSourceCommits",
    "recoveryArtifact",
    "schemaVersion",
    "state",
    "verificationExecution",
  ]);
  assert.equal(
    plan.schemaVersion,
    1,
    "unsupported verification continuation schema",
  );
  assert.equal(plan.kind, "frontend-registry-verification-continuation");
  assert.equal(
    plan.state,
    "reviewed",
    "verification continuation is not reviewed",
  );
  validateBootstrapRecoveryPlan(recoveryPlan);
  assertArtifactIdentity(
    plan.recoveryArtifact,
    "recovery artifact",
    "frontend-packages-bootstrap-recovery",
  );
  assertArtifactIdentity(
    plan.originalCandidate,
    "original candidate artifact",
    "frontend-packages-release",
  );
  assert.deepEqual(
    plan.originalCandidate,
    recoveryPlan.incident,
    "verification original candidate differs from the recovery plan",
  );
  assert.deepEqual(Object.keys(plan.publicationExecution ?? {}).sort(), [
    "ref",
    "repository",
    "runAttempt",
    "runId",
    "sourceCommit",
    "workflow",
    "workflowRef",
  ]);
  assert.equal(plan.publicationExecution.repository, "ThalesGroup/fred");
  assert.equal(plan.publicationExecution.ref, "refs/heads/swift");
  assert.equal(
    plan.publicationExecution.sourceCommit,
    plan.recoveryArtifact.sourceCommit,
    "publication commit differs from the recovery artifact",
  );
  assert.equal(
    plan.publicationExecution.runId,
    plan.recoveryArtifact.workflowRunId,
    "publication run differs from the recovery artifact",
  );
  assert.equal(
    plan.publicationExecution.runAttempt,
    plan.recoveryArtifact.workflowRunAttempt,
    "publication attempt differs from the recovery artifact",
  );
  assert.equal(
    plan.publicationExecution.workflowRef,
    expectedWorkflowRef(contract),
  );
  assert.equal(plan.publicationExecution.workflow, "Publish frontend packages");
  assert.deepEqual(
    Object.keys(plan.publicationSourceCommits ?? {}).sort(),
    [...packageRoles].sort(),
  );
  assert.equal(
    plan.publicationSourceCommits.designTokens,
    recoveryPlan.incident.sourceCommit,
  );
  for (const role of ["ui", "iframeSdk"])
    assert.equal(
      plan.publicationSourceCommits[role],
      plan.publicationExecution.sourceCommit,
      `${role} publication commit differs`,
    );
  assert.deepEqual(Object.keys(plan.verificationExecution ?? {}).sort(), [
    "ref",
    "repository",
    "sourceCommitPolicy",
    "workflow",
  ]);
  assert.deepEqual(plan.verificationExecution, recoveryPlan.recoveryExecution);
  assert.equal(
    plan.verificationExecution.workflow,
    contract.expectedProvenance.workflow,
  );
  return plan;
}

export function assertRecoveryArtifactMetadata(plan, metadata) {
  const expected = plan.recoveryArtifact;
  assert.equal(
    metadata?.id,
    expected.artifactId,
    "recovery artifact ID differs",
  );
  assert.equal(
    metadata?.name,
    expected.artifactName,
    "recovery artifact name differs",
  );
  assert.equal(metadata?.expired, false, "recovery artifact has expired");
  assert.equal(
    metadata?.digest,
    `sha256:${expected.artifactZipSha256}`,
    "recovery artifact ZIP digest differs",
  );
  assert.equal(
    String(metadata?.workflow_run?.id),
    expected.workflowRunId,
    "recovery artifact workflow run differs",
  );
  assert.equal(
    metadata?.workflow_run?.head_sha,
    expected.sourceCommit,
    "recovery artifact source commit differs",
  );
  assert.equal(
    metadata?.workflow_run?.head_branch,
    "swift",
    "recovery artifact source branch differs",
  );
  return true;
}

export function githubExecution(environment = process.env) {
  return {
    actions: environment.GITHUB_ACTIONS,
    repository: environment.GITHUB_REPOSITORY,
    ref: environment.GITHUB_REF,
    sha: environment.GITHUB_SHA,
    workflowRef: environment.GITHUB_WORKFLOW_REF,
    workflow: environment.GITHUB_WORKFLOW,
    runId: environment.GITHUB_RUN_ID,
    runAttempt: environment.GITHUB_RUN_ATTEMPT,
  };
}

export function assertVerificationExecution({ contract, plan, github }) {
  assert.equal(github.actions, "true", "verification requires GitHub Actions");
  assert.equal(
    github.repository,
    plan.verificationExecution.repository,
    "verification repository differs",
  );
  assert.equal(
    github.ref,
    plan.verificationExecution.ref,
    "verification ref differs",
  );
  assert.match(
    github.sha ?? "",
    /^[0-9a-f]{40}$/,
    "verification commit is invalid",
  );
  assert.equal(
    github.workflowRef,
    expectedWorkflowRef(contract),
    "verification workflow identity differs",
  );
  assert.equal(github.workflow, "Publish frontend packages");
  assert.match(github.runId ?? "", /^\d+$/, "verification run ID is invalid");
  assert.match(
    github.runAttempt ?? "",
    /^\d+$/,
    "verification run attempt is invalid",
  );
  return true;
}

function historicalGithub(plan) {
  return {
    actions: "true",
    ...plan.publicationExecution,
    sha: plan.publicationExecution.sourceCommit,
  };
}

function expectedRecoveryArtifactFiles(contract) {
  return [
    "bootstrap-recovery-evidence.json",
    recoveryArtifactMetadataFilename,
    recoveryArtifactZipFilename,
    recoveryCandidateEvidenceFilename,
    recoveryTransferMetadataFilename,
    ...packageRoles.map((role) => {
      const selected = contract.packages[role];
      return fixtureArchiveFilename(selected.name, selected.version);
    }),
  ].sort();
}

async function readJson(selectedPath) {
  return JSON.parse(await readFile(selectedPath, "utf8"));
}

async function inspectContinuationArtifact({
  contract,
  recoveryPlan,
  plan,
  artifactZipPath,
  artifactMetadata,
  transferredRoot,
}) {
  validateRegistryVerificationContinuationPlan({
    plan,
    contract,
    recoveryPlan,
  });
  assertRecoveryArtifactMetadata(plan, artifactMetadata);
  const outer = await verifyPinnedArtifactZip({
    artifactZipPath,
    artifactZipSha256: plan.recoveryArtifact.artifactZipSha256,
    expectedFiles: expectedRecoveryArtifactFiles(contract),
    label: "bootstrap recovery artifact",
  });
  try {
    const [evidence, recoveryEvidence, originalMetadata] = await Promise.all([
      readJson(path.join(outer.root, recoveryCandidateEvidenceFilename)),
      readJson(path.join(outer.root, "bootstrap-recovery-evidence.json")),
      readJson(path.join(outer.root, recoveryArtifactMetadataFilename)),
    ]);
    assertOriginalArtifactMetadata(recoveryPlan, originalMetadata);
    validateBootstrapRecoveryEvidence({
      contract,
      plan: recoveryPlan,
      evidence,
      recoveryEvidence,
      github: historicalGithub(plan),
    });
    for (const role of packageRoles)
      assert.equal(
        recoveryEvidence.expectedProvenance[role].sourceCommit,
        plan.publicationSourceCommits[role],
        `${role} historical publication commit differs`,
      );
    const original = await verifyOriginalRecoveryArtifact({
      artifactZipPath: path.join(outer.root, recoveryArtifactZipFilename),
      contract,
      plan: recoveryPlan,
      transferredRoot: outer.root,
      transferredEvidence: evidence,
    });
    await original.dispose();
    if (transferredRoot) {
      const allowed = [
        ...outer.expectedFiles,
        verificationArtifactZipFilename,
        verificationArtifactMetadataFilename,
        verificationInputsFilename,
      ].sort();
      assert.deepEqual(
        (await readdir(transferredRoot)).sort(),
        allowed,
        "verification transfer file set differs",
      );
      for (const filename of outer.expectedFiles) {
        const selected = path.join(transferredRoot, filename);
        const stats = await lstat(selected);
        assert(
          stats.isFile() && !stats.isSymbolicLink(),
          `verification transfer ${filename} must be a regular file`,
        );
        assert.equal(
          sha256Hex(await readFile(selected)),
          sha256Hex(await readFile(path.join(outer.root, filename))),
          `verification transfer ${filename} differs from the pinned artifact`,
        );
      }
    }
    return { outer, evidence, recoveryEvidence };
  } catch (error) {
    await outer.dispose();
    throw error;
  }
}

async function materializeContinuationArtifact({
  inspected,
  artifactZipPath,
  artifactMetadataPath,
  outputRoot,
}) {
  const root = path.resolve(outputRoot);
  await mkdir(root, { recursive: true });
  const stats = await lstat(root);
  assert(stats.isDirectory() && !stats.isSymbolicLink());
  assert.deepEqual(
    await readdir(root),
    [],
    "verification output root must be empty",
  );
  for (const filename of inspected.outer.expectedFiles)
    await copyFile(
      path.join(inspected.outer.root, filename),
      path.join(root, filename),
      constants.COPYFILE_EXCL,
    );
  await copyFile(
    path.resolve(artifactZipPath),
    path.join(root, verificationArtifactZipFilename),
    constants.COPYFILE_EXCL,
  );
  await copyFile(
    path.resolve(artifactMetadataPath),
    path.join(root, verificationArtifactMetadataFilename),
    constants.COPYFILE_EXCL,
  );
  return root;
}

function verificationInputs({
  contract,
  plan,
  recoveryEvidence,
  github,
  createdAt,
}) {
  return {
    schemaVersion: 1,
    kind: "frontend-registry-verification-inputs",
    createdAt,
    planDigest: registryVerificationContinuationPlanDigest(plan),
    contractDigest: releaseContractDigest(contract),
    recoveryArtifact: { ...plan.recoveryArtifact },
    originalCandidate: { ...plan.originalCandidate },
    publicationExecution: { ...plan.publicationExecution },
    publicationSourceCommits: { ...plan.publicationSourceCommits },
    verificationExecution: {
      repository: github.repository,
      ref: github.ref,
      sourceCommit: github.sha,
      workflowRef: github.workflowRef,
      workflow: github.workflow,
      runId: github.runId,
      runAttempt: github.runAttempt,
    },
    expectedProvenance: structuredClone(recoveryEvidence.expectedProvenance),
  };
}

export async function prepareRegistryVerificationContinuation({
  contract,
  recoveryPlan,
  plan,
  artifactZipPath,
  artifactMetadataPath,
  artifactMetadata,
  github,
  outputRoot,
  createdAt = new Date().toISOString(),
}) {
  assertVerificationExecution({ contract, plan, github });
  const inspected = await inspectContinuationArtifact({
    contract,
    recoveryPlan,
    plan,
    artifactZipPath,
    artifactMetadata,
  });
  try {
    const root = await materializeContinuationArtifact({
      inspected,
      artifactZipPath,
      artifactMetadataPath,
      outputRoot,
    });
    return {
      root,
      inputs: verificationInputs({
        contract,
        plan,
        recoveryEvidence: inspected.recoveryEvidence,
        github,
        createdAt,
      }),
    };
  } finally {
    await inspected.outer.dispose();
  }
}

export function validateRegistryVerificationInputs({
  contract,
  plan,
  inputs,
  github,
}) {
  assert.deepEqual(Object.keys(inputs ?? {}).sort(), [
    "contractDigest",
    "createdAt",
    "expectedProvenance",
    "kind",
    "originalCandidate",
    "planDigest",
    "publicationExecution",
    "publicationSourceCommits",
    "recoveryArtifact",
    "schemaVersion",
    "verificationExecution",
  ]);
  assert.equal(inputs.schemaVersion, 1);
  assert.equal(inputs.kind, "frontend-registry-verification-inputs");
  assert.match(inputs.createdAt ?? "", /^\d{4}-\d{2}-\d{2}T.*Z$/);
  assert.equal(
    inputs.planDigest,
    registryVerificationContinuationPlanDigest(plan),
  );
  assert.equal(inputs.contractDigest, releaseContractDigest(contract));
  for (const field of [
    "recoveryArtifact",
    "originalCandidate",
    "publicationExecution",
    "publicationSourceCommits",
  ])
    assert.deepEqual(
      inputs[field],
      plan[field],
      `${field} differs from the reviewed plan`,
    );
  assert.deepEqual(
    inputs.verificationExecution,
    {
      repository: github.repository,
      ref: github.ref,
      sourceCommit: github.sha,
      workflowRef: github.workflowRef,
      workflow: github.workflow,
      runId: github.runId,
      runAttempt: github.runAttempt,
    },
    "verification execution differs from the prepared inputs",
  );
  return inputs;
}

export async function verifyRegistryVerificationContinuation({
  contract,
  recoveryPlan,
  plan,
  inputs,
  artifactZipPath,
  artifactMetadata,
  transferredRoot,
  github,
}) {
  validateRegistryVerificationContinuationPlan({
    plan,
    contract,
    recoveryPlan,
  });
  assertVerificationExecution({ contract, plan, github });
  validateRegistryVerificationInputs({ contract, plan, inputs, github });
  const inspected = await inspectContinuationArtifact({
    contract,
    recoveryPlan,
    plan,
    artifactZipPath,
    artifactMetadata,
    transferredRoot,
  });
  try {
    assert.deepEqual(
      inputs.expectedProvenance,
      inspected.recoveryEvidence.expectedProvenance,
      "verification provenance expectations differ from retained recovery evidence",
    );
    return {
      evidence: inspected.evidence,
      provenanceExpectations: inputs.expectedProvenance,
      historicalPublication: inputs.publicationExecution,
      verificationExecution: inputs.verificationExecution,
    };
  } finally {
    await inspected.outer.dispose();
  }
}

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

async function loadJson(selectedPath) {
  assert(selectedPath, "JSON path is required");
  return JSON.parse(await readFile(path.resolve(selectedPath), "utf8"));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const contractPath = optionValue("--contract");
  const recoveryPlanPath = optionValue("--recovery-plan");
  const planPath = optionValue("--plan");
  const artifactZipPath = optionValue("--artifact-zip");
  const artifactMetadataPath = optionValue("--artifact-metadata");
  const outputRoot = optionValue("--output-root");
  const outputPath = optionValue("--output");
  for (const [name, value] of Object.entries({
    "--contract": contractPath,
    "--recovery-plan": recoveryPlanPath,
    "--plan": planPath,
    "--artifact-zip": artifactZipPath,
    "--artifact-metadata": artifactMetadataPath,
    "--output-root": outputRoot,
    "--output": outputPath,
  }))
    assert(value, `${name} is required`);
  const result = await prepareRegistryVerificationContinuation({
    contract: await loadReleaseContract(contractPath),
    recoveryPlan: await loadJson(recoveryPlanPath),
    plan: await loadJson(planPath),
    artifactZipPath,
    artifactMetadataPath,
    artifactMetadata: await loadJson(artifactMetadataPath),
    github: githubExecution(),
    outputRoot,
  });
  const resolvedOutput = path.resolve(outputPath);
  assert.equal(
    path.dirname(resolvedOutput),
    path.resolve(result.root),
    "verification inputs must be written inside the materialized output root",
  );
  assert.equal(path.basename(resolvedOutput), verificationInputsFilename);
  await writeFile(
    resolvedOutput,
    `${JSON.stringify(result.inputs, null, 2)}\n`,
    {
      flag: "wx",
    },
  );
  process.stdout.write(
    `prepared registry verification inputs at ${outputPath}\n`,
  );
}
