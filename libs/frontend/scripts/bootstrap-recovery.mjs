import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertExactPublishedMetadata,
  reconcilePublishedCandidate,
} from "./bootstrap-publish.mjs";
import {
  assertOriginalArtifactMetadata,
  assertOriginalRecoveryEvidence,
  assertRecoveryWorkflowIdentity,
  bootstrapRecoveryPlanDigest,
  recoveryExpectedProvenance,
  validateBootstrapRecoveryEvidence,
  validateBootstrapRecoveryPlan,
} from "./bootstrap-recovery-contract.mjs";
import { run } from "./process.mjs";
import {
  assertMaintainerConfirmed,
  loadReleaseContract,
} from "./release-contract.mjs";
import { releaseContractDigest } from "./release-evidence.mjs";
import { fetchExactPackageMetadata } from "./registry-metadata.mjs";
import {
  materializeVerifiedRecoveryArtifact,
  verifyOriginalRecoveryArtifact,
} from "./recovery-artifact.mjs";

const recoveryPublishOrder = ["ui", "iframeSdk"];

export {
  assertOriginalArtifactMetadata,
  assertRecoveryWorkflowIdentity,
  validateBootstrapRecoveryEvidence,
  validateBootstrapRecoveryPlan,
} from "./bootstrap-recovery-contract.mjs";

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function githubEnvironment() {
  return {
    actions: process.env.GITHUB_ACTIONS,
    repository: process.env.GITHUB_REPOSITORY,
    ref: process.env.GITHUB_REF,
    sha: process.env.GITHUB_SHA,
    workflowRef: process.env.GITHUB_WORKFLOW_REF,
    workflow: process.env.GITHUB_WORKFLOW,
    runId: process.env.GITHUB_RUN_ID,
    runAttempt: process.env.GITHUB_RUN_ATTEMPT,
  };
}

async function verifyPublishedPackage({
  role,
  contract,
  evidence,
  candidate,
  expected,
}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-recovery-registry-"));
  try {
    const {
      assertProvenanceIdentity,
      resolveNpmRegistryPackage,
      verifyNpmPackageProvenance,
    } = await import("./registry-verifier.mjs");
    const registryPackage = await resolveNpmRegistryPackage({
      coordinate: candidate.coordinate,
      registry: contract.registry,
      root,
      role,
      contract,
      evidence,
      expectedPackage: contract.packages[role],
      candidate,
    });
    const result = await verifyNpmPackageProvenance(registryPackage, {
      registry: contract.registry,
      expectedProvenance: expected,
      certificateIssuer: contract.expectedProvenance.certificateIssuer,
    });
    assertProvenanceIdentity({
      cryptographicallyVerified: result.cryptographicallyVerified,
      actual: result.identity,
      expected,
    });
    return registryPackage.metadata;
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

export async function prepareBootstrapRecovery({
  contract,
  plan,
  evidence: transferredEvidence,
  archiveRoot: transferredRoot,
  artifactZipPath,
  artifactMetadata,
  github,
  materializeRoot,
  inspectRegistry = fetchExactPackageMetadata,
  verifyExistingPackage = verifyPublishedPackage,
  createdAt = new Date().toISOString(),
}) {
  assertMaintainerConfirmed(contract);
  validateBootstrapRecoveryPlan(plan);
  assertOriginalArtifactMetadata(plan, artifactMetadata);
  assertRecoveryWorkflowIdentity({ contract, plan, github });
  const verified = await verifyOriginalRecoveryArtifact({
    artifactZipPath,
    contract,
    plan,
    transferredRoot,
    transferredEvidence,
  });
  try {
    const evidence = verified.evidence;
    assertOriginalRecoveryEvidence({ plan, evidence });
    const provenance = recoveryExpectedProvenance(evidence, github);

    for (const role of plan.publishedRoles) {
      const candidate = evidence.packages[role];
      const metadata = await inspectRegistry({
        coordinate: candidate.coordinate,
        registry: contract.registry,
        candidate,
      });
      assertExactPublishedMetadata(metadata, candidate);
      await verifyExistingPackage({
        role,
        contract,
        evidence,
        candidate,
        expected: provenance[role],
      });
    }
    for (const role of plan.missingRoles) {
      const candidate = evidence.packages[role];
      const metadata = await inspectRegistry({
        coordinate: candidate.coordinate,
        registry: contract.registry,
        candidate,
      });
      assert.equal(
        metadata,
        null,
        `${candidate.coordinate} unexpectedly exists; stop recovery`,
      );
    }

    const recoveryEvidence = {
      schemaVersion: 1,
      kind: "frontend-bootstrap-recovery-evidence",
      createdAt,
      planDigest: bootstrapRecoveryPlanDigest(plan),
      contractDigest: releaseContractDigest(contract),
      originalCandidate: { ...plan.incident },
      recoveryExecution: {
        repository: github.repository,
        ref: github.ref,
        sourceCommit: github.sha,
        workflowRef: github.workflowRef,
        workflow: github.workflow,
        runId: github.runId,
        runAttempt: github.runAttempt,
      },
      publishedRoles: [...plan.publishedRoles],
      missingRoles: [...plan.missingRoles],
      expectedProvenance: provenance,
    };
    if (materializeRoot)
      await materializeVerifiedRecoveryArtifact({
        verified,
        artifactZipPath,
        artifactMetadata,
        outputRoot: materializeRoot,
      });
    return recoveryEvidence;
  } finally {
    await verified.dispose();
  }
}

async function npmIdentity({ registry }) {
  return (await run("npm", ["whoami", "--registry", registry])).stdout.trim();
}

async function npmPublish({ archivePath, contract }) {
  await run("npm", [
    "publish",
    archivePath,
    "--provenance",
    "--access",
    "public",
    "--tag",
    contract.distTag,
    "--registry",
    contract.registry,
  ]);
}

export async function publishBootstrapRecovery({
  contract,
  plan,
  evidence: transferredEvidence,
  recoveryEvidence,
  archiveRoot: transferredRoot,
  artifactZipPath,
  artifactMetadata,
  github,
  identifyPublisher = npmIdentity,
  inspectRegistry = fetchExactPackageMetadata,
  verifyExistingPackage = verifyPublishedPackage,
  publishArchive = npmPublish,
  visibilityAttempts,
  visibilityDelayMilliseconds,
  waitForVisibility,
}) {
  assertMaintainerConfirmed(contract);
  validateBootstrapRecoveryPlan(plan);
  assertOriginalArtifactMetadata(plan, artifactMetadata);
  assertRecoveryWorkflowIdentity({ contract, plan, github });
  const verified = await verifyOriginalRecoveryArtifact({
    artifactZipPath,
    contract,
    plan,
    transferredRoot,
    transferredEvidence,
  });
  try {
    const evidence = verified.evidence;
    const archivePaths = verified.archivePaths;
    assertOriginalRecoveryEvidence({ plan, evidence });
    validateBootstrapRecoveryEvidence({
      contract,
      plan,
      evidence,
      recoveryEvidence,
      github,
    });
    assert.equal(
      await identifyPublisher({ registry: contract.registry }),
      contract.maintainerApproval.bootstrapIdentity,
      "authenticated npm identity differs from the approved bootstrap identity",
    );

    for (const role of plan.publishedRoles) {
      const candidate = evidence.packages[role];
      assertExactPublishedMetadata(
        await inspectRegistry({
          coordinate: candidate.coordinate,
          registry: contract.registry,
          candidate,
        }),
        candidate,
      );
      await verifyExistingPackage({
        role,
        contract,
        evidence,
        candidate,
        expected: recoveryEvidence.expectedProvenance[role],
      });
    }
    for (const role of recoveryPublishOrder) {
      const candidate = evidence.packages[role];
      assert.equal(
        await inspectRegistry({
          coordinate: candidate.coordinate,
          registry: contract.registry,
          candidate,
        }),
        null,
        `${candidate.coordinate} unexpectedly exists; stop recovery without publishing`,
      );
    }

    const published = [];
    for (const role of recoveryPublishOrder) {
      const candidate = evidence.packages[role];
      try {
        await publishArchive({
          role,
          archivePath: archivePaths[role],
          contract,
          candidate,
        });
      } catch (error) {
        try {
          await reconcilePublishedCandidate({
            candidate,
            registry: contract.registry,
            inspectRegistry,
            visibilityAttempts,
            visibilityDelayMilliseconds,
            waitForVisibility,
          });
        } catch (reconciliationError) {
          throw new Error(
            `recovery publish command failed for ${candidate.coordinate}; outcome is indeterminate because exact-version reconciliation failed (${reconciliationError.message}); previously confirmed recovery publications: ${published.join(", ") || "none"}; do not continue`,
            { cause: reconciliationError },
          );
        }
        published.push(candidate.coordinate);
        throw new Error(
          `recovery publish command failed for ${candidate.coordinate}, but exact-version reconciliation confirmed the expected bytes; confirmed recovery publications: ${published.join(", ")}; stop before continuing`,
          { cause: error },
        );
      }
      published.push(candidate.coordinate);
      try {
        await reconcilePublishedCandidate({
          candidate,
          registry: contract.registry,
          inspectRegistry,
          visibilityAttempts,
          visibilityDelayMilliseconds,
          waitForVisibility,
        });
      } catch (error) {
        throw new Error(
          `recovery publication completed for ${candidate.coordinate}, but exact-version verification failed (${error.message}); confirmed recovery publish commands: ${published.join(", ")}; stop before continuing`,
          { cause: error },
        );
      }
    }
    return { kind: "frontend-bootstrap-recovery-publication", published };
  } finally {
    await verified.dispose();
  }
}

async function loadJson(selectedPath) {
  return JSON.parse(await readFile(path.resolve(selectedPath), "utf8"));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const mode = optionValue("--mode");
  const contractPath = optionValue("--contract");
  const planPath = optionValue("--plan");
  const evidencePath = optionValue("--evidence");
  const archiveRoot = optionValue("--archive-root");
  const artifactZipPath = optionValue("--artifact-zip");
  const artifactMetadataPath = optionValue("--artifact-metadata");
  assert(
    ["prepare", "publish"].includes(mode),
    "--mode prepare|publish is required",
  );
  assert(contractPath, "--contract is required");
  assert(planPath, "--plan is required");
  assert(artifactZipPath, "--artifact-zip is required");
  assert(artifactMetadataPath, "--artifact-metadata is required");
  const common = {
    contract: await loadReleaseContract(contractPath),
    plan: await loadJson(planPath),
    evidence: evidencePath ? await loadJson(evidencePath) : undefined,
    archiveRoot,
    artifactZipPath,
    artifactMetadata: await loadJson(artifactMetadataPath),
    github: githubEnvironment(),
  };
  if (mode === "prepare") {
    const materializeRoot = optionValue("--materialize-root");
    const output = optionValue("--output");
    assert(materializeRoot, "--materialize-root is required");
    assert(output, "--output is required");
    const result = await prepareBootstrapRecovery({
      ...common,
      materializeRoot,
    });
    await writeFile(
      path.resolve(output),
      `${JSON.stringify(result, null, 2)}\n`,
    );
    process.stdout.write(`prepared recovery evidence at ${output}\n`);
  } else {
    assert(evidencePath, "--evidence is required for publication");
    assert(archiveRoot, "--archive-root is required for publication");
    const recoveryEvidencePath = optionValue("--recovery-evidence");
    assert(recoveryEvidencePath, "--recovery-evidence is required");
    const result = await publishBootstrapRecovery({
      ...common,
      recoveryEvidence: await loadJson(recoveryEvidencePath),
    });
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  }
}
