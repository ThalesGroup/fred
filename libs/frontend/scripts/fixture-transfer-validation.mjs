import assert from "node:assert/strict";
import { mkdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { runBrowserSmoke } from "./browser-smoke.mjs";
import {
  archiveTransferArtifactName,
  fixtureExecution,
  verifyFixtureTransfer,
} from "./fixture-transfer.mjs";
import { runIframeSdkHostIntegration } from "./iframe-sdk-host-integration.mjs";
import { stageIsolatedConsumer } from "./isolated-consumer.mjs";
import { stageIsolatedIframeSdkConsumer } from "./isolated-iframe-sdk-consumer.mjs";
import { stageIsolatedReactConsumer } from "./isolated-react-consumer.mjs";
import { run } from "./process.mjs";
import { loadCompatibilityLedger } from "./compatibility-baselines.mjs";
import {
  candidateRecordFromEvidence,
  validateReleaseRecord,
} from "./release-record.mjs";
import {
  loadReleaseContract,
  packageRoles,
  workspaceRoot,
} from "./release-contract.mjs";
import {
  assertApplicationToolchain,
  createCandidateEvidence,
  verifyCandidateEvidence,
} from "./release-evidence.mjs";

async function runTransferredGates({
  contract,
  archivePaths,
  integrities,
  stageRoot,
}) {
  const tokenOutput = path.join(stageRoot, "tokens");
  const reactOutput = path.join(stageRoot, "react");
  const iframeSdkOutput = path.join(stageRoot, "iframe-sdk");
  const tokens = await stageIsolatedConsumer({
    contract,
    archivePath: archivePaths.designTokens,
    expectedIntegrity: integrities.designTokens,
    stagedOutputPath: tokenOutput,
  });
  const ui = await stageIsolatedReactConsumer({
    contract,
    tokenArchivePath: archivePaths.designTokens,
    uiArchivePath: archivePaths.ui,
    expectedIntegrities: integrities,
    stagedOutputPath: reactOutput,
  });
  const iframeSdk = await stageIsolatedIframeSdkConsumer({
    contract,
    archivePath: archivePaths.iframeSdk,
    expectedIntegrity: integrities.iframeSdk,
    stagedOutputPath: iframeSdkOutput,
  });
  const host = await runIframeSdkHostIntegration({
    contract,
    archivePath: archivePaths.iframeSdk,
    expectedIntegrity: integrities.iframeSdk,
  });
  const browser = await runBrowserSmoke({
    tokenOutput,
    reactOutput,
    iframeSdkOutput,
  });
  return {
    archives: { validated: true, reusedPackedBytes: true },
    consumers: {
      designTokens: tokens.evidence,
      ui: ui.evidence,
      iframeSdk,
    },
    browser,
    host,
  };
}

export async function persistCandidatePair({
  evidencePath,
  recordPath,
  evidence,
  record,
  renameFile = rename,
}) {
  const temporaryEvidencePath = `${evidencePath}.tmp`;
  const temporaryRecordPath = `${recordPath}.tmp`;
  try {
    await writeFile(
      temporaryRecordPath,
      `${JSON.stringify(record, null, 2)}\n`,
    );
    await writeFile(
      temporaryEvidencePath,
      `${JSON.stringify(evidence, null, 2)}\n`,
    );
    await renameFile(temporaryRecordPath, recordPath);
    await renameFile(temporaryEvidencePath, evidencePath);
  } catch (error) {
    // A complete record must never survive without its matching final evidence.
    await Promise.allSettled(
      [
        recordPath,
        evidencePath,
        temporaryRecordPath,
        temporaryEvidencePath,
      ].map((file) => rm(file, { force: true })),
    );
    throw error;
  }
}

export async function validateTransferredFixture({
  transferRoot,
  evidencePath,
  stageRoot,
  contract,
  sourceCommit,
  sourceTreeClean,
  execution,
  applicationToolchain,
  runGates = runTransferredGates,
}) {
  const outputPath = path.resolve(evidencePath);
  const temporaryPath = `${outputPath}.tmp`;
  const recordPath = path.join(
    path.dirname(outputPath),
    "candidate-record.json",
  );
  const temporaryRecordPath = `${recordPath}.tmp`;
  await rm(outputPath, { force: true });
  await rm(temporaryPath, { force: true });
  await rm(recordPath, { force: true });
  await rm(temporaryRecordPath, { force: true });
  assertApplicationToolchain(applicationToolchain);
  const verified = await verifyFixtureTransfer({
    transferRoot,
    contract,
    sourceCommit,
    sourceTreeClean,
    execution,
  });
  const gates = await runGates({
    contract,
    archivePaths: verified.archivePaths,
    integrities: verified.integrities,
    stageRoot: path.resolve(stageRoot),
  });
  const afterGates = await verifyFixtureTransfer({
    transferRoot,
    contract,
    sourceCommit,
    sourceTreeClean,
    execution,
  });
  assert.equal(
    afterGates.metadataDigest,
    verified.metadataDigest,
    "fixture transfer metadata changed during downstream validation",
  );
  assert.deepEqual(
    afterGates.integrities,
    verified.integrities,
    "fixture transfer archives changed during downstream validation",
  );
  const archives = packageRoles.map((role) => ({
    role,
    path: verified.archivePaths[role],
  }));
  const evidence = await createCandidateEvidence({
    contract,
    archives,
    sourceCommit,
    producerToolchain: verified.metadata.producerToolchain,
    applicationToolchain,
    gates,
    approved: contract.state === "maintainer-confirmed",
  });
  assert.equal(
    evidence.kind,
    contract.state === "maintainer-confirmed"
      ? "release-candidate-evidence"
      : "fixture-candidate-evidence",
  );
  for (const role of packageRoles) {
    const transferRecord = verified.metadata.packages[role];
    assert.deepEqual(
      {
        coordinate: evidence.packages[role].coordinate,
        filename: evidence.packages[role].filename,
        bytes: evidence.packages[role].bytes,
        integrity: evidence.packages[role].integrity,
      },
      {
        coordinate: transferRecord.coordinate,
        filename: transferRecord.filename,
        bytes: transferRecord.bytes,
        integrity: transferRecord.integrity,
      },
      `${role} final evidence differs from fixture transfer`,
    );
  }
  evidence.transfer = {
    kind: verified.metadata.kind,
    artifactName: archiveTransferArtifactName({
      contractState: contract.state,
      sourceCommit,
      ...execution,
    }),
    metadataFilename: path.basename(verified.metadataPath),
    metadataDigest: verified.metadataDigest,
    sourceTreeClean,
    execution,
  };
  await verifyCandidateEvidence(evidence, verified.archivePaths, { contract });
  const record = await candidateRecordFromEvidence({
    evidence,
    contract,
    ledger: await loadCompatibilityLedger(),
    archivePaths: verified.archivePaths,
  });
  if (runGates !== runTransferredGates && record.readiness === "complete")
    record.readiness = "incomplete"; // Controlled injected gates do not claim real browser/host evidence.
  validateReleaseRecord(record);
  await mkdir(path.dirname(outputPath), { recursive: true });
  await persistCandidatePair({
    evidencePath: outputPath,
    recordPath,
    evidence,
    record,
  });
  return {
    evidence,
    evidencePath: outputPath,
    record,
    recordPath,
    ...verified,
  };
}

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function cliExecution() {
  const github = Boolean(process.env.GITHUB_ACTIONS);
  return fixtureExecution({
    provider: github ? "github-actions" : "local-rehearsal",
    repository:
      optionValue("--repository") ??
      process.env.GITHUB_REPOSITORY ??
      "local/fred",
    workflow:
      optionValue("--workflow") ??
      process.env.GITHUB_WORKFLOW ??
      "local-fixture-transfer",
    runId: optionValue("--run-id") ?? process.env.GITHUB_RUN_ID,
    runAttempt: optionValue("--run-attempt") ?? process.env.GITHUB_RUN_ATTEMPT,
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const transferRoot = optionValue("--transfer");
  const evidencePath = optionValue("--evidence");
  const stageRoot = optionValue("--stage-root");
  assert(transferRoot, "--transfer is required");
  assert(evidencePath, "--evidence is required");
  assert(stageRoot, "--stage-root is required");
  const contract = await loadReleaseContract(optionValue("--contract"));
  const approved = process.argv.includes("--approved");
  assert.equal(
    approved,
    contract.state === "maintainer-confirmed",
    approved
      ? "approved transfer validation requires a maintainer-confirmed contract"
      : "maintainer-confirmed transfer validation requires --approved",
  );
  const [{ stdout: status }, { stdout: commit }, { stdout: npmVersion }] =
    await Promise.all([
      run("git", ["status", "--porcelain"], { cwd: workspaceRoot }),
      run("git", ["rev-parse", "HEAD"], { cwd: workspaceRoot }),
      run("npm", ["--version"], { cwd: workspaceRoot }),
    ]);
  const result = await validateTransferredFixture({
    transferRoot,
    evidencePath,
    stageRoot,
    contract,
    sourceCommit: commit.trim(),
    sourceTreeClean: status.trim() === "",
    execution: cliExecution(),
    applicationToolchain: {
      source: "apps/frontend/package-lock.json",
      isolation: "application-owned",
      node: process.versions.node,
      npm: npmVersion.trim(),
    },
  });
  process.stdout.write(
    `${JSON.stringify(
      {
        evidencePath: result.evidencePath,
        recordPath: result.recordPath,
        kind: result.evidence.kind,
        recordReadiness: result.record.readiness,
      },
      null,
      2,
    )}\n`,
  );
}
