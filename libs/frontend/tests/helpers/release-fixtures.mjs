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

import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { loadCompatibilityLedger } from "../../scripts/compatibility-baselines.mjs";

// Exercise historical-token scenarios independently of the current UI peer range.
export async function withCompatibleTokenBaseline(contract) {
  const fixture = structuredClone(contract);
  const ledger = await loadCompatibilityLedger();
  const baseline = ledger.baselines.find(
    ({ memberId }) => memberId === "designTokens",
  );
  const version = baseline.coordinate.slice(
    baseline.coordinate.lastIndexOf("@") + 1,
  );
  fixture.packages.ui.expectedManifest.peerDependencies[
    fixture.packages.designTokens.name
  ] += ` || ${version}`;
  return fixture;
}

// Simulated release gates must not depend on approval of the working-tree release.
export async function changelogFixture(context, contract) {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "fred-release-changelogs-"),
  );
  context.after(() => rm(root, { recursive: true, force: true }));
  for (const { id, workspace } of contract.inventory.members) {
    await mkdir(path.join(root, workspace));
    await writeFile(
      path.join(root, workspace, "CHANGELOG.md"),
      `## ${contract.packages[id].version}\nReview: approved\nChanges: Disposable release test fixture.\n`,
    );
  }
  return root;
}
