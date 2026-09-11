import assert from "node:assert/strict";
import { lstat, realpath } from "node:fs/promises";
import path from "node:path";

import { sha512Integrity } from "./release-evidence.mjs";

function within(root, target) {
  const relative = path.relative(root, target);
  return (
    relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative)
  );
}

function fileTarget(specifier) {
  assert.equal(
    typeof specifier,
    "string",
    "dependency reference must be a string",
  );
  assert(
    specifier.startsWith("file:"),
    "candidate dependency must use npm file: syntax",
  );
  return specifier.slice("file:".length);
}

export async function validateCandidateTarballReference({
  specifier,
  consumerRoot,
  expectedFilename,
  expectedIntegrity,
}) {
  const reference = fileTarget(specifier);
  assert(
    reference && !reference.endsWith("/"),
    "candidate reference must name a tarball",
  );
  const rootReal = await realpath(consumerRoot);
  const absolute = path.resolve(consumerRoot, reference);
  const relative = path.relative(consumerRoot, absolute);
  assert(
    within(consumerRoot, absolute),
    "candidate reference escapes consumer",
  );
  assert.equal(
    path.basename(relative),
    expectedFilename,
    "candidate archive filename differs",
  );
  const metadata = await lstat(absolute);
  assert.equal(
    metadata.isSymbolicLink(),
    false,
    "candidate archive must not be a symlink",
  );
  assert.equal(
    metadata.isFile(),
    true,
    "candidate reference must resolve to a regular file",
  );
  const targetReal = await realpath(absolute);
  assert(
    within(rootReal, targetReal),
    "candidate archive real path escapes consumer",
  );
  assert.equal(
    await sha512Integrity(absolute),
    expectedIntegrity,
    "candidate archive integrity differs",
  );
  return absolute;
}

export async function assertOfflineConsumerReferences({
  manifest,
  lockfile,
  consumerRoot,
  evidence,
}) {
  const allowed = new Map();
  for (const record of Object.values(evidence.packages ?? {})) {
    const separator = record.coordinate.lastIndexOf("@");
    const name = record.coordinate.slice(0, separator);
    allowed.set(name, record);
  }
  for (const [name, record] of allowed) {
    const manifestReference = manifest.dependencies?.[name];
    const lockReference = lockfile.packages?.[""]?.dependencies?.[name];
    assert.equal(
      manifestReference,
      lockReference,
      `${name} manifest/lock reference differs`,
    );
    await validateCandidateTarballReference({
      specifier: manifestReference,
      consumerRoot,
      expectedFilename: record.filename,
      expectedIntegrity: record.integrity,
    });
    const installed = lockfile.packages?.[`node_modules/${name}`];
    assert(installed, `${name} lock entry is missing`);
    assert.equal(
      installed.link,
      undefined,
      `${name} must not be a consumer link`,
    );
    assert.equal(
      installed.integrity,
      record.integrity,
      `${name} lock integrity differs`,
    );
    await validateCandidateTarballReference({
      specifier: installed.resolved,
      consumerRoot,
      expectedFilename: record.filename,
      expectedIntegrity: record.integrity,
    });
  }
  for (const [lockPath, entry] of Object.entries(lockfile.packages ?? {})) {
    assert.notEqual(
      entry?.link,
      true,
      `isolated consumer contains link ${lockPath}`,
    );
    if (
      typeof entry?.resolved === "string" &&
      entry.resolved.startsWith("file:")
    ) {
      const matched = [...allowed.values()].some(
        (record) =>
          path.basename(fileTarget(entry.resolved)) === record.filename,
      );
      assert(
        matched,
        `isolated consumer contains unexpected local reference ${entry.resolved}`,
      );
    }
  }
}

export function assertRegistryConsumer({
  manifest,
  lockfile,
  contract,
  evidence,
  roles = Object.keys(contract.packages),
}) {
  const registry = new URL(contract.registry);
  for (const role of roles) {
    const expected = contract.packages[role];
    assert(expected, `unknown registry consumer package role ${role}`);
    const record = evidence.packages?.[role];
    assert(record, `registry evidence missing ${role}`);
    assert.equal(
      manifest.dependencies?.[expected.name],
      expected.version,
      `${expected.name} must use exact registry version`,
    );
    const entry = lockfile.packages?.[`node_modules/${expected.name}`];
    assert(entry, `${expected.name} registry lock entry is missing`);
    assert.equal(
      entry.version,
      expected.version,
      `${expected.name} lock version differs`,
    );
    assert.equal(
      entry.integrity,
      record.integrity,
      `${expected.name} registry integrity differs`,
    );
    assert.notEqual(
      entry.link,
      true,
      `${expected.name} registry package must not be linked`,
    );
    assert.equal(
      typeof entry.resolved,
      "string",
      `${expected.name} registry URL is missing`,
    );
    const resolved = new URL(entry.resolved);
    assert.equal(
      resolved.origin,
      registry.origin,
      `${expected.name} uses unexpected registry`,
    );
  }
  for (const [lockPath, entry] of Object.entries(lockfile.packages ?? {})) {
    assert.notEqual(
      entry?.link,
      true,
      `registry consumer contains link ${lockPath}`,
    );
    assert(
      typeof entry?.resolved !== "string" ||
        !/^(?:file|workspace|link):/i.test(entry.resolved),
      `registry consumer contains local fallback ${entry.resolved}`,
    );
  }
}
