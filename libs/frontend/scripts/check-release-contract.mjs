import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  assertProducerLockfile,
  loadReleaseContract,
  validateReleaseContract,
  workspaceRoot,
} from "./release-contract.mjs";

export async function checkReleaseContracts() {
  const fixture = await loadReleaseContract();
  const proposed = validateReleaseContract(
    JSON.parse(
      await readFile(
        path.join(workspaceRoot, "release/proposed-release-contract.json"),
        "utf8",
      ),
    ),
  );
  assert.equal(fixture.state, "fixture");
  assert.equal(proposed.state, "proposed");
  const rootManifest = JSON.parse(
    await readFile(path.join(workspaceRoot, "package.json"), "utf8"),
  );
  const lockfile = JSON.parse(
    await readFile(path.join(workspaceRoot, "package-lock.json"), "utf8"),
  );
  await assertProducerLockfile({
    contract: fixture,
    rootManifest,
    lockfile,
    root: workspaceRoot,
  });
  return {
    kind: "release-contract-tooling",
    contracts: [fixture.state, proposed.state],
    producerMembers: Object.keys(fixture.packages),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await checkReleaseContracts(), null, 2)}\n`,
  );
}
