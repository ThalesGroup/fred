import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  copyFile,
  lstat,
  mkdir,
  readFile,
  readdir,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { packDesignTokens } from "./pack-design-tokens.mjs";
import { packIframeSdk } from "./pack-iframe-sdk.mjs";
import { packUi } from "./pack-ui.mjs";
import { run } from "./process.mjs";
import {
  assertReleaseToolchain,
  loadReleaseContract,
  packageRoles,
  validateReleaseContract,
  workspaceRoot,
} from "./release-contract.mjs";
import { releaseContractDigest, sha512Integrity } from "./release-evidence.mjs";

export const fixtureTransferMetadataFilename = "fixture-transfer.json";
const exactVersionPattern = /^\d+\.\d+\.\d+$/;
const integrityPattern = /^sha512-[A-Za-z0-9+/]+={0,2}$/;
const commitPattern = /^[0-9a-f]{40}$/;
const identityPattern = /^[A-Za-z0-9._-]+$/;

function exactKeys(value, expected, label) {
  assert(
    value && typeof value === "object" && !Array.isArray(value),
    `${label} must be an object`,
  );
  assert.deepEqual(
    Object.keys(value).sort(),
    [...expected].sort(),
    `${label} keys`,
  );
}

function assertNonemptyString(value, label) {
  assert.equal(typeof value, "string", `${label} must be a string`);
  assert(value.length > 0, `${label} is required`);
}

function assertSha512Integrity(value, label) {
  assert(integrityPattern.test(value), `${label} is invalid`);
  const encoded = value.slice("sha512-".length);
  const digest = Buffer.from(encoded, "base64");
  assert.equal(digest.byteLength, 64, `${label} is not a SHA-512 digest`);
  assert.equal(encoded, digest.toString("base64"), `${label} is not canonical`);
}

export function fixtureArchiveFilename(name, version) {
  return `${name.replace(/^@/, "").replaceAll("/", "-")}-${version}.tgz`;
}

export function fixtureArtifactName({ sourceCommit, runId, runAttempt }) {
  assert(
    commitPattern.test(sourceCommit),
    "fixture source commit must be a full Git commit",
  );
  assert(identityPattern.test(runId), "fixture run id is invalid");
  assert(/^[1-9]\d*$/.test(runAttempt), "fixture run attempt is invalid");
  return `frontend-packages-fixture-${sourceCommit}-${runId}-${runAttempt}`;
}

export function fixtureExecution({
  provider,
  repository,
  workflow,
  runId,
  runAttempt,
}) {
  const execution = { provider, repository, workflow, runId, runAttempt };
  assertFixtureExecution(execution);
  return execution;
}

function assertFixtureExecution(execution) {
  exactKeys(
    execution,
    ["provider", "repository", "workflow", "runId", "runAttempt"],
    "fixture execution",
  );
  assert(
    ["github-actions", "local-rehearsal"].includes(execution.provider),
    "fixture execution provider is invalid",
  );
  assertNonemptyString(execution.repository, "fixture repository");
  assertNonemptyString(execution.workflow, "fixture workflow");
  assert(identityPattern.test(execution.runId), "fixture run id is invalid");
  assert(
    /^[1-9]\d*$/.test(execution.runAttempt),
    "fixture run attempt is invalid",
  );
}

function assertToolchain(toolchain, label) {
  exactKeys(toolchain, ["node", "npm"], label);
  for (const [name, version] of Object.entries(toolchain))
    assert(exactVersionPattern.test(version), `${label} ${name} must be exact`);
}

function assertPackageRecord(record, role, contract) {
  exactKeys(
    record,
    ["role", "name", "version", "coordinate", "filename", "bytes", "integrity"],
    `${role} transfer package`,
  );
  const expected = contract.packages[role];
  assert.equal(record.role, role, `${role} transfer role differs`);
  assert.equal(record.name, expected.name, `${role} transfer name differs`);
  assert.equal(
    record.version,
    expected.version,
    `${role} transfer version differs`,
  );
  assert.equal(
    record.coordinate,
    `${expected.name}@${expected.version}`,
    `${role} transfer coordinate differs`,
  );
  assert.equal(
    record.filename,
    fixtureArchiveFilename(expected.name, expected.version),
    `${role} transfer filename differs`,
  );
  assert(
    Number.isSafeInteger(record.bytes) && record.bytes > 0,
    `${role} transfer byte length is invalid`,
  );
  assertSha512Integrity(record.integrity, `${role} transfer integrity`);
}

export function validateFixtureTransferMetadata(
  metadata,
  { contract, sourceCommit, sourceTreeClean, execution },
) {
  validateReleaseContract(contract);
  assert.equal(
    contract.state,
    "fixture",
    "fixture transfer requires a fixture contract",
  );
  assertFixtureExecution(execution);
  exactKeys(
    metadata,
    [
      "schemaVersion",
      "kind",
      "artifactName",
      "createdAt",
      "sourceCommit",
      "sourceTreeClean",
      "contract",
      "producerToolchain",
      "execution",
      "producerValidation",
      "packages",
    ],
    "fixture transfer metadata",
  );
  assert.equal(
    metadata.schemaVersion,
    1,
    "unsupported fixture transfer schema",
  );
  assert.equal(
    metadata.kind,
    "fixture-archive-transfer",
    "fixture transfer kind differs",
  );
  assertNonemptyString(metadata.createdAt, "fixture transfer creation time");
  assert.equal(
    new Date(metadata.createdAt).toISOString(),
    metadata.createdAt,
    "fixture transfer creation time is not canonical UTC",
  );
  assert.equal(
    metadata.sourceCommit,
    sourceCommit,
    "fixture transfer source commit differs",
  );
  assert(
    commitPattern.test(metadata.sourceCommit),
    "fixture transfer source commit is invalid",
  );
  assert.equal(
    metadata.sourceTreeClean,
    sourceTreeClean,
    "fixture transfer source-tree state differs",
  );
  assert.equal(typeof metadata.sourceTreeClean, "boolean");
  if (execution.provider === "github-actions")
    assert.equal(
      metadata.sourceTreeClean,
      true,
      "CI fixture transfer requires a clean checkout",
    );
  exactKeys(
    metadata.contract,
    ["state", "digest"],
    "fixture transfer contract",
  );
  assert.equal(
    metadata.contract.state,
    "fixture",
    "fixture transfer contract state differs",
  );
  assert.equal(
    metadata.contract.digest,
    releaseContractDigest(contract),
    "fixture transfer contract digest differs",
  );
  assertToolchain(metadata.producerToolchain, "fixture producer toolchain");
  assert.deepEqual(
    metadata.producerToolchain,
    contract.releaseToolchain,
    "fixture producer toolchain differs from contract",
  );
  assertFixtureExecution(metadata.execution);
  assert.deepEqual(
    metadata.execution,
    execution,
    "fixture transfer execution differs",
  );
  assert.equal(
    metadata.artifactName,
    fixtureArtifactName({ sourceCommit, ...execution }),
    "fixture transfer artifact name differs",
  );
  exactKeys(
    metadata.producerValidation,
    ["archives", "consumers", "browser", "host"],
    "fixture producer validation",
  );
  assert.deepEqual(metadata.producerValidation, {
    archives: true,
    consumers: false,
    browser: false,
    host: false,
  });
  exactKeys(metadata.packages, packageRoles, "fixture transfer packages");
  for (const role of packageRoles)
    assertPackageRecord(metadata.packages[role], role, contract);
  return metadata;
}

async function fileSha256(filePath) {
  return `sha256-${createHash("sha256")
    .update(await readFile(filePath))
    .digest("base64")}`;
}

async function assertRegularFile(filePath, label) {
  const stats = await lstat(filePath);
  assert(
    !stats.isSymbolicLink() && stats.isFile(),
    `${label} must be a regular non-symlink file`,
  );
  return stats;
}

async function resolvedThroughExistingAncestor(target) {
  const missingSegments = [];
  let candidate = target;
  while (true) {
    try {
      const stats = await lstat(candidate);
      if (candidate === target)
        assert(
          !stats.isSymbolicLink(),
          "fixture transfer output must not be a symbolic link",
        );
      return path.resolve(await realpath(candidate), ...missingSegments);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
      const parent = path.dirname(candidate);
      assert.notEqual(
        parent,
        candidate,
        "fixture transfer output has no existing ancestor",
      );
      missingSegments.unshift(path.basename(candidate));
      candidate = parent;
    }
  }
}

function isStrictDescendant(target, parent) {
  const relative = path.relative(parent, target);
  return (
    relative.length > 0 &&
    !relative.startsWith("..") &&
    !path.isAbsolute(relative)
  );
}

function pathsOverlap(target, sensitive) {
  return (
    target === sensitive ||
    isStrictDescendant(target, sensitive) ||
    isStrictDescendant(sensitive, target)
  );
}

function targetDeletes(target, sensitive) {
  return target === sensitive || isStrictDescendant(sensitive, target);
}

export function assertDedicatedFixtureOutput({
  target,
  producerTarget,
  repository,
  producerWorkspace,
  home,
  temporaryRoots,
}) {
  if (isStrictDescendant(target, producerTarget)) return target;
  for (const sensitive of [path.parse(target).root, home, producerTarget])
    assert(
      !targetDeletes(target, sensitive),
      "fixture transfer output overlaps a sensitive repository or filesystem root",
    );
  for (const sensitive of [repository, producerWorkspace])
    assert(
      !pathsOverlap(target, sensitive),
      "fixture transfer output overlaps a sensitive repository or filesystem root",
    );
  assert(
    temporaryRoots.some((temporaryRoot) =>
      isStrictDescendant(target, temporaryRoot),
    ),
    "fixture transfer output must be a dedicated descendant of the producer target or system temporary directory",
  );
  return target;
}

export async function assertSafeFixtureTransferOutput(outputRoot) {
  assertNonemptyString(outputRoot, "fixture transfer output");
  const target = await resolvedThroughExistingAncestor(
    path.resolve(outputRoot),
  );
  const resolvedRoots = {};
  for (const [name, root] of Object.entries({
    producerTarget: path.join(workspaceRoot, "target"),
    repository: path.resolve(workspaceRoot, "../.."),
    producerWorkspace: workspaceRoot,
    home: homedir(),
  }))
    resolvedRoots[name] = await resolvedThroughExistingAncestor(
      path.resolve(root),
    );
  const temporaryRoots = [];
  for (const allowed of [tmpdir(), "/private/tmp"]) {
    try {
      const resolved = await resolvedThroughExistingAncestor(
        path.resolve(allowed),
      );
      if (!temporaryRoots.includes(resolved)) temporaryRoots.push(resolved);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  return assertDedicatedFixtureOutput({
    target,
    ...resolvedRoots,
    temporaryRoots,
  });
}

export async function verifyFixtureTransfer({
  transferRoot,
  contract,
  sourceCommit,
  sourceTreeClean,
  execution,
}) {
  const root = path.resolve(transferRoot);
  const rootStats = await lstat(root);
  assert(
    !rootStats.isSymbolicLink() && rootStats.isDirectory(),
    "fixture transfer root must be a regular non-symlink directory",
  );
  const metadataPath = path.join(root, fixtureTransferMetadataFilename);
  await assertRegularFile(metadataPath, "fixture transfer metadata");
  const metadata = validateFixtureTransferMetadata(
    JSON.parse(await readFile(metadataPath, "utf8")),
    { contract, sourceCommit, sourceTreeClean, execution },
  );
  const expectedFiles = [
    fixtureTransferMetadataFilename,
    ...packageRoles.map((role) => metadata.packages[role].filename),
  ].sort();
  const entries = await readdir(root, { withFileTypes: true });
  assert.deepEqual(
    entries.map(({ name }) => name).sort(),
    expectedFiles,
    "fixture transfer file set differs",
  );
  const archivePaths = {};
  for (const role of packageRoles) {
    const record = metadata.packages[role];
    const archivePath = path.join(root, record.filename);
    const stats = await assertRegularFile(
      archivePath,
      `${role} fixture archive`,
    );
    assert.equal(
      stats.size,
      record.bytes,
      `${role} fixture archive byte length differs`,
    );
    assert.equal(
      await sha512Integrity(archivePath),
      record.integrity,
      `${role} fixture archive integrity differs`,
    );
    archivePaths[role] = archivePath;
  }
  return {
    metadata,
    metadataPath,
    metadataDigest: await fileSha256(metadataPath),
    archivePaths,
    integrities: Object.fromEntries(
      packageRoles.map((role) => [role, metadata.packages[role].integrity]),
    ),
  };
}

export async function createFixtureTransfer({
  outputRoot,
  contract,
  sourceCommit,
  sourceTreeClean,
  producerToolchain,
  execution,
  createdAt = new Date().toISOString(),
  packers = {
    designTokens: packDesignTokens,
    ui: packUi,
    iframeSdk: packIframeSdk,
  },
}) {
  validateReleaseContract(contract);
  assert.equal(
    contract.state,
    "fixture",
    "fixture transfer requires a fixture contract",
  );
  assertReleaseToolchain(contract, producerToolchain);
  assertFixtureExecution(execution);
  assert(
    commitPattern.test(sourceCommit),
    "fixture source commit must be a full Git commit",
  );
  assert.equal(
    typeof sourceTreeClean,
    "boolean",
    "fixture source-tree state is required",
  );
  if (execution.provider === "github-actions")
    assert.equal(
      sourceTreeClean,
      true,
      "CI fixture transfer requires a clean checkout",
    );
  const root = await assertSafeFixtureTransferOutput(outputRoot);
  await rm(root, { recursive: true, force: true });
  await mkdir(root, { recursive: true });
  const packages = {};
  for (const role of ["designTokens", "iframeSdk", "ui"]) {
    const result = await packers[role]({ contract, validate: true });
    const expected = contract.packages[role];
    const filename = fixtureArchiveFilename(expected.name, expected.version);
    assert.equal(
      path.basename(result.archivePath),
      filename,
      `${role} packed filename differs`,
    );
    const target = path.join(root, filename);
    await assertRegularFile(result.archivePath, `${role} packed archive`);
    await copyFile(result.archivePath, target);
    const stats = await assertRegularFile(
      target,
      `${role} transferred archive`,
    );
    packages[role] = {
      role,
      name: expected.name,
      version: expected.version,
      coordinate: `${expected.name}@${expected.version}`,
      filename,
      bytes: stats.size,
      integrity: await sha512Integrity(target),
    };
  }
  const metadata = {
    schemaVersion: 1,
    kind: "fixture-archive-transfer",
    artifactName: fixtureArtifactName({ sourceCommit, ...execution }),
    createdAt,
    sourceCommit,
    sourceTreeClean,
    contract: {
      state: contract.state,
      digest: releaseContractDigest(contract),
    },
    producerToolchain,
    execution,
    producerValidation: {
      archives: true,
      consumers: false,
      browser: false,
      host: false,
    },
    packages,
  };
  validateFixtureTransferMetadata(metadata, {
    contract,
    sourceCommit,
    sourceTreeClean,
    execution,
  });
  await writeFile(
    path.join(root, fixtureTransferMetadataFilename),
    `${JSON.stringify(metadata, null, 2)}\n`,
  );
  await verifyFixtureTransfer({
    transferRoot: root,
    contract,
    sourceCommit,
    sourceTreeClean,
    execution,
  });
  return { outputRoot: root, metadata };
}

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function cliExecution() {
  const github = Boolean(process.env.GITHUB_ACTIONS);
  return fixtureExecution({
    provider: github ? "github-actions" : "local-rehearsal",
    repository:
      optionValue("--repository") ??
      process.env.GITHUB_REPOSITORY ??
      "local/fred",
    workflow:
      optionValue("--workflow") ??
      process.env.GITHUB_WORKFLOW ??
      "local-fixture-transfer",
    runId: optionValue("--run-id") ?? process.env.GITHUB_RUN_ID,
    runAttempt: optionValue("--run-attempt") ?? process.env.GITHUB_RUN_ATTEMPT,
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const outputRoot = optionValue("--output");
  assert(outputRoot, "--output is required");
  const contract = await loadReleaseContract(optionValue("--contract"));
  const [{ stdout: status }, { stdout: commit }, { stdout: npmVersion }] =
    await Promise.all([
      run("git", ["status", "--porcelain"], { cwd: workspaceRoot }),
      run("git", ["rev-parse", "HEAD"], { cwd: workspaceRoot }),
      run("npm", ["--version"], { cwd: workspaceRoot }),
    ]);
  const result = await createFixtureTransfer({
    outputRoot,
    contract,
    sourceCommit: commit.trim(),
    sourceTreeClean: status.trim() === "",
    producerToolchain: { node: process.versions.node, npm: npmVersion.trim() },
    execution: cliExecution(),
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}
