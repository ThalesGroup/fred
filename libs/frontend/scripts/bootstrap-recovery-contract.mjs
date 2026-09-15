import assert from "node:assert/strict";
import { createHash } from "node:crypto";

import { packageRoles } from "./release-contract.mjs";
import { releaseContractDigest } from "./release-evidence.mjs";

const recoveryPublishOrder = ["ui", "iframeSdk"];

export function bootstrapRecoveryPlanDigest(value) {
  return `sha256-${createHash("sha256")
    .update(JSON.stringify(value))
    .digest("base64")}`;
}

function expectedWorkflowRef(contract) {
  const workflow = new URL(contract.expectedProvenance.workflow);
  return `${workflow.pathname.slice(1)}${workflow.hash}`;
}

export function validateBootstrapRecoveryPlan(plan) {
  assert.deepEqual(Object.keys(plan).sort(), [
    "incident",
    "kind",
    "missingRoles",
    "publishedRoles",
    "recoveryExecution",
    "schemaVersion",
    "state",
  ]);
  assert.equal(plan.schemaVersion, 1, "unsupported recovery plan schema");
  assert.equal(plan.kind, "frontend-bootstrap-partial-recovery");
  assert.equal(plan.state, "reviewed", "recovery plan is not reviewed");
  assert.match(plan.incident?.sourceCommit ?? "", /^[0-9a-f]{40}$/);
  assert.deepEqual(Object.keys(plan.incident).sort(), [
    "artifactId",
    "artifactName",
    "artifactZipSha256",
    "sourceCommit",
    "workflowRunAttempt",
    "workflowRunId",
  ]);
  assert.match(plan.incident?.workflowRunId ?? "", /^\d+$/);
  assert.match(plan.incident?.workflowRunAttempt ?? "", /^\d+$/);
  assert(Number.isSafeInteger(plan.incident?.artifactId));
  assert.equal(
    plan.incident.artifactName,
    `frontend-packages-release-${plan.incident.sourceCommit}-${plan.incident.workflowRunId}-${plan.incident.workflowRunAttempt}`,
    "original release artifact name differs",
  );
  assert.match(plan.incident?.artifactZipSha256 ?? "", /^[0-9a-f]{64}$/);
  assert.deepEqual(plan.publishedRoles, ["designTokens"]);
  assert.deepEqual(plan.missingRoles, recoveryPublishOrder);
  assert.deepEqual(
    [...plan.publishedRoles, ...plan.missingRoles].sort(),
    [...packageRoles].sort(),
    "recovery roles do not partition the release packages",
  );
  assert.equal(plan.recoveryExecution?.repository, "ThalesGroup/fred");
  assert.deepEqual(Object.keys(plan.recoveryExecution).sort(), [
    "ref",
    "repository",
    "sourceCommitPolicy",
    "workflow",
  ]);
  assert.equal(plan.recoveryExecution?.ref, "refs/heads/swift");
  assert.equal(
    plan.recoveryExecution?.sourceCommitPolicy,
    "github-actions-sha",
  );
  assert.match(
    plan.recoveryExecution?.workflow ?? "",
    /^https:\/\/github\.com\/ThalesGroup\/fred\/\.github\/workflows\/Publish-frontend-packages\.yml@refs\/heads\/swift$/,
  );
  return plan;
}

export function assertOriginalArtifactMetadata(plan, metadata) {
  validateBootstrapRecoveryPlan(plan);
  assert.equal(metadata?.id, plan.incident.artifactId, "artifact ID differs");
  assert.equal(
    metadata?.name,
    plan.incident.artifactName,
    "artifact name differs",
  );
  assert.equal(metadata?.expired, false, "original artifact has expired");
  assert.equal(
    metadata?.digest,
    `sha256:${plan.incident.artifactZipSha256}`,
    "artifact ZIP digest differs",
  );
  assert.equal(
    String(metadata?.workflow_run?.id),
    plan.incident.workflowRunId,
    "artifact workflow run differs",
  );
  assert.equal(
    metadata?.workflow_run?.head_sha,
    plan.incident.sourceCommit,
    "artifact source commit differs",
  );
  assert.equal(
    metadata?.workflow_run?.head_branch,
    "swift",
    "artifact source branch differs",
  );
  return true;
}

export function assertRecoveryWorkflowIdentity({ contract, plan, github }) {
  validateBootstrapRecoveryPlan(plan);
  assert.equal(github.actions, "true", "recovery requires GitHub Actions");
  assert.equal(
    github.repository,
    plan.recoveryExecution.repository,
    "recovery repository differs",
  );
  assert.equal(github.ref, plan.recoveryExecution.ref, "recovery ref differs");
  assert.match(github.sha ?? "", /^[0-9a-f]{40}$/);
  assert.equal(
    github.workflowRef,
    expectedWorkflowRef(contract),
    "recovery workflow identity differs from the release contract",
  );
  assert.equal(
    contract.expectedProvenance.workflow,
    plan.recoveryExecution.workflow,
    "recovery plan workflow differs from the release contract",
  );
  assert.match(github.runId ?? "", /^\d+$/, "recovery run ID is invalid");
  assert.match(
    github.runAttempt ?? "",
    /^\d+$/,
    "recovery run attempt is invalid",
  );
  return true;
}

export function recoveryExpectedProvenance(evidence, github) {
  return Object.fromEntries(
    packageRoles.map((role) => [
      role,
      {
        ...evidence.packages[role].expectedProvenance,
        sourceCommit:
          role === "designTokens" ? evidence.sourceCommit : github.sha,
      },
    ]),
  );
}

export function assertOriginalRecoveryEvidence({ plan, evidence }) {
  assert.equal(evidence.sourceCommit, plan.incident.sourceCommit);
  assert.equal(evidence.transfer?.kind, "release-candidate-archive-transfer");
  assert.equal(evidence.transfer?.sourceTreeClean, true);
  assert.equal(evidence.transfer?.metadataFilename, "candidate-transfer.json");
  assert.match(
    evidence.transfer?.metadataDigest ?? "",
    /^sha256-[A-Za-z0-9+/]+={0,2}$/,
  );
  assert.equal(evidence.transfer?.execution?.provider, "github-actions");
  assert.equal(
    evidence.transfer?.execution?.repository,
    plan.recoveryExecution.repository,
  );
  assert.equal(
    evidence.transfer?.artifactName,
    `frontend-packages-candidate-${plan.incident.sourceCommit}-${plan.incident.workflowRunId}-${plan.incident.workflowRunAttempt}`,
  );
  assert.equal(
    evidence.transfer?.execution?.runId,
    plan.incident.workflowRunId,
  );
  assert.equal(
    evidence.transfer?.execution?.runAttempt,
    plan.incident.workflowRunAttempt,
  );
}

export function validateBootstrapRecoveryEvidence({
  contract,
  plan,
  evidence,
  recoveryEvidence,
  github,
}) {
  validateBootstrapRecoveryPlan(plan);
  assertRecoveryWorkflowIdentity({ contract, plan, github });
  assertOriginalRecoveryEvidence({ plan, evidence });
  assert.equal(evidence.kind, "release-candidate-evidence");
  assert.equal(evidence.contractDigest, releaseContractDigest(contract));
  assert.deepEqual(Object.keys(recoveryEvidence).sort(), [
    "contractDigest",
    "createdAt",
    "expectedProvenance",
    "kind",
    "missingRoles",
    "originalCandidate",
    "planDigest",
    "publishedRoles",
    "recoveryExecution",
    "schemaVersion",
  ]);
  assert.equal(recoveryEvidence.schemaVersion, 1);
  assert.equal(recoveryEvidence.kind, "frontend-bootstrap-recovery-evidence");
  assert.match(
    recoveryEvidence.createdAt ?? "",
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/,
    "recovery evidence timestamp is invalid",
  );
  assert.equal(recoveryEvidence.planDigest, bootstrapRecoveryPlanDigest(plan));
  assert.equal(
    recoveryEvidence.contractDigest,
    releaseContractDigest(contract),
  );
  assert.deepEqual(recoveryEvidence.originalCandidate, plan.incident);
  assert.deepEqual(recoveryEvidence.publishedRoles, plan.publishedRoles);
  assert.deepEqual(recoveryEvidence.missingRoles, plan.missingRoles);
  assert.deepEqual(
    recoveryEvidence.expectedProvenance,
    recoveryExpectedProvenance(evidence, github),
    "recovery provenance expectations differ",
  );
  assert.deepEqual(recoveryEvidence.recoveryExecution, {
    repository: github.repository,
    ref: github.ref,
    sourceCommit: github.sha,
    workflowRef: github.workflowRef,
    workflow: github.workflow,
    runId: github.runId,
    runAttempt: github.runAttempt,
  });
  return true;
}
