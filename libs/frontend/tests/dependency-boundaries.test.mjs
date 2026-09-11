import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertOfflineConsumerReferences,
  assertRegistryConsumer,
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
    /unexpected local reference/,
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
