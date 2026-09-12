import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertExactRegistryCoordinate,
  assertExpectedManifest,
  assertProducerLockfile,
  assertPublishedDependencyReferences,
  assertReleaseToolchain,
  developmentContractPath,
  loadReleaseContract,
  validateReleaseContract,
  workspaceRoot,
} from "../scripts/release-contract.mjs";

const contract = await loadReleaseContract();
const rootManifest = JSON.parse(
  await readFile(path.join(workspaceRoot, "package.json"), "utf8"),
);
const lockfile = JSON.parse(
  await readFile(path.join(workspaceRoot, "package-lock.json"), "utf8"),
);

function clone(value) {
  return structuredClone(value);
}

function confirm(changed) {
  changed.state = "maintainer-confirmed";
  changed.distTag = "next";
  changed.expectedProvenance.repository = "https://github.com/example/fred";
  changed.expectedProvenance.workflow =
    "https://github.com/example/fred/.github/workflows/release.yml@refs/heads/main";
  changed.maintainerApproval = {
    scopeOwner: "test-maintainer-organization",
    owners: {
      packageApi: "test-package-api-owner",
      sdkProtocol: "test-sdk-protocol-owner",
      release: "test-release-owner",
      npmPublishing: "test-npm-publishing-owner",
    },
    bootstrapIdentity: "test-bootstrap-identity",
    bootstrapAuthorityVerified: true,
    registryAccess: "public",
    publishingPolicy: "staged",
  };
  for (const entry of Object.values(changed.packages))
    entry.version = "0.1.0-alpha.1";
  changed.packages.ui.expectedManifest.peerDependencies[
    changed.packages.designTokens.name
  ] = "^0.1.0-alpha.1";
}

test("loads the explicit development fixture contract", () => {
  assert.equal(contract.state, "fixture");
  assert.equal(contract.releaseToolchain.node, "24.21.0");
  assert.equal(contract.releaseToolchain.npm, "11.19.0");
  assert.match(developmentContractPath, /development-fixture-contract\.json$/);
});

test("accepts only explicit release contract states and exact versions", () => {
  for (const state of ["proposed", "fixture", "maintainer-confirmed"]) {
    const changed = clone(contract);
    changed.state = state;
    if (state === "maintainer-confirmed") confirm(changed);
    assert.doesNotThrow(() => validateReleaseContract(changed));
  }
  for (const value of ["next", "^1.2.3", "workspace:*", "file:package.tgz"]) {
    const changed = clone(contract);
    changed.packages.ui.version = value;
    assert.throws(() => validateReleaseContract(changed));
  }
  for (const mutate of [
    (changed) => delete changed.registry,
    (changed) => (changed.unexpected = true),
    (changed) => (changed.registry = "http://registry.example"),
    (changed) => (changed.releaseToolchain.npm = "11.x"),
    (changed) => (changed.packages.ui.name = "INVALID NAME"),
    (changed) =>
      (changed.packages.ui.name = changed.packages.designTokens.name),
  ]) {
    const changed = clone(contract);
    mutate(changed);
    assert.throws(() => validateReleaseContract(changed));
  }
});

test("confirmed contracts require explicit provenance identities", () => {
  const changed = clone(contract);
  confirm(changed);
  changed.expectedProvenance.workflow = null;
  assert.throws(() => validateReleaseContract(changed), /confirmed workflow/);
  const unverifiedBootstrap = clone(contract);
  confirm(unverifiedBootstrap);
  unverifiedBootstrap.maintainerApproval.bootstrapAuthorityVerified = false;
  assert.throws(
    () => validateReleaseContract(unverifiedBootstrap),
    /bootstrap authority/,
  );
  const incomplete = clone(contract);
  delete incomplete.packages.ui.expectedManifest.exports;
  assert.throws(
    () => validateReleaseContract(incomplete),
    /expectedManifest\.exports is required/,
  );
  const contradictory = clone(contract);
  delete contradictory.packages.ui.expectedManifest.peerDependencies[
    contradictory.packages.designTokens.name
  ];
  assert.throws(
    () => validateReleaseContract(contradictory),
    /selected design-token peer/,
  );
});

test("fixture markers cannot be promoted into a confirmed contract", () => {
  const changed = clone(contract);
  changed.state = "maintainer-confirmed";
  assert.throws(
    () => validateReleaseContract(changed),
    /confirmed source repository|confirmed workflow|bootstrap authority|fixture/,
  );
});

test("validates current member manifests against an external contract", async () => {
  for (const [role, expected] of Object.entries(contract.packages)) {
    const manifest = JSON.parse(
      await readFile(
        path.join(workspaceRoot, expected.workspace, "package.json"),
        "utf8",
      ),
    );
    assert.doesNotThrow(() => assertExpectedManifest(manifest, expected), role);
    const changed = clone(manifest);
    changed.version = "9.9.9";
    assert.throws(
      () => assertExpectedManifest(changed, expected),
      /version differs/,
    );
    for (const field of Object.keys(expected.expectedManifest)) {
      const changedField = clone(manifest);
      changedField[field] = null;
      assert.throws(
        () => assertExpectedManifest(changedField, expected),
        new RegExp(`${field} differs`),
      );
    }
  }
});

test("published manifests reject every local dependency boundary", () => {
  for (const reference of [
    "workspace:*",
    "file:archive.tgz",
    "link:../package",
    "git+file:///tmp/package",
    "\tGiT+FiLe:///tmp/package",
    "../package",
    "./package",
    "/tmp/package",
    "C:\\tmp\\package",
  ]) {
    assert.throws(
      () =>
        assertPublishedDependencyReferences({
          dependencies: { local: reference },
        }),
      /local dependency reference/,
    );
  }
  assert.doesNotThrow(() =>
    assertPublishedDependencyReferences({
      peerDependencies: { react: "^19.2.4" },
    }),
  );
});

test("rejects a publishable root or accidental fourth producer member", async () => {
  await assert.rejects(
    assertProducerLockfile({
      contract,
      rootManifest: { ...rootManifest, private: false },
      lockfile,
      root: workspaceRoot,
    }),
    /must remain private/,
  );
  await assert.rejects(
    assertProducerLockfile({
      contract,
      rootManifest: {
        ...rootManifest,
        workspaces: [...rootManifest.workspaces, "unexpected"],
      },
      lockfile,
      root: workspaceRoot,
    }),
    /workspace declaration differs/,
  );
});

test("accepts the npm-generated links for declared producer members", async () => {
  await assert.doesNotReject(
    assertProducerLockfile({
      contract,
      rootManifest,
      lockfile,
      root: workspaceRoot,
    }),
  );
});

test("rejects unexpected, mismatched, and escaping producer links", async () => {
  let changed = clone(lockfile);
  changed.packages["node_modules/unexpected"] = { link: true, resolved: "ui" };
  await assert.rejects(
    assertProducerLockfile({
      contract,
      rootManifest,
      lockfile: changed,
      root: workspaceRoot,
    }),
    /unexpected producer link/,
  );
  changed = clone(lockfile);
  changed.packages["node_modules/@fred/ui"].resolved = "design-tokens";
  await assert.rejects(
    assertProducerLockfile({
      contract,
      rootManifest,
      lockfile: changed,
      root: workspaceRoot,
    }),
    /target differs/,
  );
  changed = clone(lockfile);
  changed.packages["node_modules/@fred/ui"].resolved = "../ui";
  await assert.rejects(
    assertProducerLockfile({
      contract,
      rootManifest,
      lockfile: changed,
      root: workspaceRoot,
    }),
    /target differs|escapes/,
  );
});

test("rejects a declared producer member whose real target escapes", async (context) => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-release-lock-"));
  const outside = await mkdtemp(
    path.join(os.tmpdir(), "fred-release-outside-"),
  );
  context.after(() =>
    Promise.all([
      rm(temporary, { recursive: true, force: true }),
      rm(outside, { recursive: true, force: true }),
    ]),
  );
  await symlink(outside, path.join(temporary, "design-tokens"));
  await symlink(outside, path.join(temporary, "ui"));
  await symlink(outside, path.join(temporary, "iframe-sdk"));
  await assert.rejects(
    assertProducerLockfile({
      contract,
      rootManifest,
      lockfile,
      root: temporary,
    }),
    /real target escapes/,
  );
});

test("enforces exact registry coordinates and release toolchain", () => {
  assert.doesNotThrow(() =>
    assertExactRegistryCoordinate(
      "@fred/ui@0.0.0-development",
      contract.packages.ui,
    ),
  );
  for (const coordinate of [
    "@fred/ui@next",
    "@fred/ui@^0.1.0",
    "file:ui.tgz",
  ]) {
    assert.throws(() =>
      assertExactRegistryCoordinate(coordinate, contract.packages.ui),
    );
  }
  assert.doesNotThrow(() =>
    assertReleaseToolchain(contract, { node: "24.21.0", npm: "11.19.0" }),
  );
  assert.throws(
    () => assertReleaseToolchain(contract, { node: "24.21.1", npm: "11.19.0" }),
    /Node version differs/,
  );
});
