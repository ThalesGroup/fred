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
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { loadReleaseContract } from "../scripts/release-contract.mjs";
import {
  reviewedProfiles,
  validatePackageInventory,
} from "../scripts/release-inventory.mjs";
import { validateReleaseRecord } from "../scripts/release-record.mjs";
import { assertSelectedRegistryInputs } from "../scripts/registry-verifier.mjs";
import {
  orderReleaseMembers,
  selectInventoryMembers,
  selectReleaseMembers,
  selectionOption,
} from "../scripts/release-selection.mjs";

const contract = await loadReleaseContract();

test("selection is deterministic and leaves omitted all-member commands working", () => {
  assert.deepEqual(selectReleaseMembers(contract), [
    "designTokens",
    "ui",
    "iframeSdk",
  ]);
  assert.deepEqual(selectReleaseMembers(contract, "iframeSdk"), ["iframeSdk"]);
  assert.deepEqual(selectReleaseMembers(contract, "ui,designTokens"), [
    "designTokens",
    "ui",
  ]);
  assert.deepEqual(selectReleaseMembers(contract, "designTokens"), [
    "designTokens",
  ]);
  assert.deepEqual(orderReleaseMembers(contract, ["ui", "designTokens"]), [
    "designTokens",
    "ui",
  ]);
});

test("omitted selection sorts a dependent registered before its prerequisite", () => {
  const inventory = {
    members: [{ id: "futureTool" }, { id: "designTokens" }],
  };
  const packages = {
    futureTool: {
      name: "@fred-oss/future-tool",
      expectedManifest: {
        dependencies: { "@fred-oss/design-tokens": "0.1.0-alpha.1" },
        peerDependencies: {},
      },
    },
    designTokens: {
      name: "@fred-oss/design-tokens",
      expectedManifest: { dependencies: {}, peerDependencies: {} },
    },
  };
  assert.deepEqual(selectInventoryMembers({ inventory, packages }), [
    "designTokens",
    "futureTool",
  ]);
});

test("Make preserves an explicitly empty selection and provisioned browser path", () => {
  const cwd = path.resolve(import.meta.dirname, "..");
  const omittedEnv = { ...process.env };
  delete omittedEnv.RELEASE_SELECTION;
  const selectedEnv = {
    ...omittedEnv,
    RELEASE_SELECTION: "designTokens,ui,iframeSdk",
  };
  const omitted = execFileSync("make", ["-n", "release-transfer-create"], {
    cwd,
    encoding: "utf8",
    env: omittedEnv,
  });
  const empty = execFileSync(
    "make",
    ["-n", "RELEASE_SELECTION=", "release-transfer-create"],
    { cwd, encoding: "utf8", env: selectedEnv },
  );
  const selected = execFileSync("make", ["-n", "release-transfer-create"], {
    cwd,
    encoding: "utf8",
    env: selectedEnv,
  });
  const candidate = execFileSync("make", ["-n", "release-candidate"], {
    cwd,
    encoding: "utf8",
    env: omittedEnv,
  });
  assert(!omitted.includes("--select"));
  assert.match(empty, /--select ""/);
  assert.match(selected, /--select "designTokens,ui,iframeSdk"/);
  assert.match(candidate, /PLAYWRIGHT_BROWSERS_PATH=target\/playwright/);
});

test("explicit invalid selections fail before packing", () => {
  for (const value of [
    "",
    " ",
    ",",
    "ui,",
    ",ui",
    "ui,ui",
    "unknown",
    "@fred/frontend-packages-workspace",
    "frontend-packages-workspace",
  ])
    assert.throws(() => selectReleaseMembers(contract, value));
  assert.throws(
    () => selectionOption(["node", "script", "--select"]),
    /requires/,
  );
  assert.throws(
    () =>
      selectionOption(["node", "script", "--select", "ui", "--select", "ui"]),
    /duplicate/,
  );
  assert.equal(selectionOption(["node", "script", "--select", "ui"]), "ui");
  assert.equal(selectionOption(["node", "script"]), undefined);
});

test("disposable fourth profile exercises selection, record and generic verifier without registering a release member", async () => {
  const fixture = JSON.parse(
    await readFile(
      path.resolve(
        import.meta.dirname,
        "../fixtures/release-fourth-package.json",
      ),
      "utf8",
    ),
  );
  assert.throws(
    () => validatePackageInventory(fixture.inventory),
    /unreviewed inventory workspace/,
  );
  const inventory = validatePackageInventory(fixture.inventory, {
    profiles: { ...reviewedProfiles, "future-tool": fixture.profile },
  });
  const packages = { ...contract.packages, futureTool: fixture.package };
  assert.deepEqual(
    selectInventoryMembers({ inventory, packages, selection: "futureTool" }),
    ["futureTool"],
  );
  const candidate = {
    schemaVersion: 1,
    kind: "candidate",
    readiness: "fixture",
    sourceCommit: "f".repeat(40),
    transferOrigin: null,
    selected: [
      {
        id: "futureTool",
        coordinate: `${fixture.package.name}@${fixture.package.version}`,
        builder: fixture.profile.builder,
        validator: fixture.profile.validator,
        consumer: fixture.profile.consumer,
      },
    ],
    compatibilityOnly: [],
    policyDigest: `sha256-${"A".repeat(43)}=`,
    baselineDigest: `sha256-${"a".repeat(64)}`,
    expectedProvenance: {
      repository: "fixture/repository",
      workflow: "fixture/workflow",
      certificateIssuer: "fixture/issuer",
    },
    observedToolchains: {
      producer: { node: "24.21.0", npm: "11.19.0" },
      application: { node: "22.13.0", npm: "10.9.2" },
    },
    gates: { archives: { validated: true } },
    archives: {
      futureTool: {
        filename: "future-tool-fixture.tgz",
        bytes: 32,
        integrity: `sha512-${"A".repeat(86)}==`,
      },
    },
    manifestRanges: { futureTool: { dependencies: {}, peerDependencies: {} } },
  };
  validateReleaseRecord(candidate);
  assertSelectedRegistryInputs({
    inventory,
    packages,
    selectedIds: ["futureTool"],
    coordinates: { futureTool: candidate.selected[0].coordinate },
    evidence: {
      packages: {
        futureTool: {
          coordinate: candidate.selected[0].coordinate,
          integrity: candidate.archives.futureTool.integrity,
        },
      },
    },
  });
  assert.throws(
    () =>
      selectReleaseMembers({ ...contract, inventory, packages }, "futureTool"),
    /unreviewed inventory workspace|profile lacks a reviewed archive validator/,
  );
});
