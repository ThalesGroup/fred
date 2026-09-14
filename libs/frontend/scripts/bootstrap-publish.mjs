import assert from "node:assert/strict";
import { lstat, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { run } from "./process.mjs";
import {
  assertMaintainerConfirmed,
  loadReleaseContract,
  packageRoles,
} from "./release-contract.mjs";
import { verifyCandidateEvidence } from "./release-evidence.mjs";
import {
  assertExactPublishedMetadata,
  fetchExactPackageMetadata,
} from "./registry-metadata.mjs";

export { assertExactPublishedMetadata } from "./registry-metadata.mjs";

const publishOrder = ["designTokens", "ui", "iframeSdk"];
const candidateTransferMetadataFilename = "candidate-transfer.json";
const defaultVisibilityAttempts = 6;
const defaultVisibilityDelayMilliseconds = 5_000;

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function expectedWorkflowRef(contract) {
  const workflow = new URL(contract.expectedProvenance.workflow);
  return `${workflow.pathname.slice(1)}${workflow.hash}`;
}

export function assertBootstrapWorkflowIdentity({
  contract,
  evidence,
  github,
}) {
  assert.equal(
    github.actions,
    "true",
    "bootstrap publication requires GitHub Actions",
  );
  assert.equal(
    github.repository,
    "ThalesGroup/fred",
    "publishing repository differs",
  );
  assert.equal(
    github.ref,
    "refs/heads/swift",
    "bootstrap publication requires swift",
  );
  assert.equal(
    github.sha,
    evidence.sourceCommit,
    "publishing commit differs from evidence",
  );
  assert.equal(
    github.workflowRef,
    expectedWorkflowRef(contract),
    "publishing workflow identity differs from release contract",
  );
  const expectedExecution = {
    provider: "github-actions",
    repository: github.repository,
    workflow: github.workflow,
    runId: github.runId,
    runAttempt: github.runAttempt,
  };
  assert.deepEqual(
    evidence.transfer?.execution,
    expectedExecution,
    "candidate transfer does not belong to this workflow run",
  );
  assert.equal(
    evidence.transfer?.kind,
    "release-candidate-archive-transfer",
    "bootstrap publication requires an approved candidate transfer",
  );
  assert.equal(
    evidence.transfer?.metadataFilename,
    candidateTransferMetadataFilename,
    "candidate transfer metadata filename differs",
  );
  assert.match(
    evidence.transfer?.metadataDigest ?? "",
    /^sha256-[A-Za-z0-9+/]+={0,2}$/,
    "candidate transfer metadata digest is invalid",
  );
  assert.equal(
    evidence.transfer?.sourceTreeClean,
    true,
    "bootstrap publication requires a clean candidate source tree",
  );
  assert.equal(
    evidence.transfer?.artifactName,
    `frontend-packages-candidate-${evidence.sourceCommit}-${github.runId}-${github.runAttempt}`,
    "candidate artifact identity differs from this workflow run",
  );
}

async function archivePathsFromEvidence(archiveRoot, evidence) {
  const root = path.resolve(archiveRoot);
  const archivePaths = {};
  for (const role of packageRoles) {
    const filename = evidence.packages?.[role]?.filename;
    assert(
      filename && path.basename(filename) === filename,
      `${role} filename is invalid`,
    );
    const archivePath = path.resolve(root, filename);
    const relative = path.relative(root, archivePath);
    assert(
      relative && !relative.startsWith("..") && !path.isAbsolute(relative),
      `${role} archive escapes the candidate root`,
    );
    const stats = await lstat(archivePath);
    assert(
      !stats.isSymbolicLink() && stats.isFile(),
      `${role} archive must be a regular non-symlink file`,
    );
    archivePaths[role] = archivePath;
  }
  return archivePaths;
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

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function reconcilePublishedCandidate({
  candidate,
  registry,
  inspectRegistry,
  visibilityAttempts = defaultVisibilityAttempts,
  visibilityDelayMilliseconds = defaultVisibilityDelayMilliseconds,
  waitForVisibility = wait,
}) {
  assert(
    Number.isSafeInteger(visibilityAttempts) && visibilityAttempts > 0,
    "visibilityAttempts must be a positive integer",
  );
  for (let attempt = 1; attempt <= visibilityAttempts; attempt += 1) {
    const metadata = await inspectRegistry({
      coordinate: candidate.coordinate,
      registry,
      candidate,
    });
    if (metadata !== null)
      return assertExactPublishedMetadata(metadata, candidate);
    if (attempt < visibilityAttempts)
      await waitForVisibility(visibilityDelayMilliseconds);
  }
  throw new Error(
    `${candidate.coordinate} visibility retries exhausted after ${visibilityAttempts} exact-version reads`,
  );
}

export async function publishBootstrapRelease({
  contract,
  evidence,
  archiveRoot,
  github,
  identifyPublisher = npmIdentity,
  inspectRegistry = fetchExactPackageMetadata,
  publishArchive = npmPublish,
  visibilityAttempts = defaultVisibilityAttempts,
  visibilityDelayMilliseconds = defaultVisibilityDelayMilliseconds,
  waitForVisibility = wait,
}) {
  assertMaintainerConfirmed(contract);
  assert.equal(
    evidence.kind,
    "release-candidate-evidence",
    "bootstrap publication requires approved candidate evidence",
  );
  const archivePaths = await archivePathsFromEvidence(archiveRoot, evidence);
  await verifyCandidateEvidence(evidence, archivePaths, { contract });
  assertBootstrapWorkflowIdentity({ contract, evidence, github });
  assert.equal(
    await identifyPublisher({ registry: contract.registry }),
    contract.maintainerApproval.bootstrapIdentity,
    "authenticated npm identity differs from the approved bootstrap identity",
  );

  const existing = [];
  for (const role of publishOrder) {
    const candidate = evidence.packages[role];
    const metadata = await inspectRegistry({
      coordinate: candidate.coordinate,
      registry: contract.registry,
      candidate,
    });
    if (metadata) {
      assertExactPublishedMetadata(metadata, candidate);
      existing.push(candidate.coordinate);
    }
  }
  assert.equal(
    existing.length,
    0,
    `bootstrap versions already exist (${existing.join(", ")}); stop and verify the partial release before choosing an explicit recovery`,
  );

  const published = [];
  for (const role of publishOrder) {
    const candidate = evidence.packages[role];
    try {
      await publishArchive({
        role,
        archivePath: archivePaths[role],
        contract,
        candidate,
      });
    } catch (error) {
      let reconciliation;
      try {
        reconciliation = await reconcilePublishedCandidate({
          candidate,
          registry: contract.registry,
          inspectRegistry,
          visibilityAttempts,
          visibilityDelayMilliseconds,
          waitForVisibility,
        });
      } catch (reconciliationError) {
        throw new Error(
          `bootstrap publish command failed for ${candidate.coordinate}; outcome is indeterminate because exact-version registry reconciliation failed (${reconciliationError.message}); previously confirmed from this evidence: ${published.join(", ") || "no earlier coordinates"}; do not rebuild, overwrite, or continue until maintainers verify the registry`,
          { cause: reconciliationError },
        );
      }
      if (reconciliation) {
        published.push(candidate.coordinate);
        throw new Error(
          `bootstrap publish command failed for ${candidate.coordinate}, but registry reconciliation confirmed the expected archive bytes; confirmed published from this evidence: ${published.join(", ")}; stop before continuing and select an explicit recovery`,
          { cause: error },
        );
      }
      throw new Error(
        `bootstrap publish command failed for ${candidate.coordinate}; outcome is indeterminate and the registry did not confirm the expected archive bytes; previously confirmed from this evidence: ${published.join(", ") || "no earlier coordinates"}; do not rebuild, overwrite, or continue until maintainers verify the registry`,
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
        `bootstrap publication completed for ${candidate.coordinate}, but registry verification failed (${error.message}); confirmed publish commands from this evidence: ${published.join(", ")}; stop before continuing and verify the registry without rebuilding or overwriting`,
        { cause: error },
      );
    }
  }
  return { kind: "bootstrap-publication", published };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const contractPath = optionValue("--contract");
  const evidencePath = optionValue("--evidence");
  const archiveRoot = optionValue("--archive-root");
  assert(contractPath, "--contract is required");
  assert(evidencePath, "--evidence is required");
  assert(archiveRoot, "--archive-root is required");
  const result = await publishBootstrapRelease({
    contract: await loadReleaseContract(contractPath),
    evidence: JSON.parse(await readFile(path.resolve(evidencePath), "utf8")),
    archiveRoot,
    github: {
      actions: process.env.GITHUB_ACTIONS,
      repository: process.env.GITHUB_REPOSITORY,
      ref: process.env.GITHUB_REF,
      sha: process.env.GITHUB_SHA,
      workflowRef: process.env.GITHUB_WORKFLOW_REF,
      workflow: process.env.GITHUB_WORKFLOW,
      runId: process.env.GITHUB_RUN_ID,
      runAttempt: process.env.GITHUB_RUN_ATTEMPT,
    },
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}
