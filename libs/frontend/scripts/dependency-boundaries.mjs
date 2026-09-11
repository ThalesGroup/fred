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
  const target = specifier.slice("file:".length);
  assert(
    !/[\\%?#]/.test(target),
    "candidate file reference must use an unencoded, unambiguous path",
  );
  return target;
}

const dependencyFields = [
  "dependencies",
  "devDependencies",
  "optionalDependencies",
  "peerDependencies",
];

function isLocalReference(specifier) {
  return (
    typeof specifier === "string" &&
    (/^(?:file|workspace|link):/i.test(specifier) ||
      specifier.startsWith("./") ||
      specifier.startsWith("../") ||
      path.isAbsolute(specifier))
  );
}

function packageNameFromLockPath(lockPath) {
  const marker = "node_modules/";
  const index = lockPath.lastIndexOf(marker);
  if (index === -1) return undefined;
  const segments = lockPath.slice(index + marker.length).split("/");
  const length = segments[0]?.startsWith("@") ? 2 : 1;
  if (segments.length !== length) return undefined;
  return segments.slice(0, length).join("/");
}

function dependencyEntryPaths(lockPath, packageName) {
  const paths = [];
  let parent = lockPath;
  while (true) {
    paths.push(
      parent
        ? `${parent}/node_modules/${packageName}`
        : `node_modules/${packageName}`,
    );
    const nestedIndex = parent.lastIndexOf("/node_modules/");
    if (nestedIndex !== -1) parent = parent.slice(0, nestedIndex);
    else if (parent.startsWith("node_modules/")) parent = "";
    else break;
  }
  return paths;
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
    assert(separator > 0, `invalid candidate coordinate ${record.coordinate}`);
    const name = record.coordinate.slice(0, separator);
    assert(!allowed.has(name), `duplicate candidate identity ${name}`);
    allowed.set(name, {
      ...record,
      version: record.coordinate.slice(separator + 1),
    });
  }

  async function validateReference(name, specifier, integrity) {
    const record = allowed.get(name);
    assert(record, `unapproved local dependency identity ${name}`);
    assert.equal(
      typeof specifier,
      "string",
      `${name} local dependency reference is missing`,
    );
    assert(
      specifier.startsWith("file:"),
      `${name} local dependency must use an approved file: tarball`,
    );
    await validateCandidateTarballReference({
      specifier,
      consumerRoot,
      expectedFilename: record.filename,
      expectedIntegrity: record.integrity,
    });
    if (integrity !== undefined)
      assert.equal(
        integrity,
        record.integrity,
        `${name} lock integrity differs`,
      );
    return record;
  }

  const rootLock = lockfile.packages?.[""] ?? {};
  for (const name of allowed.keys()) {
    const manifestReference = manifest.dependencies?.[name];
    const lockReference = rootLock.dependencies?.[name];
    assert.equal(
      manifestReference,
      lockReference,
      `${name} manifest/lock reference differs`,
    );
    await validateReference(name, manifestReference);
    const installed = lockfile.packages?.[`node_modules/${name}`];
    assert(installed, `${name} lock entry is missing`);
    assert.equal(
      installed.link,
      undefined,
      `${name} must not be a consumer link`,
    );
    await validateReference(name, installed.resolved, installed.integrity);
  }

  for (const field of dependencyFields) {
    const manifestDependencies = manifest[field] ?? {};
    const rootDependencies = rootLock[field] ?? {};
    for (const [name, specifier] of Object.entries(manifestDependencies)) {
      if (!isLocalReference(specifier)) continue;
      assert.equal(
        rootDependencies[name],
        specifier,
        `${name} ${field} manifest/lock reference differs`,
      );
      await validateReference(name, specifier);
    }
    for (const [name, specifier] of Object.entries(rootDependencies)) {
      if (!isLocalReference(specifier)) continue;
      assert.equal(
        manifestDependencies[name],
        specifier,
        `${name} ${field} lock/manifest reference differs`,
      );
      await validateReference(name, specifier);
    }
  }

  for (const [lockPath, entry] of Object.entries(lockfile.packages ?? {})) {
    assert.notEqual(
      entry?.link,
      true,
      `isolated consumer contains link ${lockPath}`,
    );
    if (isLocalReference(entry?.resolved)) {
      const name = packageNameFromLockPath(lockPath);
      assert(name, `local lock entry has no package identity ${lockPath}`);
      const record = await validateReference(
        name,
        entry.resolved,
        entry.integrity,
      );
      assert.equal(
        entry.version,
        record.version,
        `${name} lock version differs`,
      );
    }
    if (isLocalReference(entry?.version)) {
      const name = packageNameFromLockPath(lockPath);
      assert(name, `local lock version has no package identity ${lockPath}`);
      await validateReference(name, entry.version, entry.integrity);
    }
    for (const field of dependencyFields) {
      for (const [name, specifier] of Object.entries(entry?.[field] ?? {})) {
        if (!isLocalReference(specifier)) continue;
        await validateReference(name, specifier);
        const installedPath = dependencyEntryPaths(lockPath, name).find(
          (candidate) => lockfile.packages?.[candidate],
        );
        assert(
          installedPath,
          `${name} local ${field} lock entry is missing from ${lockPath || "root"}`,
        );
        const installed = lockfile.packages[installedPath];
        await validateReference(name, installed.resolved, installed.integrity);
      }
    }
  }
}

export async function installAfterOfflineReferenceValidation({
  manifest,
  lockfile,
  consumerRoot,
  evidence,
  installDependencies,
}) {
  assert.equal(
    typeof installDependencies,
    "function",
    "offline dependency installer is required",
  );
  await assertOfflineConsumerReferences({
    manifest,
    lockfile,
    consumerRoot,
    evidence,
  });
  return installDependencies();
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
