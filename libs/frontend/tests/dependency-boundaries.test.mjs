import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertOfflineConsumerReferences,
  assertRegistryConsumer,
  installAfterOfflineReferenceValidation,
  validateCandidateTarballReference,
} from "../scripts/dependency-boundaries.mjs";
import { loadReleaseContract } from "../scripts/release-contract.mjs";
import { sha512Integrity } from "../scripts/release-evidence.mjs";

const contract = await loadReleaseContract();

async function fixture(context) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-offline-boundary-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const filename = "ui.tgz";
  const archive = path.join(root, filename);
  await writeFile(archive, "fixture archive bytes");
  const integrity = await sha512Integrity(archive);
  const coordinate = `${contract.packages.ui.name}@${contract.packages.ui.version}`;
  const reference = `file:${filename}`;
  return {
    root,
    filename,
    archive,
    integrity,
    evidence: {
      packages: { ui: { coordinate, filename, integrity } },
    },
    manifest: { dependencies: { [contract.packages.ui.name]: reference } },
    lockfile: {
      packages: {
        "": { dependencies: { [contract.packages.ui.name]: reference } },
        [`node_modules/${contract.packages.ui.name}`]: {
          version: contract.packages.ui.version,
          resolved: reference,
          integrity,
        },
      },
    },
  };
}

test("accepts npm file references to the integrity-verified candidate tarball", async (context) => {
  const value = await fixture(context);
  await assert.doesNotReject(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
  );
});

test("validates the complete offline graph before dependency installation", async (context) => {
  const value = await fixture(context);
  let installed = false;
  await installAfterOfflineReferenceValidation({
    manifest: value.manifest,
    lockfile: value.lockfile,
    consumerRoot: value.root,
    evidence: value.evidence,
    installDependencies: async () => {
      installed = true;
    },
  });
  assert.equal(installed, true);

  installed = false;
  value.lockfile.packages["node_modules/unapproved"] = {
    version: contract.packages.ui.version,
    resolved: `file:${value.filename}`,
    integrity: value.integrity,
  };
  await assert.rejects(
    installAfterOfflineReferenceValidation({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
      installDependencies: async () => {
        installed = true;
      },
    }),
    /unapproved local dependency identity/,
  );
  assert.equal(installed, false);
});

test("rejects modified, directory, escaping, symlink, and unexpected tarball references", async (context) => {
  let value = await fixture(context);
  await writeFile(value.archive, "modified");
  await assert.rejects(
    validateCandidateTarballReference({
      specifier: `file:${value.filename}`,
      consumerRoot: value.root,
      expectedFilename: value.filename,
      expectedIntegrity: value.integrity,
    }),
    /integrity differs/,
  );

  value = await fixture(context);
  await mkdir(path.join(value.root, "directory"));
  await assert.rejects(
    validateCandidateTarballReference({
      specifier: "file:directory",
      consumerRoot: value.root,
      expectedFilename: "directory",
      expectedIntegrity: value.integrity,
    }),
    /regular file/,
  );
  await assert.rejects(
    validateCandidateTarballReference({
      specifier: "file:../outside.tgz",
      consumerRoot: value.root,
      expectedFilename: "outside.tgz",
      expectedIntegrity: value.integrity,
    }),
    /escapes/,
  );
  const link = path.join(value.root, "linked.tgz");
  await symlink(value.archive, link);
  await assert.rejects(
    validateCandidateTarballReference({
      specifier: "file:linked.tgz",
      consumerRoot: value.root,
      expectedFilename: "linked.tgz",
      expectedIntegrity: value.integrity,
    }),
    /symlink/,
  );
  value.lockfile.packages["node_modules/unexpected"] = {
    resolved: "file:other.tgz",
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /unexpected local reference|unapproved local dependency identity/,
  );
});

test("rejects npm-decoded traversal and separator ambiguity in file references", async (context) => {
  const value = await fixture(context);
  const encodedTraversalDirectory = path.join(value.root, "%2e%2e");
  await mkdir(encodedTraversalDirectory);
  const literalTraversalArchive = path.join(
    encodedTraversalDirectory,
    value.filename,
  );
  await writeFile(literalTraversalArchive, "encoded traversal bytes");
  await assert.rejects(
    validateCandidateTarballReference({
      specifier: `file:%2e%2e/${value.filename}`,
      consumerRoot: value.root,
      expectedFilename: value.filename,
      expectedIntegrity: await sha512Integrity(literalTraversalArchive),
    }),
    /encoded|ambiguous/,
  );

  const encodedSeparatorFilename = `stage%2f${value.filename}`;
  const literalSeparatorArchive = path.join(
    value.root,
    encodedSeparatorFilename,
  );
  await writeFile(literalSeparatorArchive, "encoded separator bytes");
  await assert.rejects(
    validateCandidateTarballReference({
      specifier: `file:${encodedSeparatorFilename}`,
      consumerRoot: value.root,
      expectedFilename: encodedSeparatorFilename,
      expectedIntegrity: await sha512Integrity(literalSeparatorArchive),
    }),
    /encoded|ambiguous/,
  );

  for (const suffix of ["?other", "#other", "\\other"]) {
    await assert.rejects(
      validateCandidateTarballReference({
        specifier: `file:${value.filename}${suffix}`,
        consumerRoot: value.root,
        expectedFilename: `${value.filename}${suffix}`,
        expectedIntegrity: value.integrity,
      }),
      /encoded|ambiguous/,
    );
  }
});

test("rejects unapproved local lock entries even when candidate filenames match", async (context) => {
  let value = await fixture(context);
  const outsideRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-offline-boundary-outside-"),
  );
  context.after(() => rm(outsideRoot, { recursive: true, force: true }));
  const outsideArchive = path.join(outsideRoot, value.filename);
  await writeFile(outsideArchive, "different outside bytes");
  value.lockfile.packages[
    `node_modules/holder/node_modules/${contract.packages.ui.name}`
  ] = {
    resolved: `file:${path.relative(value.root, outsideArchive)}`,
    integrity: await sha512Integrity(outsideArchive),
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /escapes/,
  );

  value = await fixture(context);
  await mkdir(path.join(value.root, "extra"));
  await writeFile(
    path.join(value.root, "extra", value.filename),
    "other bytes",
  );
  value.lockfile.packages["node_modules/unapproved"] = {
    resolved: `file:extra/${value.filename}`,
    integrity: await sha512Integrity(
      path.join(value.root, "extra", value.filename),
    ),
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /unexpected local reference|unapproved|identity/,
  );
});

test("rejects directory, symlink, nested, and integrity-bypassing local lock entries", async (context) => {
  let value = await fixture(context);
  await mkdir(path.join(value.root, "extra"));
  await mkdir(path.join(value.root, "extra", value.filename));
  value.lockfile.packages[
    `node_modules/holder/node_modules/${contract.packages.ui.name}`
  ] = {
    resolved: `file:extra/${value.filename}`,
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /regular file/,
  );

  value = await fixture(context);
  await mkdir(path.join(value.root, "linked"));
  await symlink(value.archive, path.join(value.root, "linked", value.filename));
  value.lockfile.packages[
    `node_modules/holder/node_modules/${contract.packages.ui.name}`
  ] = {
    resolved: `file:linked/${value.filename}`,
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /symlink/,
  );

  value = await fixture(context);
  await mkdir(path.join(value.root, "extra"));
  await writeFile(
    path.join(value.root, "extra", value.filename),
    "nested bytes",
  );
  value.lockfile.packages["node_modules/holder"] = {
    dependencies: { unapproved: `file:extra/${value.filename}` },
  };
  value.lockfile.packages["node_modules/holder/node_modules/unapproved"] = {
    resolved: `file:extra/${value.filename}`,
    integrity: await sha512Integrity(
      path.join(value.root, "extra", value.filename),
    ),
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /unapproved|unexpected local reference|identity/,
  );

  value = await fixture(context);
  value.lockfile.packages[
    `node_modules/holder/node_modules/${contract.packages.ui.name}`
  ] = {
    resolved: `file:${value.filename}`,
    integrity: "sha512-wrong",
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /integrity differs/,
  );
});

test("inspects local references in root and nested dependency fields", async (context) => {
  let value = await fixture(context);
  value.manifest.optionalDependencies = {
    unapproved: `file:${value.filename}`,
  };
  value.lockfile.packages[""].optionalDependencies = {
    unapproved: `file:${value.filename}`,
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /unapproved local dependency identity/,
  );

  value = await fixture(context);
  value.lockfile.packages["node_modules/holder"] = {
    optionalDependencies: { unapproved: `file:${value.filename}` },
  };
  await assert.rejects(
    assertOfflineConsumerReferences({
      manifest: value.manifest,
      lockfile: value.lockfile,
      consumerRoot: value.root,
      evidence: value.evidence,
    }),
    /unapproved local dependency identity/,
  );
});

test("registry consumers require exact versions, integrity, and registry URLs", () => {
  const confirmed = structuredClone(contract);
  confirmed.state = "maintainer-confirmed";
  const packages = {};
  const dependencies = {};
  const lockPackages = { "": { dependencies } };
  for (const [role, expected] of Object.entries(confirmed.packages)) {
    const integrity = `sha512-${Buffer.from(role).toString("base64")}`;
    packages[role] = { integrity };
    dependencies[expected.name] = expected.version;
    lockPackages[`node_modules/${expected.name}`] = {
      version: expected.version,
      resolved: `https://registry.npmjs.org/${expected.name}/-/${role}.tgz`,
      integrity,
    };
  }
  const manifest = { dependencies };
  const lockfile = { packages: lockPackages };
  assert.doesNotThrow(() =>
    assertRegistryConsumer({
      manifest,
      lockfile,
      contract: confirmed,
      evidence: { packages },
    }),
  );
  lockPackages["node_modules/@fred/ui"].resolved = "file:ui.tgz";
  assert.throws(
    () =>
      assertRegistryConsumer({
        manifest,
        lockfile,
        contract: confirmed,
        evidence: { packages },
      }),
    /Invalid URL|registry|local fallback/,
  );
});
