import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { validateBootstrapRecoveryPlan } from "./bootstrap-recovery-contract.mjs";
import {
  assertExpectedManifest,
  assertProducerLockfile,
  loadReleaseContract,
  validateReleaseContract,
  workspaceRoot,
} from "./release-contract.mjs";

export function assertSelectedContractState(contract) {
  assert(
    ["proposed", "maintainer-confirmed"].includes(contract.state),
    "selected release contract must be proposed or maintainer-confirmed",
  );
  return contract;
}

export async function checkReleaseContracts() {
  const fixture = await loadReleaseContract();
  const selected = assertSelectedContractState(
    validateReleaseContract(
      JSON.parse(
        await readFile(
          path.join(workspaceRoot, "release/proposed-release-contract.json"),
          "utf8",
        ),
      ),
    ),
  );
  const recoveryPlan = validateBootstrapRecoveryPlan(
    JSON.parse(
      await readFile(
        path.join(workspaceRoot, "release/bootstrap-recovery.json"),
        "utf8",
      ),
    ),
  );
  assert.equal(fixture.state, "fixture");
  const rootManifest = JSON.parse(
    await readFile(path.join(workspaceRoot, "package.json"), "utf8"),
  );
  const lockfile = JSON.parse(
    await readFile(path.join(workspaceRoot, "package-lock.json"), "utf8"),
  );
  for (const expected of Object.values(selected.packages)) {
    const manifest = JSON.parse(
      await readFile(
        path.join(workspaceRoot, expected.workspace, "package.json"),
        "utf8",
      ),
    );
    assertExpectedManifest(manifest, expected);
  }
  await assertProducerLockfile({
    contract: selected,
    rootManifest,
    lockfile,
    root: workspaceRoot,
  });
  return {
    kind: "release-contract-tooling",
    contracts: [fixture.state, selected.state],
    producerMembers: Object.keys(selected.packages),
    recoveryPlan: recoveryPlan.state,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await checkReleaseContracts(), null, 2)}\n`,
  );
}
