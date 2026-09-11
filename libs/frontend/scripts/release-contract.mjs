import assert from "node:assert/strict";
import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const workspaceRoot = path.resolve(scriptDirectory, "..");
export const developmentContractPath = path.join(
  workspaceRoot,
  "release/development-fixture-contract.json",
);
export const packageRoles = ["designTokens", "ui", "iframeSdk"];
export const releaseStates = ["proposed", "fixture", "maintainer-confirmed"];

const exactVersionPattern = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
const exactToolVersionPattern = /^\d+\.\d+\.\d+$/;
const packageNamePattern = /^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/;
const localDependencyPattern =
  /^(?:workspace|file|link):|^(?:\.{0,2}[\\/]|[\\/])|^[a-z]:[\\/]/i;

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
      "maintainerApproval",
      "expectedProvenance",
      "packages",
    ],
    "release contract",
  );
  assert.equal(
    contract.schemaVersion,
    1,
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
  exactKeys(contract.releaseToolchain, ["node", "npm"], "release toolchain");
  for (const [name, value] of Object.entries(contract.releaseToolchain)) {
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
      contract.expectedProvenance.certificateIssuer,
      "https://token.actions.githubusercontent.com",
      "confirmed certificate issuer must be GitHub Actions OIDC",
    );
    assert(
      contract.maintainerApproval.scopeOwner,
      "confirmed scope owner is required",
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
  exactKeys(contract.packages, packageRoles, "release packages");
  const workspaces = new Set();
  const names = new Set();
  for (const role of packageRoles) {
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
    assert(
      !workspaces.has(entry.workspace),
      `duplicate workspace ${entry.workspace}`,
    );
    assert(!names.has(entry.name), `duplicate package name ${entry.name}`);
    workspaces.add(entry.workspace);
    names.add(entry.name);
  }
  if (contract.state === "maintainer-confirmed")
    for (const role of packageRoles)
      assert(
        !/development/i.test(contract.packages[role].version),
        `${role} fixture version cannot confirm a release contract`,
      );
  if (contract.state !== "proposed") {
    const requiredManifestFields = {
      designTokens: [
        "description",
        "license",
        "type",
        "exports",
        "files",
        "sideEffects",
      ],
      ui: [
        "description",
        "license",
        "type",
        "exports",
        "types",
        "files",
        "sideEffects",
        "peerDependencies",
      ],
      iframeSdk: [
        "description",
        "license",
        "type",
        "exports",
        "types",
        "files",
        "sideEffects",
      ],
    };
    for (const role of packageRoles) {
      const manifest = contract.packages[role].expectedManifest;
      for (const field of requiredManifestFields[role])
        assert(
          field in manifest,
          `${role} expectedManifest.${field} is required`,
        );
      assertPublishedDependencyReferences(manifest);
    }
    const token = contract.packages.designTokens;
    assert(
      contract.packages.ui.expectedManifest.peerDependencies?.[token.name],
      "UI expected manifest must declare the selected design-token peer",
    );
  }
  return contract;
}

export async function loadReleaseContract(
  contractPath = developmentContractPath,
) {
  return validateReleaseContract(
    JSON.parse(await readFile(path.resolve(contractPath), "utf8")),
  );
}

export function packageContract(contract, role) {
  validateReleaseContract(contract);
  assert(packageRoles.includes(role), `unknown package role ${role}`);
  return contract.packages[role];
}

export function assertExactRegistryCoordinate(coordinate, expectedPackage) {
  assert.equal(
    coordinate,
    `${expectedPackage.name}@${expectedPackage.version}`,
    `registry coordinate must be exact ${expectedPackage.name}@${expectedPackage.version}`,
  );
  assert(
    !localDependencyPattern.test(coordinate),
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
        typeof value === "string" && !localDependencyPattern.test(value),
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
  const expectedWorkspaces = packageRoles.map(
    (role) => contract.packages[role].workspace,
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
  for (const role of packageRoles) {
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
    const targetReal = await realpath(path.join(root, link.resolved));
    const rootReal = await realpath(root);
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
