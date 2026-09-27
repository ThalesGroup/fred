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
import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { assertDocumentSchema } from "./schema-validation.mjs";

const schemaPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../release/package-inventory.schema.json",
);

const memberId = /^[a-z][A-Za-z0-9]*$/;
const workspaceName = /^[a-z0-9-]+$/;
// Profiles are reviewed as whole tuples. A package cannot borrow another member's gate.
// Registering a fourth member requires adding its specialized builder/validator/consumer here.
export const reviewedProfiles = {
  "design-tokens": {
    id: "designTokens",
    builder: "pack-design-tokens",
    validator: "design-tokens",
    consumer: "tokens",
  },
  ui: {
    id: "ui",
    builder: "pack-ui",
    validator: "ui",
    consumer: "react-browser",
  },
  "iframe-sdk": {
    id: "iframeSdk",
    builder: "pack-iframe-sdk",
    validator: "iframe-sdk",
    consumer: "iframe-browser-host",
  },
};

function exactKeys(value, keys, label) {
  assert(
    value && typeof value === "object" && !Array.isArray(value),
    `${label} must be an object`,
  );
  assert.deepEqual(
    Object.keys(value).sort(),
    [...keys].sort(),
    `${label} keys`,
  );
}

// The reviewed inventory describes identities and specialized gates, never manifest metadata.
export async function loadPackageInventory(filePath, options) {
  return validatePackageInventory(
    JSON.parse(await readFile(filePath, "utf8")),
    options,
  );
}

export function validatePackageInventory(
  inventory,
  { profiles = reviewedProfiles } = {},
) {
  assertDocumentSchema(inventory, schemaPath, "package inventory");
  exactKeys(inventory, ["$schema", "schemaVersion", "members"], "inventory");
  assert.equal(
    inventory.$schema,
    "./package-inventory.schema.json",
    "inventory schema reference differs",
  );
  assert.equal(inventory.schemaVersion, 1, "inventory schema version differs");
  assert(
    Array.isArray(inventory.members) && inventory.members.length > 0,
    "inventory members are required",
  );
  const ids = new Set();
  const workspaces = new Set();
  for (const member of inventory.members) {
    exactKeys(
      member,
      ["id", "workspace", "builder", "validator", "consumer"],
      "inventory member",
    );
    assert(memberId.test(member.id), `invalid inventory ID ${member.id}`);
    assert(
      workspaceName.test(member.workspace),
      `invalid inventory workspace ${member.workspace}`,
    );
    const profile = profiles[member.workspace];
    assert(profile, `unreviewed inventory workspace ${member.workspace}`);
    for (const field of ["id", "builder", "validator", "consumer"])
      assert.equal(
        member[field],
        profile[field],
        `${member.workspace} ${field} differs from reviewed profile`,
      );
    assert(!ids.has(member.id), `duplicate inventory ID ${member.id}`);
    assert(
      !workspaces.has(member.workspace),
      `duplicate inventory workspace ${member.workspace}`,
    );
    ids.add(member.id);
    workspaces.add(member.workspace);
  }
  return inventory;
}

export async function assertInventoryWorkspaces(inventory, rootManifest, root) {
  validatePackageInventory(inventory);
  assert.equal(
    rootManifest.private,
    true,
    "producer workspace root must remain private",
  );
  assert.deepEqual(
    rootManifest.workspaces,
    inventory.members.map(({ workspace }) => workspace),
    "inventory and producer workspaces differ",
  );
  const actualRoot = await realpath(root);
  for (const { workspace } of inventory.members) {
    const target = await realpath(path.join(root, workspace));
    const relative = path.relative(actualRoot, target);
    assert(
      relative && !relative.startsWith("..") && !path.isAbsolute(relative),
      `${workspace} inventory target escapes producer root`,
    );
  }
}
