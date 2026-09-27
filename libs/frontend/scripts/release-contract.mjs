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
import { readFileSync } from "node:fs";
import {
  readFile as readFileAsync,
  realpath as realpathAsync,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  assertInventoryWorkspaces,
  loadPackageInventory,
  validatePackageInventory,
} from "./release-inventory.mjs";
import { assertDocumentSchema } from "./schema-validation.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const workspaceRoot = path.resolve(scriptDirectory, "..");
export const developmentContractPath = path.join(
  workspaceRoot,
  "release/development-fixture-contract.json",
);
export const inventoryPath = path.join(
  workspaceRoot,
  "release/package-inventory.json",
);
export const packageRoles = validatePackageInventory(
  JSON.parse(readFileSync(inventoryPath, "utf8")),
).members.map(({ id }) => id);
export const releaseStates = ["proposed", "fixture", "maintainer-confirmed"];

const exactVersionPattern = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
const exactToolVersionPattern = /^\d+\.\d+\.\d+$/;
const packageNamePattern = /^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/;
const localDependencyPattern =
  /^\s*(?:(?:workspace|file|link|git\+file):|\.{0,2}[\\/]|[\\/]|[a-z]:[\\/])/i;

export function isLocalDependencyReference(value) {
  return typeof value === "string" && localDependencyPattern.test(value);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, expected, label) {
  assert.deepEqual(
    Object.keys(value).sort(),
    [...expected].sort(),
    `${label} keys`,
  );
}

function assertManifestExports(exportsMap, label) {
  assert(isObject(exportsMap), `${label} exports must be an object`);
  for (const [exportName, target] of Object.entries(exportsMap)) {
    assert(
      exportName === "." || exportName.startsWith("./"),
      `${label} export name is invalid`,
    );
    const targets =
      typeof target === "string" ? [target] : Object.values(target ?? {});
    assert(targets.length > 0, `${label} export target is missing`);
    for (const value of targets)
      assert(
        typeof value === "string" &&
          value.startsWith("./dist/") &&
          !value.split("/").includes("..") &&
          !/[?#]/.test(value),
        `${label} export target escapes packaged dist`,
      );
  }
}

export function validateReleaseContract(contract) {
  assert(isObject(contract), "release contract must be an object");
  exactKeys(
    contract,
    [
      "$schema",
      "schemaVersion",
      "state",
      "registry",
      "distTag",
      "releaseToolchain",
      "applicationToolchain",
      "sourceBranch",
      "workflowFilename",
      "publishingEnvironment",
      "approvedBaselineDigest",
      "maintainerApproval",
      "expectedProvenance",
      "packages",
      "inventory",
    ],
    "release contract",
  );
  assertDocumentSchema(
    Object.fromEntries(
      Object.entries(contract).filter(
        ([field]) => !["inventory", "packages"].includes(field),
      ),
    ),
    path.join(workspaceRoot, "release/release-contract.schema.json"),
    "release policy",
  );
  assert.equal(
    contract.schemaVersion,
    2,
    "unsupported release contract schema",
  );
  assert(
    releaseStates.includes(contract.state),
    "invalid release contract state",
  );
  const registry = new URL(contract.registry);
  assert.equal(registry.protocol, "https:", "release registry must use HTTPS");
  assert.equal(
    registry.pathname,
    "/",
    "release registry must not contain a path",
  );
  assert(/^[a-z][a-z0-9._-]*$/.test(contract.distTag), "invalid dist-tag");
  assert(
    /^[a-z][a-z0-9._/-]*$/.test(contract.sourceBranch),
    "invalid source branch",
  );
  assert(
    /^[A-Za-z0-9_-]+\.yml$/.test(contract.workflowFilename),
    "invalid workflow filename",
  );
  assert(
    typeof contract.publishingEnvironment === "string" &&
      contract.publishingEnvironment.length > 0,
    "publishing environment is required",
  );
  assert(
    /^[a-f0-9]{64}$/.test(contract.approvedBaselineDigest),
    "approved baseline digest invalid",
  );
  exactKeys(contract.releaseToolchain, ["node", "npm"], "release toolchain");
  exactKeys(
    contract.applicationToolchain,
    ["node", "npm"],
    "application toolchain",
  );
  for (const [name, value] of [
    ...Object.entries(contract.releaseToolchain),
    ...Object.entries(contract.applicationToolchain),
  ]) {
    assert(
      exactToolVersionPattern.test(value),
      `${name} must be an exact version`,
    );
  }
  exactKeys(
    contract.maintainerApproval,
    [
      "scopeOwner",
      "owners",
      "bootstrapIdentity",
      "bootstrapAuthorityVerified",
      "registryAccess",
      "publishingPolicy",
    ],
    "maintainer approval",
  );
  exactKeys(
    contract.maintainerApproval.owners,
    ["packageApi", "sdkProtocol", "release", "npmPublishing"],
    "maintainer owners",
  );
  exactKeys(
    contract.expectedProvenance,
    ["repository", "workflow", "certificateIssuer"],
    "expected provenance",
  );
  for (const field of ["repository", "workflow", "certificateIssuer"]) {
    const value = contract.expectedProvenance[field];
    assert(value === null || (typeof value === "string" && value.length > 0));
  }
  if (contract.state === "maintainer-confirmed") {
    assert.equal(
      contract.registry,
      "https://registry.npmjs.org/",
      "confirmed registry differs from policy",
    );
    assert.equal(
      contract.distTag,
      "next",
      "confirmed dist-tag differs from policy",
    );
    assert.equal(
      contract.sourceBranch,
      "swift",
      "confirmed branch must be swift",
    );
    assert.equal(
      contract.workflowFilename,
      "Publish-frontend-packages.yml",
      "confirmed workflow filename differs",
    );
    assert.equal(
      contract.publishingEnvironment,
      "npm-publish",
      "confirmed environment differs",
    );
    assert(
      contract.expectedProvenance.repository,
      "confirmed repository is required",
    );
    assert(
      contract.expectedProvenance.workflow,
      "confirmed workflow is required",
    );
    assert(
      contract.expectedProvenance.certificateIssuer,
      "confirmed certificate issuer is required",
    );
    assert.equal(
      new URL(contract.expectedProvenance.repository).origin,
      "https://github.com",
      "confirmed source repository must be a GitHub repository",
    );
    assert(
      contract.expectedProvenance.workflow.startsWith(
        `${contract.expectedProvenance.repository}/.github/workflows/`,
      ) && contract.expectedProvenance.workflow.includes("@refs/"),
      "confirmed workflow must be the GitHub certificate identity URI",
    );
    assert.equal(
      contract.expectedProvenance.workflow,
      `${contract.expectedProvenance.repository}/.github/workflows/${contract.workflowFilename}@refs/heads/${contract.sourceBranch}`,
      "workflow identity differs from release policy",
    );
    assert.equal(
      contract.expectedProvenance.certificateIssuer,
      "https://token.actions.githubusercontent.com",
      "confirmed certificate issuer must be GitHub Actions OIDC",
    );
    assert(
      contract.maintainerApproval.scopeOwner,
      "confirmed scope owner is required",
    );
    assert.equal(
      contract.maintainerApproval.scopeOwner,
      "fred-oss",
      "confirmed scope differs from policy",
    );
    for (const [role, owner] of Object.entries(
      contract.maintainerApproval.owners,
    ))
      assert(owner, `confirmed ${role} owner is required`);
    assert(
      contract.maintainerApproval.bootstrapIdentity,
      "confirmed bootstrap identity is required",
    );
    assert.equal(
      contract.maintainerApproval.bootstrapAuthorityVerified,
      true,
      "bootstrap authority must be verified",
    );
    assert.equal(
      contract.maintainerApproval.registryAccess,
      "public",
      "confirmed registry access must be public",
    );
    assert(
      ["direct", "staged"].includes(
        contract.maintainerApproval.publishingPolicy,
      ),
      "confirmed publishing policy is required",
    );
    const approvalValues = [
      contract.maintainerApproval.scopeOwner,
      ...Object.values(contract.maintainerApproval.owners),
      contract.maintainerApproval.bootstrapIdentity,
    ];
    assert(
      approvalValues.every((value) => !/^fixture:/i.test(value)),
      "fixture approval identities cannot confirm a release contract",
    );
    assert.notEqual(
      contract.distTag,
      "development",
      "fixture dist-tag cannot confirm a release contract",
    );
  }
  validatePackageInventory(contract.inventory);
  const registeredRoles = contract.inventory.members.map(({ id }) => id);
  exactKeys(contract.packages, registeredRoles, "release packages");
  const workspaces = new Set();
  const names = new Set();
  for (const role of registeredRoles) {
    const entry = contract.packages[role];
    exactKeys(
      entry,
      ["workspace", "name", "version", "expectedManifest"],
      `${role} package`,
    );
    assert(
      /^[a-z0-9-]+$/.test(entry.workspace),
      `${role} workspace is invalid`,
    );
    assert(
      packageNamePattern.test(entry.name),
      `${role} package name is invalid`,
    );
    assert(
      exactVersionPattern.test(entry.version),
      `${role} version must be exact`,
    );
    assert(
      isObject(entry.expectedManifest),
      `${role} expectedManifest must be an object`,
    );
    assert.equal(
      entry.workspace,
      contract.inventory.members.find(({ id }) => id === role).workspace,
      `${role} workspace differs from inventory`,
    );
    assert(
      !workspaces.has(entry.workspace),
      `duplicate workspace ${entry.workspace}`,
    );
    assert(!names.has(entry.name), `duplicate package name ${entry.name}`);
    workspaces.add(entry.workspace);
    names.add(entry.name);
  }
  if (contract.maintainerApproval.bootstrapAuthorityVerified) {
    const expectedScope = `@${contract.maintainerApproval.scopeOwner}/`;
    for (const role of registeredRoles)
      assert(
        contract.packages[role].name.startsWith(expectedScope),
        `${role} package must belong to the verified npm scope ${expectedScope}`,
      );
  }
  if (contract.state === "maintainer-confirmed")
    for (const role of registeredRoles)
      assert(
        !/development/i.test(contract.packages[role].version),
        `${role} fixture version cannot confirm a release contract`,
      );
  const requiredManifestFields = {
    "design-tokens": [
      "description",
      "license",
      "type",
      "repository",
      "homepage",
      "bugs",
      "engines",
      "exports",
      "files",
      "sideEffects",
      "publishConfig",
    ],
    ui: [
      "description",
      "license",
      "type",
      "repository",
      "homepage",
      "bugs",
      "engines",
      "exports",
      "types",
      "files",
      "sideEffects",
      "peerDependencies",
      "publishConfig",
    ],
    "iframe-sdk": [
      "description",
      "license",
      "type",
      "repository",
      "homepage",
      "bugs",
      "engines",
      "exports",
      "types",
      "files",
      "sideEffects",
      "publishConfig",
    ],
  };
  for (const role of registeredRoles) {
    const profile = contract.inventory.members.find(
      ({ id }) => id === role,
    ).validator;
    assert(
      requiredManifestFields[profile],
      `${role} profile lacks a reviewed archive validator`,
    );
    const manifest = contract.packages[role].expectedManifest;
    for (const field of requiredManifestFields[profile])
      assert(
        field in manifest,
        `${role} expectedManifest.${field} is required`,
      );
    assertManifestExports(manifest.exports, role);
    assertPublishedDependencyReferences(manifest);
    assert.deepEqual(
      manifest.publishConfig,
      {
        access: "public",
        registry: contract.registry,
        tag: contract.distTag,
        provenance: true,
      },
      `${role} publishConfig differs from release policy`,
    );
    if (contract.state === "maintainer-confirmed") {
      assert.equal(
        manifest.repository?.url,
        `git+${contract.expectedProvenance.repository}.git`,
        `${role} repository differs from release policy`,
      );
      assert.equal(
        manifest.repository?.directory,
        `libs/frontend/${contract.packages[role].workspace}`,
        `${role} repository directory differs from inventory`,
      );
    }
  }
  const token = contract.packages.designTokens;
  if (token && contract.packages.ui)
    assert(
      contract.packages.ui.expectedManifest.peerDependencies?.[token.name],
      "UI expected manifest must declare the selected design-token peer",
    );
  return contract;
}

export function unresolvedMaintainerDecisions(contract) {
  validateReleaseContract(contract);
  const unresolved = [];
  for (const [role, owner] of Object.entries(
    contract.maintainerApproval.owners,
  ))
    if (!owner) unresolved.push(`maintainerApproval.owners.${role}`);
  if (!contract.maintainerApproval.publishingPolicy)
    unresolved.push("maintainerApproval.publishingPolicy");
  return unresolved;
}

export function assertMaintainerConfirmed(contract) {
  validateReleaseContract(contract);
  const unresolved = unresolvedMaintainerDecisions(contract);
  assert.equal(
    contract.state,
    "maintainer-confirmed",
    `release contract is not maintainer-confirmed${
      unresolved.length ? `; unresolved: ${unresolved.join(", ")}` : ""
    }`,
  );
  return contract;
}

export async function loadReleaseContract(
  contractPath = developmentContractPath,
  {
    root = workspaceRoot,
    inventoryFile = path.join(root, "release/package-inventory.json"),
  } = {},
) {
  const policy = JSON.parse(
    await readFileAsync(path.resolve(contractPath), "utf8"),
  );
  const inventory = await loadPackageInventory(inventoryFile);
  const rootManifest = JSON.parse(
    await readFileAsync(path.join(root, "package.json"), "utf8"),
  );
  await assertInventoryWorkspaces(inventory, rootManifest, root);
  const packages = {};
  for (const { id, workspace } of inventory.members) {
    const manifest = JSON.parse(
      await readFileAsync(path.join(root, workspace, "package.json"), "utf8"),
    );
    assert.notEqual(
      manifest.private,
      true,
      `${id} registered release member must not be private`,
    );
    packages[id] = {
      workspace,
      name: manifest.name,
      version: manifest.version,
      expectedManifest: Object.fromEntries(
        Object.entries(manifest).filter(
          ([field]) =>
            ![
              "name",
              "version",
              "private",
              "scripts",
              "devDependencies",
            ].includes(field),
        ),
      ),
    };
  }
  return validateReleaseContract({ ...policy, inventory, packages });
}

export function packageContract(contract, role) {
  validateReleaseContract(contract);
  assert(
    contract.inventory.members.some(({ id }) => id === role),
    `unknown package role ${role}`,
  );
  return contract.packages[role];
}

export function assertExactRegistryCoordinate(coordinate, expectedPackage) {
  assert.equal(
    coordinate,
    `${expectedPackage.name}@${expectedPackage.version}`,
    `registry coordinate must be exact ${expectedPackage.name}@${expectedPackage.version}`,
  );
  assert(
    !isLocalDependencyReference(coordinate),
    "registry coordinate is local",
  );
}

export function assertPublishedDependencyReferences(manifest) {
  for (const field of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    for (const [name, value] of Object.entries(manifest[field] ?? {})) {
      assert(
        typeof value === "string" && !isLocalDependencyReference(value),
        `${field}.${name} uses a local dependency reference`,
      );
    }
  }
}

export function assertExpectedManifest(manifest, expectedPackage) {
  assert.equal(
    manifest.name,
    expectedPackage.name,
    "package name differs from release contract",
  );
  assert.equal(
    manifest.version,
    expectedPackage.version,
    "package version differs from release contract",
  );
  assert.notEqual(manifest.private, true, "release member must not be private");
  assertPublishedDependencyReferences(manifest);
  for (const [field, expected] of Object.entries(
    expectedPackage.expectedManifest,
  )) {
    assert.deepEqual(
      manifest[field],
      expected,
      `${field} differs from release contract`,
    );
  }
}

function assertContainedRelative(target, expected, label) {
  assert.equal(
    target,
    expected,
    `${label} target differs from declared workspace`,
  );
  assert(!path.isAbsolute(target), `${label} target must be relative`);
  const normalized = path.posix.normalize(target.replaceAll(path.sep, "/"));
  assert(
    !normalized.startsWith("../") && normalized !== "..",
    `${label} target escapes`,
  );
}

export async function assertProducerLockfile({
  contract,
  rootManifest,
  lockfile,
  root = workspaceRoot,
}) {
  validateReleaseContract(contract);
  assert.equal(
    rootManifest.private,
    true,
    "producer workspace root must remain private",
  );
  const expectedWorkspaces = contract.inventory.members.map(
    ({ id }) => contract.packages[id].workspace,
  );
  assert.deepEqual(
    rootManifest.workspaces,
    expectedWorkspaces,
    "workspace declaration differs",
  );
  assert.deepEqual(
    lockfile.packages?.[""]?.workspaces,
    expectedWorkspaces,
    "lock workspaces differ",
  );

  const expectedLinks = new Map();
  for (const role of contract.inventory.members.map(({ id }) => id)) {
    const expected = contract.packages[role];
    const workspaceEntry = lockfile.packages?.[expected.workspace];
    assert.equal(
      workspaceEntry?.name,
      expected.name,
      `${role} lock member name differs`,
    );
    assert.equal(
      workspaceEntry?.version,
      expected.version,
      `${role} lock member version differs`,
    );
    const lockPath = `node_modules/${expected.name}`;
    expectedLinks.set(lockPath, expected.workspace);
    const link = lockfile.packages?.[lockPath];
    assert.equal(link?.link, true, `${lockPath} must be npm workspace link`);
    assertContainedRelative(link.resolved, expected.workspace, lockPath);
    const targetReal = await realpathAsync(path.join(root, link.resolved));
    const rootReal = await realpathAsync(root);
    const relative = path.relative(rootReal, targetReal);
    assert(
      relative && !relative.startsWith("..") && !path.isAbsolute(relative),
      `${lockPath} real target escapes producer workspace`,
    );
  }
  for (const [lockPath, entry] of Object.entries(lockfile.packages ?? {})) {
    if (!entry?.link) continue;
    assert(expectedLinks.has(lockPath), `unexpected producer link ${lockPath}`);
    assertContainedRelative(
      entry.resolved,
      expectedLinks.get(lockPath),
      lockPath,
    );
  }
}

export function assertReleaseToolchain(contract, actual = process.versions) {
  const node = actual.node;
  const npm =
    actual.npm ?? process.env.npm_config_user_agent?.match(/npm\/([^ ]+)/)?.[1];
  assert.equal(
    node,
    contract.releaseToolchain.node,
    "release Node version differs",
  );
  assert.equal(
    npm,
    contract.releaseToolchain.npm,
    "release npm version differs",
  );
}
