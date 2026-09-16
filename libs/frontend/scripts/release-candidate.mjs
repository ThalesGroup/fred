import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { mkdir, realpath, writeFile } from "node:fs/promises";
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
import { loadCompatibilityLedger } from "./compatibility-baselines.mjs";
import { resolveUiTokenDependency } from "./compatibility-baselines.mjs";
import { assertCompatibleTokenProvision } from "./provision-compatible-token.mjs";
import { selectReleaseMembers, selectionOption } from "./release-selection.mjs";
import { candidateRecordFromEvidence } from "./release-record.mjs";
import { assertMemberChangelog } from "./release-changelog.mjs";

export async function runCandidateGates({
  contract,
  archivePaths,
  integrities,
  selectedIds,
  ledger,
  stageRoot = path.join(workspaceRoot, "target/staged-consumers"),
}) {
  const needsUiBaseline =
    selectedIds.includes("ui") && !selectedIds.includes("designTokens");
  const compatibleToken = needsUiBaseline
    ? await assertCompatibleTokenProvision({ contract, ledger })
    : undefined;
  const tokens =
    selectedIds.includes("designTokens") || needsUiBaseline
      ? await stageIsolatedConsumer({
          contract,
          archivePath:
            compatibleToken?.archivePath ?? archivePaths.designTokens,
          expectedIntegrity:
            compatibleToken?.receipt.integrity ?? integrities.designTokens,
          compatibleToken: compatibleToken
            ? {
                archivePath: compatibleToken.archivePath,
                coordinate: compatibleToken.receipt.coordinate,
                integrity: compatibleToken.receipt.integrity,
              }
            : undefined,
          stagedOutputPath: path.join(stageRoot, "tokens"),
        })
      : undefined;
  const ui = selectedIds.includes("ui")
    ? await stageIsolatedReactConsumer({
        contract,
        tokenArchivePath: archivePaths.designTokens,
        uiArchivePath: archivePaths.ui,
        expectedIntegrities: integrities,
        compatibleToken: compatibleToken
          ? {
              archivePath: compatibleToken.archivePath,
              coordinate: compatibleToken.receipt.coordinate,
              integrity: compatibleToken.receipt.integrity,
            }
          : undefined,
        stagedOutputPath: path.join(stageRoot, "react"),
      })
    : undefined;
  const iframeSdk = selectedIds.includes("iframeSdk")
    ? await stageIsolatedIframeSdkConsumer({
        contract,
        archivePath: archivePaths.iframeSdk,
        expectedIntegrity: integrities.iframeSdk,
        stagedOutputPath: path.join(stageRoot, "iframe-sdk"),
      })
    : undefined;
  const host = iframeSdk
    ? await runIframeSdkHostIntegration({
        contract,
        archivePath: archivePaths.iframeSdk,
        expectedIntegrity: integrities.iframeSdk,
      })
    : undefined;
  const browser = await runBrowserSmoke({
    tokenOutput: path.join(stageRoot, "tokens"),
    reactOutput: path.join(stageRoot, "react"),
    iframeSdkOutput: path.join(stageRoot, "iframe-sdk"),
    checks: [
      ...(tokens ? ["tokens", "fonts"] : []),
      ...(ui ? ["ui"] : []),
      ...(iframeSdk ? ["iframeSdk"] : []),
    ],
  });
  return {
    archives: { validated: true, reusedPackedBytes: true },
    consumers: {
      ...(selectedIds.includes("designTokens")
        ? { designTokens: tokens.evidence }
        : {}),
      ...(ui ? { ui: ui.evidence } : {}),
      ...(iframeSdk ? { iframeSdk } : {}),
    },
    ...(compatibleToken
      ? { compatibility: { designTokens: compatibleToken.receipt } }
      : {}),
    ...(host ? { host } : {}),
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
  root = workspaceRoot,
  runGates = runCandidateGates,
  packers = {
    designTokens: packDesignTokens,
    ui: packUi,
    iframeSdk: packIframeSdk,
  },
  selection,
}) {
  validateReleaseContract(contract);
  const selectedIds = selectReleaseMembers(contract, selection);
  const ledger = await loadCompatibilityLedger();
  if (selectedIds.includes("ui"))
    resolveUiTokenDependency({ contract, ledger, selectedIds });
  assert.equal(clean, true, "release candidate requires a clean checkout");
  assertReleaseToolchain(contract, producerToolchain);
  if (approved)
    assert.equal(
      contract.state,
      "maintainer-confirmed",
      "approved candidate evidence requires a maintainer-confirmed contract",
    );
  if (approved) {
    assert.equal(
      await realpath(root),
      await realpath(workspaceRoot),
      "approved candidate cannot use a disposable producer root",
    );
    assert.equal(
      runGates,
      runCandidateGates,
      "approved candidate requires the actual consumer/browser/host gates",
    );
    for (const [id, builder] of Object.entries({
      designTokens: packDesignTokens,
      ui: packUi,
      iframeSdk: packIframeSdk,
    }).filter(([id]) => selectedIds.includes(id)))
      assert.equal(
        packers[id],
        builder,
        `approved candidate requires the actual ${id} packer`,
      );
  }
  for (const member of contract.inventory.members.filter(({ id }) =>
    selectedIds.includes(id),
  ))
    await assertMemberChangelog(
      root,
      member,
      contract.packages[member.id].version,
    );
  const archives = [];
  for (const role of selectedIds) {
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
  const gates = await runGates({
    contract,
    archivePaths,
    integrities,
    selectedIds,
    ledger,
  });
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
  const record = await candidateRecordFromEvidence({
    evidence,
    contract,
    ledger,
    selectedIds,
    compatibilityOnly:
      selectedIds.includes("ui") && !selectedIds.includes("designTokens")
        ? ["designTokens"]
        : [],
    archivePaths,
  });
  return { archives, evidence, record };
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
    selection: selectionOption(),
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
  const recordPath = path.resolve(
    workspaceRoot,
    optionValue("--record") ?? "target/release-evidence/record.json",
  );
  await mkdir(path.dirname(recordPath), { recursive: true });
  await writeFile(recordPath, `${JSON.stringify(result.record, null, 2)}\n`);
  process.stdout.write(
    `${JSON.stringify({ evidencePath, recordPath, ...result }, null, 2)}\n`,
  );
}
