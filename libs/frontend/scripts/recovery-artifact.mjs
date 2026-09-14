import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  constants,
  copyFile,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { assertNoArchiveLinks, listArchiveFiles } from "./archive-safety.mjs";
import {
  fixtureArchiveFilename,
  validateFixtureTransferMetadata,
} from "./fixture-transfer.mjs";
import { run } from "./process.mjs";
import { packageRoles } from "./release-contract.mjs";
import {
  releaseContractDigest,
  verifyCandidateEvidence,
} from "./release-evidence.mjs";

export const recoveryCandidateEvidenceFilename = "candidate-evidence.json";
export const recoveryTransferMetadataFilename = "candidate-transfer.json";
export const recoveryArtifactZipFilename = "original-release-artifact.zip";
export const recoveryArtifactMetadataFilename =
  "original-artifact-metadata.json";

function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function sha256Integrity(bytes) {
  return `sha256-${createHash("sha256").update(bytes).digest("base64")}`;
}

async function assertRegularFile(filePath, label) {
  const stats = await lstat(filePath);
  assert(
    stats.isFile() && !stats.isSymbolicLink(),
    `${label} must be a regular non-symlink file`,
  );
  return stats;
}

function expectedCandidateFiles(contract) {
  return [
    recoveryCandidateEvidenceFilename,
    recoveryTransferMetadataFilename,
    ...packageRoles.map((role) => {
      const selected = contract.packages[role];
      return fixtureArchiveFilename(selected.name, selected.version);
    }),
  ].sort();
}

function assertZipEntryModes(listing, expectedFiles) {
  const entries = listing
    .split("\n")
    .filter((line) => /^[-dlcbps][rwxStTs-]{9}\s/.test(line))
    .map((line) => ({ mode: line[0], name: line.trim().split(/\s+/).at(-1) }));
  assert.deepEqual(
    entries.map(({ name }) => name).sort(),
    expectedFiles,
    "recovery ZIP detailed entry set differs",
  );
  for (const entry of entries)
    assert.equal(
      entry.mode,
      "-",
      `recovery ZIP entry must not be a link or special file: ${entry.name}`,
    );
}

function originalTransferExecution(plan, transfer) {
  return {
    provider: "github-actions",
    repository: plan.recoveryExecution.repository,
    workflow: transfer.execution?.workflow,
    runId: plan.incident.workflowRunId,
    runAttempt: plan.incident.workflowRunAttempt,
  };
}

async function compareTransferredCandidate({
  transferredRoot,
  expectedFiles,
  extractedRoot,
  transferredEvidence,
  originalEvidence,
}) {
  if (!transferredRoot && !transferredEvidence) return;
  assert(transferredRoot, "transferred candidate root is required");
  const root = path.resolve(transferredRoot);
  const rootStats = await lstat(root);
  assert(
    rootStats.isDirectory() && !rootStats.isSymbolicLink(),
    "transferred candidate root must be a regular non-symlink directory",
  );
  const candidateFiles = (await readdir(root))
    .filter(
      (entry) =>
        entry.endsWith(".tgz") ||
        entry === recoveryCandidateEvidenceFilename ||
        entry === recoveryTransferMetadataFilename,
    )
    .sort();
  assert.deepEqual(
    candidateFiles,
    expectedFiles,
    "transferred candidate copy set differs from the pinned original artifact",
  );
  for (const filename of expectedFiles) {
    await assertRegularFile(
      path.join(root, filename),
      `transferred candidate ${filename}`,
    );
    const [transferred, original] = await Promise.all([
      readFile(path.join(root, filename)),
      readFile(path.join(extractedRoot, filename)),
    ]);
    assert.equal(
      sha256Hex(transferred),
      sha256Hex(original),
      `${filename} candidate copy differs from the pinned original artifact`,
    );
  }
  if (transferredEvidence)
    assert.deepEqual(
      transferredEvidence,
      originalEvidence,
      "candidate evidence copy differs from the pinned original artifact",
    );
}

export async function verifyOriginalRecoveryArtifact({
  artifactZipPath,
  contract,
  plan,
  transferredRoot,
  transferredEvidence,
  runCommand = run,
}) {
  assert(artifactZipPath, "original recovery artifact ZIP is required");
  const zipPath = path.resolve(artifactZipPath);
  await assertRegularFile(zipPath, "original recovery artifact ZIP");
  const zipBytes = await readFile(zipPath);
  assert.equal(
    sha256Hex(zipBytes),
    plan.incident.artifactZipSha256,
    "original recovery artifact ZIP digest differs",
  );
  const expectedFiles = expectedCandidateFiles(contract);
  const [{ stdout: names }, { stdout: details }] = await Promise.all([
    runCommand("unzip", ["-Z1", zipPath]),
    runCommand("unzip", ["-Z", "-l", zipPath]),
  ]);
  assert.deepEqual(
    names.split("\n").filter(Boolean).sort(),
    expectedFiles,
    "recovery ZIP candidate file set differs",
  );
  assertZipEntryModes(details, expectedFiles);

  const extractedRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-bootstrap-recovery-artifact-"),
  );
  try {
    await runCommand("unzip", ["-qq", zipPath, "-d", extractedRoot]);
    const extractedFiles = await listArchiveFiles(extractedRoot);
    assert.deepEqual(
      extractedFiles,
      expectedFiles,
      "recovery ZIP extracted file set differs",
    );
    await assertNoArchiveLinks(extractedRoot, extractedFiles);
    for (const filename of extractedFiles)
      await assertRegularFile(
        path.join(extractedRoot, filename),
        `recovery artifact ${filename}`,
      );

    const [evidence, transfer] = await Promise.all([
      readFile(
        path.join(extractedRoot, recoveryCandidateEvidenceFilename),
        "utf8",
      ).then(JSON.parse),
      readFile(
        path.join(extractedRoot, recoveryTransferMetadataFilename),
        "utf8",
      ).then(JSON.parse),
    ]);
    const execution = originalTransferExecution(plan, transfer);
    validateFixtureTransferMetadata(transfer, {
      contract,
      sourceCommit: plan.incident.sourceCommit,
      sourceTreeClean: true,
      execution,
    });
    assert.equal(
      evidence.contractDigest,
      releaseContractDigest(contract),
      "original candidate contract differs",
    );
    assert.equal(
      evidence.transfer?.metadataDigest,
      sha256Integrity(
        await readFile(
          path.join(extractedRoot, recoveryTransferMetadataFilename),
        ),
      ),
      "original candidate transfer metadata digest differs",
    );
    assert.equal(
      evidence.transfer?.metadataFilename,
      recoveryTransferMetadataFilename,
    );
    assert.equal(evidence.transfer?.artifactName, transfer.artifactName);
    assert.deepEqual(evidence.transfer?.execution, transfer.execution);

    const archivePaths = Object.fromEntries(
      packageRoles.map((role) => [
        role,
        path.join(extractedRoot, transfer.packages[role].filename),
      ]),
    );
    await verifyCandidateEvidence(evidence, archivePaths, { contract });
    for (const role of packageRoles) {
      const candidate = evidence.packages[role];
      const record = transfer.packages[role];
      assert.deepEqual(
        {
          coordinate: candidate.coordinate,
          filename: candidate.filename,
          bytes: candidate.bytes,
          integrity: candidate.integrity,
        },
        {
          coordinate: record.coordinate,
          filename: record.filename,
          bytes: record.bytes,
          integrity: record.integrity,
        },
        `${role} candidate evidence differs from original transfer metadata`,
      );
    }
    await compareTransferredCandidate({
      transferredRoot,
      expectedFiles,
      extractedRoot,
      transferredEvidence,
      originalEvidence: evidence,
    });
    return {
      root: extractedRoot,
      evidence,
      transfer,
      archivePaths,
      expectedFiles,
      dispose: () => rm(extractedRoot, { recursive: true, force: true }),
    };
  } catch (error) {
    await rm(extractedRoot, { recursive: true, force: true });
    throw error;
  }
}

export async function materializeVerifiedRecoveryArtifact({
  verified,
  artifactZipPath,
  artifactMetadata,
  outputRoot,
}) {
  assert(outputRoot, "recovery materialization root is required");
  const root = path.resolve(outputRoot);
  await mkdir(root, { recursive: true });
  const rootStats = await lstat(root);
  assert(
    rootStats.isDirectory() && !rootStats.isSymbolicLink(),
    "recovery materialization root must be a regular non-symlink directory",
  );
  assert.deepEqual(
    await readdir(root),
    [],
    "recovery materialization root must be empty",
  );
  for (const filename of verified.expectedFiles)
    await copyFile(
      path.join(verified.root, filename),
      path.join(root, filename),
      constants.COPYFILE_EXCL,
    );
  await copyFile(
    path.resolve(artifactZipPath),
    path.join(root, recoveryArtifactZipFilename),
    constants.COPYFILE_EXCL,
  );
  const metadataPath = path.join(root, recoveryArtifactMetadataFilename);
  await writeFile(
    metadataPath,
    `${JSON.stringify(artifactMetadata, null, 2)}\n`,
    {
      flag: "wx",
    },
  );
  return root;
}
