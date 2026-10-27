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
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const workspaceRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const defaultContractPath = path.join(
  workspaceRoot,
  "release/development-fixture-contract.json",
);
const exactToolVersionPattern = /^\d+\.\d+\.\d+$/;

export async function loadReleaseToolchain(contractPath = defaultContractPath) {
  const contract = JSON.parse(await readFile(contractPath, "utf8"));
  const toolchain = contract.releaseToolchain;
  assert.deepEqual(
    Object.keys(toolchain ?? {}).sort(),
    ["node", "npm"],
    "release toolchain keys",
  );
  for (const [name, version] of Object.entries(toolchain))
    assert.match(version, exactToolVersionPattern, `${name} must be exact`);
  return toolchain;
}

export function assertReleaseToolchain(expected, actual = process.versions) {
  const toolchain = expected.releaseToolchain ?? expected;
  const node = actual.node;
  const npm =
    actual.npm ?? process.env.npm_config_user_agent?.match(/npm\/([^ ]+)/)?.[1];
  assert.equal(node, toolchain.node, "release Node version differs");
  assert.equal(npm, toolchain.npm, "release npm version differs");
}
