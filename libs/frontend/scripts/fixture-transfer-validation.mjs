import assert from "node:assert/strict";
import { mkdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { runBrowserSmoke } from "./browser-smoke.mjs";
import {
  fixtureArtifactName,
  fixtureExecution,
  verifyFixtureTransfer,
} from "./fixture-transfer.mjs";
import { runIframeSdkHostIntegration } from "./iframe-sdk-host-integration.mjs";
import { stageIsolatedConsumer } from "./isolated-consumer.mjs";
import { stageIsolatedIframeSdkConsumer } from "./isolated-iframe-sdk-consumer.mjs";
import { stageIsolatedReactConsumer } from "./isolated-react-consumer.mjs";
import { run } from "./process.mjs";
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
  await rm(outputPath, { force: true });
  await rm(temporaryPath, { force: true });
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
  });
  assert.equal(evidence.kind, "fixture-candidate-evidence");
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
    artifactName: fixtureArtifactName({ sourceCommit, ...execution }),
    metadataFilename: path.basename(verified.metadataPath),
    metadataDigest: verified.metadataDigest,
    sourceTreeClean,
    execution,
  };
  await verifyCandidateEvidence(evidence, verified.archivePaths, { contract });
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(temporaryPath, `${JSON.stringify(evidence, null, 2)}\n`);
  await rename(temporaryPath, outputPath);
  return { evidence, evidencePath: outputPath, ...verified };
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
    `${JSON.stringify({ evidencePath: result.evidencePath, kind: result.evidence.kind }, null, 2)}\n`,
  );
}
