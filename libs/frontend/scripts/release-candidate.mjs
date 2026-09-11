import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { packDesignTokens } from "./pack-design-tokens.mjs";
import { packIframeSdk } from "./pack-iframe-sdk.mjs";
import { packUi } from "./pack-ui.mjs";
import { runBrowserSmoke } from "./browser-smoke.mjs";
import { runIframeSdkHostIntegration } from "./iframe-sdk-host-integration.mjs";
import { stageIsolatedConsumer } from "./isolated-consumer.mjs";
import { stageIsolatedIframeSdkConsumer } from "./isolated-iframe-sdk-consumer.mjs";
import { stageIsolatedReactConsumer } from "./isolated-react-consumer.mjs";
import { run } from "./process.mjs";
import {
  assertReleaseToolchain,
  loadReleaseContract,
  validateReleaseContract,
  workspaceRoot,
} from "./release-contract.mjs";
import {
  createCandidateEvidence,
  sha512Integrity,
  verifyCandidateEvidence,
} from "./release-evidence.mjs";

async function runCandidateGates({ contract, archivePaths, integrities }) {
  const tokens = await stageIsolatedConsumer({
    contract,
    archivePath: archivePaths.designTokens,
    expectedIntegrity: integrities.designTokens,
    stagedOutputPath: "target/staged-consumers/tokens",
  });
  const ui = await stageIsolatedReactConsumer({
    contract,
    tokenArchivePath: archivePaths.designTokens,
    uiArchivePath: archivePaths.ui,
    expectedIntegrities: integrities,
    stagedOutputPath: "target/staged-consumers/react",
  });
  const iframeSdk = await stageIsolatedIframeSdkConsumer({
    contract,
    archivePath: archivePaths.iframeSdk,
    expectedIntegrity: integrities.iframeSdk,
    stagedOutputPath: "target/staged-consumers/iframe-sdk",
  });
  const host = await runIframeSdkHostIntegration({
    contract,
    archivePath: archivePaths.iframeSdk,
    expectedIntegrity: integrities.iframeSdk,
  });
  const browser = await runBrowserSmoke();
  return {
    archives: { validated: true, reusedPackedBytes: true },
    consumers: {
      designTokens: tokens.evidence,
      ui: ui.evidence,
      iframeSdk,
    },
    host,
    browser,
  };
}

export async function buildReleaseCandidate({
  contract,
  sourceCommit,
  clean,
  producerToolchain,
  applicationToolchain,
  approved = false,
  runGates = runCandidateGates,
  packers = {
    designTokens: packDesignTokens,
    ui: packUi,
    iframeSdk: packIframeSdk,
  },
}) {
  validateReleaseContract(contract);
  assert.equal(clean, true, "release candidate requires a clean checkout");
  assertReleaseToolchain(contract, producerToolchain);
  if (approved)
    assert.equal(
      contract.state,
      "maintainer-confirmed",
      "approved candidate evidence requires a maintainer-confirmed contract",
    );
  const archives = [];
  for (const role of ["designTokens", "iframeSdk", "ui"]) {
    const result = await packers[role]({ contract, validate: true });
    archives.push({ role, path: result.archivePath });
  }
  const archivePaths = Object.fromEntries(
    archives.map(({ role, path: archivePath }) => [role, archivePath]),
  );
  const integrities = Object.fromEntries(
    await Promise.all(
      archives.map(async ({ role, path: archivePath }) => [
        role,
        await sha512Integrity(archivePath),
      ]),
    ),
  );
  const gates = await runGates({ contract, archivePaths, integrities });
  for (const role of Object.keys(archivePaths))
    assert.equal(
      await sha512Integrity(archivePaths[role]),
      integrities[role],
      `${role} archive changed during candidate validation`,
    );
  const evidence = await createCandidateEvidence({
    contract,
    archives,
    sourceCommit,
    producerToolchain,
    applicationToolchain,
    gates,
    approved,
  });
  await verifyCandidateEvidence(evidence, archivePaths, { contract });
  return { archives, evidence };
}

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const contract = await loadReleaseContract(optionValue("--contract"));
  const approved = process.argv.includes("--approved");
  const [{ stdout: status }, { stdout: sourceCommit }, { stdout: npmVersion }] =
    await Promise.all([
      run("git", ["status", "--porcelain"], { cwd: workspaceRoot }),
      run("git", ["rev-parse", "HEAD"], { cwd: workspaceRoot }),
      run("npm", ["--version"], { cwd: workspaceRoot }),
    ]);
  const result = await buildReleaseCandidate({
    contract,
    sourceCommit: sourceCommit.trim(),
    clean: status.trim() === "",
    producerToolchain: {
      node: process.versions.node,
      npm: npmVersion.trim(),
    },
    applicationToolchain: {
      source: "apps/frontend/package-lock.json",
      isolation: "application-owned",
      node: process.versions.node,
      npm: npmVersion.trim(),
    },
    approved,
  });
  const evidencePath = path.resolve(
    workspaceRoot,
    optionValue("--evidence") ?? "target/release-evidence/candidate.json",
  );
  await mkdir(path.dirname(evidencePath), { recursive: true });
  await writeFile(
    evidencePath,
    `${JSON.stringify(result.evidence, null, 2)}\n`,
  );
  process.stdout.write(
    `${JSON.stringify({ evidencePath, ...result }, null, 2)}\n`,
  );
}
