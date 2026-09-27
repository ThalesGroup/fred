// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  assertExpectedManifest,
  assertProducerLockfile,
  loadReleaseContract,
  workspaceRoot,
} from "./release-contract.mjs";
import { assertMemberChangelog } from "./release-changelog.mjs";
import {
  baselineDigest,
  loadCompatibilityLedger,
} from "./compatibility-baselines.mjs";

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
    await loadReleaseContract(
      path.join(workspaceRoot, "release/proposed-release-contract.json"),
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
  for (const member of selected.inventory.members)
    await assertMemberChangelog(
      workspaceRoot,
      member,
      selected.packages[member.id].version,
    );
  assert.equal(
    baselineDigest(await loadCompatibilityLedger()),
    selected.approvedBaselineDigest,
    "reviewed baseline differs from release policy",
  );
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
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await checkReleaseContracts(), null, 2)}\n`,
  );
}
