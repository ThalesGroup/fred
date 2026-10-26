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
import { createHash } from "node:crypto";
import {
  cp,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import semver from "semver";

import { runBrowserSmoke } from "./browser-smoke.mjs";
import { stageIsolatedConsumer } from "./isolated-consumer.mjs";
import { stageIsolatedIframeSdkConsumer } from "./isolated-iframe-sdk-consumer.mjs";
import { stageIsolatedReactConsumer } from "./isolated-react-consumer.mjs";
import { packDesignTokens } from "./pack-design-tokens.mjs";
import { packIframeSdk } from "./pack-iframe-sdk.mjs";
import { packUi } from "./pack-ui.mjs";
import { run } from "./process.mjs";
import { consumerCache } from "./provision-react-consumer.mjs";
import { loadReleaseContract } from "./release-contract.mjs";
import { sha512Integrity } from "./release-evidence.mjs";
import {
  approvedRegistry,
  readReleaseInputs,
  registryRoot,
} from "./release-operation-inputs.mjs";
import {
  assertReleaseToolchain,
  loadReleaseToolchain,
} from "./release-toolchain.mjs";

export {
  parseDryRun,
  readReleaseInputs,
  registryRoot,
} from "./release-operation-inputs.mjs";

export const workspaceRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
export const metadataFilename = "release.json";
export const outcomeFilename = "publish-result.json";

export const releasePackages = Object.freeze({
  "design-tokens": {
    id: "designTokens",
    pack: packDesignTokens,
    workspace: "design-tokens",
  },
  ui: { id: "ui", pack: packUi, workspace: "ui" },
  "iframe-sdk": {
    id: "iframeSdk",
    pack: packIframeSdk,
    workspace: "iframe-sdk",
  },
});

const sourceCommitPattern = /^[a-f0-9]{40}$/;
const integrityPattern = /^sha512-[A-Za-z0-9+/]{86}==$/;
const channelPattern = /^[a-z0-9][a-z0-9._-]*$/;
const maximumRegistryArchiveBytes = 50 * 1024 * 1024;

export class ReleaseError extends Error {
  constructor(code, message, options) {
    super(message, options);
    this.name = "ReleaseError";
    this.code = code;
  }
}

function releaseError(code, message, options) {
  return new ReleaseError(code, message, options);
}

export function selectPackage(packageName) {
  const selected = releasePackages[packageName];
  if (!selected)
    throw releaseError(
      "invalid-package",
      `PACKAGE must be exactly one of: ${Object.keys(releasePackages).join(", ")}`,
    );
  return { package: packageName, ...selected };
}

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

async function readManifest(selected, root = workspaceRoot) {
  const manifest = JSON.parse(
    await readFile(path.join(root, selected.workspace, "package.json"), "utf8"),
  );
  assert.equal(
    manifest.private,
    undefined,
    `${selected.package} must be publishable`,
  );
  assert.equal(
    typeof manifest.name,
    "string",
    `${selected.package} name is missing`,
  );
  assert(
    semver.valid(manifest.version),
    `${selected.package} version is invalid`,
  );
  return manifest;
}

function preparedBy(environment) {
  if (environment.GITHUB_ACTIONS !== "true") return { kind: "local" };
  for (const field of [
    "GITHUB_REPOSITORY",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_RUN_ID",
  ])
    assert(environment[field], `${field} is required for GitHub preparation`);
  return {
    kind: "github-actions",
    repository: environment.GITHUB_REPOSITORY,
    workflow: environment.GITHUB_WORKFLOW_REF,
    runId: environment.GITHUB_RUN_ID,
  };
}

export function defaultReleaseDirectory({ package: packageName }, version) {
  return path.join(workspaceRoot, "target", "releases", packageName, version);
}

function validateReleaseMetadata(metadata) {
  exactKeys(
    metadata,
    [
      "schemaVersion",
      "package",
      "name",
      "version",
      "sourceCommit",
      "archive",
      "integrity",
      "preparedBy",
    ],
    "release metadata",
  );
  assert.equal(
    metadata.schemaVersion,
    1,
    "unsupported release metadata schema",
  );
  const selected = selectPackage(metadata.package);
  assert.equal(
    typeof metadata.name,
    "string",
    "release package name is missing",
  );
  assert(semver.valid(metadata.version), "release package version is invalid");
  assert(
    sourceCommitPattern.test(metadata.sourceCommit),
    "source commit is invalid",
  );
  assert.match(
    metadata.archive,
    /^[a-zA-Z0-9._-]+\.tgz$/,
    "archive filename is invalid",
  );
  assert.match(
    metadata.integrity,
    integrityPattern,
    "archive integrity is invalid",
  );
  assert(
    metadata.preparedBy && typeof metadata.preparedBy === "object",
    "preparation identity is missing",
  );
  if (metadata.preparedBy.kind === "local")
    exactKeys(metadata.preparedBy, ["kind"], "local preparation identity");
  else if (metadata.preparedBy.kind === "github-actions") {
    exactKeys(
      metadata.preparedBy,
      ["kind", "repository", "workflow", "runId"],
      "GitHub preparation identity",
    );
    for (const field of ["repository", "workflow", "runId"])
      assert(metadata.preparedBy[field], `preparedBy.${field} is required`);
  } else throw releaseError("invalid-metadata", "unknown preparation identity");
  return selected;
}

async function packedManifest(archivePath, runCommand = run) {
  const { stdout } = await runCommand("tar", [
    "-xOf",
    archivePath,
    "package/package.json",
  ]);
  try {
    return JSON.parse(stdout);
  } catch (error) {
    throw releaseError(
      "invalid-archive",
      "packed package manifest is malformed",
      {
        cause: error,
      },
    );
  }
}

export async function validateReleaseDirectory({
  packageName,
  releaseDirectory,
  root = workspaceRoot,
  runCommand = run,
  hashArchive = sha512Integrity,
}) {
  const selected = selectPackage(packageName);
  const manifest = await readManifest(selected, root);
  const directory = path.resolve(
    releaseDirectory ?? defaultReleaseDirectory(selected, manifest.version),
  );
  const metadata = JSON.parse(
    await readFile(path.join(directory, metadataFilename), "utf8"),
  );
  const metadataPackage = validateReleaseMetadata(metadata);
  assert.equal(
    metadataPackage.package,
    packageName,
    "release package selector differs",
  );
  assert.equal(
    metadata.name,
    manifest.name,
    "release package name differs from manifest",
  );
  assert.equal(
    metadata.version,
    manifest.version,
    "release package version differs from manifest",
  );
  const allowed = new Set([
    metadataFilename,
    metadata.archive,
    outcomeFilename,
  ]);
  const entries = await readdir(directory, { withFileTypes: true });
  for (const entry of entries)
    assert(
      entry.isFile() && allowed.has(entry.name),
      `unexpected release file ${entry.name}`,
    );
  assert(
    entries.some(({ name }) => name === metadata.archive),
    "release archive is missing",
  );
  const archivePath = path.join(directory, metadata.archive);
  assert.equal(
    await hashArchive(archivePath),
    metadata.integrity,
    "prepared archive integrity differs",
  );
  const archiveManifest = await packedManifest(archivePath, runCommand);
  assert.equal(
    archiveManifest.name,
    metadata.name,
    "packed package name differs",
  );
  assert.equal(
    archiveManifest.version,
    metadata.version,
    "packed package version differs",
  );
  return {
    archiveManifest,
    archivePath,
    directory,
    manifest,
    metadata,
    selected,
  };
}

function approvedTarballEndpoint({ name, registry, tarball, version }) {
  const root = approvedRegistry(registry);
  let endpoint;
  try {
    endpoint = new URL(tarball);
  } catch (error) {
    throw releaseError(
      "registry-malformed",
      "registry tarball URL is invalid",
      {
        cause: error,
      },
    );
  }
  const expected = new URL(
    `${name}/-/${name.split("/").at(-1)}-${version}.tgz`,
    root,
  );
  if (
    endpoint.username ||
    endpoint.password ||
    endpoint.search ||
    endpoint.hash ||
    endpoint.href !== expected.href
  )
    throw releaseError(
      "registry-tarball",
      `${name}@${version} registry tarball URL is outside the approved exact-version path`,
    );
  return endpoint;
}

function registryPackagePath(name) {
  return encodeURIComponent(name).replace(/^%40/, "@").replaceAll("%2F", "%2f");
}

function registryTransportError(error, label, subject = "registry") {
  const timeout =
    error?.name === "TimeoutError" || error?.name === "AbortError";
  return releaseError(
    timeout ? "registry-timeout" : "registry-network",
    `${label} ${subject} ${timeout ? "timed out" : "network request failed"}`,
    { cause: error },
  );
}

async function registryJson({
  endpoint,
  fetchImpl,
  label,
  timeoutMilliseconds,
}) {
  let response;
  try {
    response = await fetchImpl(endpoint, {
      headers: { accept: "application/json" },
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMilliseconds),
    });
  } catch (error) {
    throw registryTransportError(error, label);
  }
  if (response.url && response.url !== endpoint.href)
    throw releaseError(
      "registry-redirect",
      `${label} registry response URL differs from the requested endpoint`,
    );
  if (response.status === 401)
    throw releaseError(
      "registry-authentication",
      `${label} registry authentication failed`,
    );
  if (response.status === 403)
    throw releaseError(
      "registry-authorization",
      `${label} registry authorization failed`,
    );
  if (response.status === 404) return null;
  if (response.status >= 300 && response.status < 400)
    throw releaseError(
      "registry-redirect",
      `${label} registry redirect is forbidden`,
    );
  if (!response.ok)
    throw releaseError(
      "registry-response",
      `${label} registry request failed with HTTP ${response.status}`,
    );
  try {
    return await response.json();
  } catch (error) {
    if (error?.name === "TimeoutError" || error?.name === "AbortError")
      throw registryTransportError(error, label);
    if (!(error instanceof SyntaxError))
      throw registryTransportError(error, label);
    throw releaseError(
      "registry-malformed",
      `${label} registry returned malformed JSON`,
      {
        cause: error,
      },
    );
  }
}

async function registryBytes({
  endpoint,
  fetchImpl,
  label,
  maximumBytes = maximumRegistryArchiveBytes,
  timeoutMilliseconds,
}) {
  let response;
  try {
    response = await fetchImpl(endpoint, {
      headers: { accept: "application/octet-stream" },
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMilliseconds),
    });
  } catch (error) {
    throw registryTransportError(error, label, "registry tarball");
  }
  if (response.url && response.url !== endpoint.href)
    throw releaseError(
      "registry-redirect",
      `${label} registry tarball response URL differs from the requested endpoint`,
    );
  if (response.status === 401)
    throw releaseError(
      "registry-authentication",
      `${label} registry tarball authentication failed`,
    );
  if (response.status === 403)
    throw releaseError(
      "registry-authorization",
      `${label} registry tarball authorization failed`,
    );
  if (response.status >= 300 && response.status < 400)
    throw releaseError(
      "registry-redirect",
      `${label} registry tarball redirect is forbidden`,
    );
  if (!response.ok)
    throw releaseError(
      "registry-response",
      `${label} registry tarball request failed with HTTP ${response.status}`,
    );
  const declaredLength = response.headers?.get?.("content-length");
  if (
    declaredLength !== null &&
    declaredLength !== undefined &&
    (!/^\d+$/.test(declaredLength) || Number(declaredLength) > maximumBytes)
  )
    throw releaseError(
      "registry-tarball",
      `${label} registry tarball exceeds the download limit`,
    );
  try {
    if (response.body?.getReader) {
      const reader = response.body.getReader();
      const chunks = [];
      let length = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        length += value.byteLength;
        if (length > maximumBytes) {
          await reader.cancel();
          throw releaseError(
            "registry-tarball",
            `${label} registry tarball exceeds the download limit`,
          );
        }
        chunks.push(Buffer.from(value));
      }
      return Buffer.concat(chunks, length);
    }
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.byteLength > maximumBytes)
      throw releaseError(
        "registry-tarball",
        `${label} registry tarball exceeds the download limit`,
      );
    return bytes;
  } catch (error) {
    if (error instanceof ReleaseError) throw error;
    throw registryTransportError(error, label, "registry tarball");
  }
}

function bytesIntegrity(bytes) {
  return `sha512-${createHash("sha512").update(bytes).digest("base64")}`;
}

export async function inspectExactVersion({
  name,
  version,
  integrity,
  registry = registryRoot,
  fetchImpl = fetch,
  timeoutMilliseconds = 10_000,
}) {
  const root = approvedRegistry(registry);
  const endpoint = new URL(
    `${registryPackagePath(name)}/${encodeURIComponent(version)}`,
    root,
  );
  const coordinate = `${name}@${version}`;
  const metadata = await registryJson({
    endpoint,
    fetchImpl,
    label: coordinate,
    timeoutMilliseconds,
  });
  if (!metadata) return { state: "absent" };
  if (metadata.name !== name || metadata.version !== version)
    throw releaseError(
      "registry-identity",
      `${coordinate} registry identity differs`,
    );
  if (!integrity) return { metadata, state: "present" };
  const actual = metadata.dist?.integrity;
  if (!integrityPattern.test(actual ?? ""))
    throw releaseError(
      "registry-malformed",
      `${coordinate} registry integrity is missing`,
    );
  const tarballEndpoint = approvedTarballEndpoint({
    name,
    registry,
    tarball: metadata.dist?.tarball,
    version,
  });
  const archive = await registryBytes({
    endpoint: tarballEndpoint,
    fetchImpl,
    label: coordinate,
    timeoutMilliseconds,
  });
  const downloadedIntegrity = bytesIntegrity(archive);
  if (downloadedIntegrity !== actual)
    throw releaseError(
      "registry-integrity",
      `${coordinate} registry tarball bytes differ from registry metadata`,
    );
  return actual === integrity
    ? { downloadedIntegrity, metadata, state: "matching" }
    : {
        actualIntegrity: actual,
        downloadedIntegrity,
        metadata,
        state: "conflict",
      };
}

export async function resolveUiDesignTokens({
  manifest,
  contract,
  registry = registryRoot,
  fetchImpl = fetch,
  timeoutMilliseconds = 10_000,
}) {
  const tokenName = contract.packages.designTokens.name;
  const range = manifest.peerDependencies?.[tokenName];
  assert.equal(
    typeof range,
    "string",
    `UI must declare ${tokenName} as a peer`,
  );
  assert(semver.validRange(range), `UI ${tokenName} peer range is invalid`);
  const root = approvedRegistry(registry);
  const endpoint = new URL(registryPackagePath(tokenName), root);
  const metadata = await registryJson({
    endpoint,
    fetchImpl,
    label: tokenName,
    timeoutMilliseconds,
  });
  if (!metadata)
    throw releaseError(
      "dependency-unavailable",
      `No published ${tokenName} version satisfies ${range}; publish design-tokens first`,
    );
  assert.equal(
    metadata.name,
    tokenName,
    `${tokenName} registry identity differs`,
  );
  assert(
    metadata.versions &&
      typeof metadata.versions === "object" &&
      !Array.isArray(metadata.versions),
    `${tokenName} registry versions are malformed`,
  );
  const version = semver.maxSatisfying(Object.keys(metadata.versions), range);
  if (!version)
    throw releaseError(
      "dependency-unavailable",
      `No published ${tokenName} version satisfies ${range}; publish design-tokens first`,
    );
  const selected = metadata.versions[version];
  assert.equal(
    selected.name,
    tokenName,
    `${tokenName}@${version} identity differs`,
  );
  assert.equal(
    selected.version,
    version,
    `${tokenName}@${version} version differs`,
  );
  assert.match(
    selected.dist?.integrity ?? "",
    integrityPattern,
    `${tokenName}@${version} integrity is missing`,
  );
  const tarball = approvedTarballEndpoint({
    name: tokenName,
    registry,
    tarball: selected.dist?.tarball,
    version,
  }).href;
  const archiveBytes = await registryBytes({
    endpoint: new URL(tarball),
    fetchImpl,
    label: `${tokenName}@${version}`,
    timeoutMilliseconds,
  });
  if (bytesIntegrity(archiveBytes) !== selected.dist.integrity)
    throw releaseError(
      "registry-integrity",
      `${tokenName}@${version} downloaded tarball integrity differs from registry metadata`,
    );
  return {
    archiveBytes,
    coordinate: `${tokenName}@${version}`,
    integrity: selected.dist.integrity,
    range,
    registry: root.href,
    tarball,
  };
}

export async function withCachedVerifiedUiToken({
  uiToken,
  action,
  cachePath = consumerCache,
  runCommand = run,
}) {
  assert.equal(typeof action, "function", "verified token action is required");
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-ui-published-token-"),
  );
  try {
    const tokenArchivePath = path.join(
      temporary,
      path.basename(new URL(uiToken.tarball).pathname),
    );
    await writeFile(tokenArchivePath, uiToken.archiveBytes, { flag: "wx" });
    assert.equal(
      await sha512Integrity(tokenArchivePath),
      uiToken.integrity,
      "verified UI token archive changed before cache population",
    );
    await runCommand(
      "npm",
      [
        "cache",
        "add",
        tokenArchivePath,
        "--cache",
        cachePath,
        "--ignore-scripts",
      ],
      { cwd: workspaceRoot },
    );
    return await action(tokenArchivePath);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

async function defaultChecks({
  selected,
  contract,
  archivePath,
  integrity,
  uiToken,
}) {
  const stageRoot = path.join(
    workspaceRoot,
    "target",
    "release-consumers",
    selected.package,
  );
  if (selected.package === "design-tokens") {
    await stageIsolatedConsumer({
      archivePath,
      contract,
      expectedIntegrity: integrity,
      stagedOutputPath: path.join(stageRoot, "tokens"),
    });
    await runBrowserSmoke({
      checks: ["tokens", "fonts"],
      tokenOutput: path.join(stageRoot, "tokens"),
    });
  } else if (selected.package === "ui") {
    await withCachedVerifiedUiToken({
      uiToken,
      action: async (tokenArchivePath) => {
        await stageIsolatedReactConsumer({
          contract,
          expectedIntegrities: { ui: integrity },
          publishedToken: uiToken,
          publishedTokenArchivePath: tokenArchivePath,
          stagedOutputPath: path.join(stageRoot, "react"),
          uiArchivePath: archivePath,
        });
        await runBrowserSmoke({
          checks: ["ui"],
          reactOutput: path.join(stageRoot, "react"),
        });
      },
    });
  } else {
    await stageIsolatedIframeSdkConsumer({
      archivePath,
      contract,
      expectedIntegrity: integrity,
      stagedOutputPath: path.join(stageRoot, "iframe-sdk"),
    });
    await runBrowserSmoke({
      checks: ["iframeSdk"],
      iframeSdkOutput: path.join(stageRoot, "iframe-sdk"),
      productionHostCompatibility: false,
    });
  }
}

export async function prepareRelease({
  packageName,
  releaseDirectory,
  root = workspaceRoot,
  environment = process.env,
  runCommand = run,
  hashArchive = sha512Integrity,
  loadContract = loadReleaseContract,
  runChecks = defaultChecks,
  pack = selectPackage(packageName).pack,
  fetchImpl = fetch,
  registry = registryRoot,
  nodeVersion = process.versions.node,
  assertToolchain = assertReleaseToolchain,
  loadToolchain = loadReleaseToolchain,
}) {
  const selected = selectPackage(packageName);
  approvedRegistry(registry);
  const expectedToolchain = await loadToolchain();
  const { stdout: npmVersion } = await runCommand("npm", ["--version"], {
    cwd: root,
  });
  assertToolchain(expectedToolchain, {
    node: nodeVersion,
    npm: npmVersion.trim(),
  });
  const manifest = await readManifest(selected, root);
  const contract = await loadContract();
  assert.deepEqual(
    contract.releaseToolchain,
    expectedToolchain,
    "validated release toolchain differs from the full contract",
  );
  const [{ stdout: status }, { stdout: commit }] = await Promise.all([
    runCommand("git", ["status", "--porcelain", "--untracked-files=all"], {
      cwd: root,
    }),
    runCommand("git", ["rev-parse", "HEAD"], { cwd: root }),
  ]);
  if (status.trim())
    throw releaseError(
      "dirty-source",
      "release preparation requires a clean committed checkout",
    );
  const sourceCommit = commit.trim();
  assert(sourceCommitPattern.test(sourceCommit), "source commit is invalid");
  const uiToken =
    packageName === "ui"
      ? await resolveUiDesignTokens({ contract, fetchImpl, manifest, registry })
      : undefined;
  const { archivePath } = await pack({ contract, validate: true });
  const integrity = await hashArchive(archivePath);
  await runChecks({
    archivePath,
    contract,
    integrity,
    registry,
    selected,
    uiToken,
  });
  assert.equal(
    await hashArchive(archivePath),
    integrity,
    "archive changed during checks",
  );
  const [{ stdout: finalStatus }, { stdout: finalCommit }] = await Promise.all([
    runCommand("git", ["status", "--porcelain", "--untracked-files=all"], {
      cwd: root,
    }),
    runCommand("git", ["rev-parse", "HEAD"], { cwd: root }),
  ]);
  if (finalStatus.trim())
    throw releaseError(
      "dirty-source",
      "release source changed during preparation",
    );
  assert.equal(
    finalCommit.trim(),
    sourceCommit,
    "source commit changed during preparation",
  );
  const directory = path.resolve(
    releaseDirectory ?? defaultReleaseDirectory(selected, manifest.version),
  );
  await mkdir(directory, { recursive: true });
  const existing = await readdir(directory);
  assert.equal(
    existing.length,
    0,
    `release directory is not empty: ${directory}`,
  );
  const target = path.join(directory, path.basename(archivePath));
  await cp(archivePath, target, { errorOnExist: true, force: false });
  const metadata = {
    schemaVersion: 1,
    package: packageName,
    name: manifest.name,
    version: manifest.version,
    sourceCommit,
    archive: path.basename(target),
    integrity,
    preparedBy: preparedBy(environment),
  };
  await writeFile(
    path.join(directory, metadataFilename),
    `${JSON.stringify(metadata, null, 2)}\n`,
    { flag: "wx" },
  );
  return validateReleaseDirectory({
    packageName,
    releaseDirectory: directory,
    root,
    runCommand,
    hashArchive,
  });
}

export function assertAuthentication({
  authMode,
  dryRun,
  environment,
  checkedOutCommit = environment.GITHUB_SHA,
  metadata,
  operation,
}) {
  assert(
    ["local", "token", "oidc"].includes(authMode),
    "AUTH_MODE must be local, token, or oidc",
  );
  const hasToken = Boolean(
    environment.NODE_AUTH_TOKEN || environment.NPM_TOKEN,
  );
  const hasOidcCredential = Boolean(
    environment.ACTIONS_ID_TOKEN_REQUEST_URL ||
    environment.ACTIONS_ID_TOKEN_REQUEST_TOKEN ||
    environment.NPM_ID_TOKEN ||
    environment.SIGSTORE_ID_TOKEN,
  );
  if (authMode === "local") {
    if (environment.CI && environment.CI !== "false")
      throw releaseError(
        "authentication",
        "CI must select token or oidc authentication explicitly",
      );
    if (hasToken || hasOidcCredential)
      throw releaseError(
        "authentication",
        "local authentication cannot be combined with token or OIDC credentials",
      );
    return { provenance: false };
  }
  if (!environment.CI || environment.CI === "false")
    throw releaseError(
      "authentication",
      `${authMode} authentication requires CI=true`,
    );
  if (authMode === "token") {
    if (hasOidcCredential)
      throw releaseError(
        "authentication",
        "token authentication cannot be combined with OIDC credentials",
      );
    if (!dryRun && !environment.NODE_AUTH_TOKEN)
      throw releaseError(
        "authentication",
        "token authentication requires NODE_AUTH_TOKEN",
      );
    if (
      environment.NODE_AUTH_TOKEN?.includes("\n") ||
      environment.NODE_AUTH_TOKEN?.includes("\r")
    )
      throw releaseError("authentication", "NODE_AUTH_TOKEN is malformed");
    return { provenance: false };
  }
  if (hasToken)
    throw releaseError(
      "authentication",
      "OIDC authentication cannot be combined with npm token credentials",
    );
  if (environment.NPM_ID_TOKEN || environment.SIGSTORE_ID_TOKEN)
    throw releaseError(
      "authentication",
      "GitHub OIDC authentication cannot be combined with alternate ID-token credentials",
    );
  if (operation !== "publish")
    throw releaseError(
      "authentication",
      "OIDC authentication is supported only for publication",
    );
  for (const field of [
    "GITHUB_ACTIONS",
    "GITHUB_REPOSITORY",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_SHA",
  ])
    if (!environment[field])
      throw releaseError(
        "authentication",
        `OIDC authentication requires ${field}`,
      );
  if (!dryRun)
    for (const field of [
      "ACTIONS_ID_TOKEN_REQUEST_URL",
      "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    ])
      if (!environment[field])
        throw releaseError(
          "authentication",
          `OIDC authentication requires ${field}`,
        );
  if (environment.GITHUB_ACTIONS !== "true")
    throw releaseError(
      "authentication",
      "OIDC authentication requires GitHub Actions",
    );
  if (metadata.preparedBy.kind !== "github-actions")
    throw releaseError(
      "provenance",
      "OIDC provenance cannot describe a release prepared outside GitHub Actions",
    );
  if (checkedOutCommit !== metadata.sourceCommit)
    throw releaseError(
      "provenance",
      "checked-out publishing source differs from the prepared source commit",
    );
  if (environment.GITHUB_SHA !== metadata.sourceCommit)
    throw releaseError(
      "provenance",
      "GitHub workflow source differs from the prepared source commit; use explicit local or token authentication for these unchanged bytes",
    );
  if (environment.GITHUB_REPOSITORY !== metadata.preparedBy.repository)
    throw releaseError(
      "provenance",
      "publishing repository differs from the preparation repository",
    );
  if (environment.GITHUB_WORKFLOW_REF !== metadata.preparedBy.workflow)
    throw releaseError(
      "provenance",
      "publishing workflow differs from the preparation workflow",
    );
  return { provenance: true };
}

function registryAuthKey(registry) {
  const url = approvedRegistry(registry);
  return `//${url.host}${url.pathname}:_authToken`;
}

async function mutationAuthentication({ authMode, environment, registry }) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "fred-npm-auth-"));
  const logsDirectory = path.join(directory, "logs");
  await mkdir(logsDirectory);
  const failureDetails = async () => {
    const entries = await readdir(logsDirectory, { withFileTypes: true });
    return (
      await Promise.all(
        entries
          .filter((entry) => entry.isFile())
          .map((entry) =>
            readFile(path.join(logsDirectory, entry.name), "utf8"),
          ),
      )
    ).join("\n");
  };
  if (authMode === "local")
    return {
      cleanup: () => rm(directory, { force: true, recursive: true }),
      environment: { ...environment, NPM_CONFIG_LOGS_DIR: logsDirectory },
      failureDetails,
      interactive: true,
    };
  const userConfig = path.join(directory, "npmrc");
  const globalConfig = path.join(directory, "global-npmrc");
  try {
    await Promise.all([
      writeFile(
        userConfig,
        authMode === "token"
          ? `${registryAuthKey(registry)}=\${NODE_AUTH_TOKEN}\n`
          : "",
        { mode: 0o600 },
      ),
      writeFile(globalConfig, "", { mode: 0o600 }),
    ]);
  } catch (error) {
    await rm(directory, { force: true, recursive: true });
    throw error;
  }
  const isolated = {
    ...environment,
    NPM_CONFIG_GLOBALCONFIG: globalConfig,
    NPM_CONFIG_LOGS_DIR: logsDirectory,
    NPM_CONFIG_USERCONFIG: userConfig,
  };
  delete isolated.npm_config_globalconfig;
  delete isolated.npm_config_userconfig;
  for (const key of Object.keys(isolated))
    if (/^npm_config_.*(?:auth|token)/i.test(key)) delete isolated[key];
  if (authMode === "token") {
    delete isolated.ACTIONS_ID_TOKEN_REQUEST_URL;
    delete isolated.ACTIONS_ID_TOKEN_REQUEST_TOKEN;
    delete isolated.NPM_ID_TOKEN;
    delete isolated.SIGSTORE_ID_TOKEN;
  } else {
    delete isolated.NODE_AUTH_TOKEN;
    delete isolated.NPM_TOKEN;
    delete isolated.NPM_ID_TOKEN;
    delete isolated.SIGSTORE_ID_TOKEN;
  }
  return {
    cleanup: () => rm(directory, { force: true, recursive: true }),
    environment: isolated,
    failureDetails,
    interactive: false,
  };
}

function definiteNpmFailure(error) {
  const details = [];
  for (let current = error; current; current = current.cause) {
    for (const value of [
      current.code,
      current.message,
      current.npmLog,
      current.stdout,
      current.stderr,
    ])
      if (value !== undefined) details.push(String(value));
  }
  const detail = details.join("\n");
  if (/\b(?:E401|ENEEDAUTH|EOTP)\b|\b401\b/.test(detail))
    return releaseError(
      "registry-authentication",
      "npm registry authentication failed before publication",
      { cause: error },
    );
  if (/\bE403\b|\b403\b/.test(detail))
    return releaseError(
      "registry-authorization",
      "npm registry authorization failed before publication",
      { cause: error },
    );
  return null;
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", `'"'"'`)}'`;
}

function verificationCommand(packageName, directory, registry) {
  return `make verify-release PACKAGE=${shellQuote(packageName)} RELEASE_DIR=${shellQuote(directory)} REGISTRY=${shellQuote(registry)}`;
}

async function writeOutcome(release, registry, state, detail = {}) {
  const outcome = {
    schemaVersion: 1,
    state,
    package: release.metadata.package,
    name: release.metadata.name,
    version: release.metadata.version,
    integrity: release.metadata.integrity,
    registry,
    verificationCommand: verificationCommand(
      release.metadata.package,
      release.directory,
      registry,
    ),
    ...detail,
  };
  await writeFile(
    path.join(release.directory, outcomeFilename),
    `${JSON.stringify(outcome, null, 2)}\n`,
  );
  return outcome;
}

export async function publishRelease({
  packageName,
  releaseDirectory,
  root = workspaceRoot,
  authMode = "local",
  dryRun = false,
  environment = process.env,
  registry = registryRoot,
  fetchImpl = fetch,
  runCommand = run,
  inspect = inspectExactVersion,
  wait = (milliseconds) =>
    new Promise((resolve) => setTimeout(resolve, milliseconds)),
  visibilityAttempts = 6,
  visibilityDelayMilliseconds = 5_000,
  loadContract = loadReleaseContract,
}) {
  const release = await validateReleaseDirectory({
    packageName,
    releaseDirectory,
    root,
    runCommand,
  });
  approvedRegistry(registry);
  const checkedOutCommit =
    authMode === "oidc"
      ? (
          await runCommand("git", ["rev-parse", "HEAD"], { cwd: root })
        ).stdout.trim()
      : undefined;
  const auth = assertAuthentication({
    authMode,
    checkedOutCommit,
    dryRun,
    environment,
    metadata: release.metadata,
    operation: "publish",
  });
  if (packageName === "ui")
    await resolveUiDesignTokens({
      contract: await loadContract(),
      fetchImpl,
      manifest: release.archiveManifest,
      registry,
    });
  const candidate = {
    name: release.metadata.name,
    version: release.metadata.version,
    integrity: release.metadata.integrity,
    registry,
    fetchImpl,
  };
  const preflight = await inspect(candidate);
  if (preflight.state === "matching")
    return writeOutcome(release, registry, "already-published");
  if (preflight.state === "conflict")
    throw releaseError(
      "version-conflict",
      `${release.metadata.name}@${release.metadata.version} exists with different bytes`,
    );
  if (preflight.state !== "absent")
    throw releaseError("registry-state", "unexpected registry preflight state");
  if (dryRun) return writeOutcome(release, registry, "dry-run");
  const arguments_ = [
    "publish",
    release.archivePath,
    "--ignore-scripts",
    "--access",
    "public",
    "--tag",
    "next",
    "--registry",
    registry,
    "--json",
  ];
  arguments_.push(auth.provenance ? "--provenance" : "--provenance=false");
  const mutationAuth = await mutationAuthentication({
    authMode,
    environment,
    registry,
  });
  try {
    await runCommand("npm", arguments_, {
      cwd: release.directory,
      env: mutationAuth.environment,
      ...(mutationAuth.interactive ? { stdio: "inherit" } : {}),
    });
  } catch (error) {
    const failure = error instanceof Error ? error : new Error(String(error));
    failure.npmLog = await mutationAuth.failureDetails();
    const definite = definiteNpmFailure(failure);
    if (definite) throw definite;
    const outcome = await writeOutcome(release, registry, "uncertain", {
      reason: "npm publish did not return success",
    });
    throw releaseError(
      "publication-uncertain",
      `Publication outcome is uncertain. Do not publish again. Run: ${outcome.verificationCommand}`,
      { cause: failure },
    );
  } finally {
    await mutationAuth.cleanup();
  }
  for (let attempt = 1; attempt <= visibilityAttempts; attempt += 1) {
    let observed;
    try {
      observed = await inspect(candidate);
    } catch (error) {
      const outcome = await writeOutcome(release, registry, "uncertain", {
        reason: `post-publication registry verification failed${error.code ? ` (${error.code})` : ""}`,
      });
      throw releaseError(
        "publication-uncertain",
        `Publication was attempted but registry verification failed. Do not publish again. Run: ${outcome.verificationCommand}`,
        { cause: error },
      );
    }
    if (observed.state === "matching")
      return writeOutcome(release, registry, "published");
    if (observed.state === "conflict")
      throw releaseError(
        "version-conflict",
        `${release.metadata.name}@${release.metadata.version} became visible with different bytes`,
      );
    if (attempt < visibilityAttempts) await wait(visibilityDelayMilliseconds);
  }
  const outcome = await writeOutcome(release, registry, "uncertain", {
    reason: `exact version remained unavailable after ${visibilityAttempts} reads`,
  });
  throw releaseError(
    "publication-uncertain",
    `Publication was accepted but registry visibility is uncertain. Do not publish again. Run: ${outcome.verificationCommand}`,
  );
}

export async function verifyRelease({
  packageName,
  releaseDirectory,
  root = workspaceRoot,
  registry = registryRoot,
  fetchImpl = fetch,
  runCommand = run,
  inspect = inspectExactVersion,
}) {
  approvedRegistry(registry);
  const release = await validateReleaseDirectory({
    packageName,
    releaseDirectory,
    root,
    runCommand,
  });
  const result = await inspect({
    name: release.metadata.name,
    version: release.metadata.version,
    integrity: release.metadata.integrity,
    registry,
    fetchImpl,
  });
  if (result.state === "absent")
    throw releaseError(
      "version-absent",
      `${release.metadata.name}@${release.metadata.version} is not visible`,
    );
  if (result.state === "conflict")
    throw releaseError(
      "version-conflict",
      `${release.metadata.name}@${release.metadata.version} exists with different bytes`,
    );
  assert.equal(
    result.state,
    "matching",
    "unexpected registry verification state",
  );
  return { ...release.metadata, state: "verified" };
}

export async function promoteRelease({
  packageName,
  version,
  channel,
  authMode = "local",
  dryRun = false,
  environment = process.env,
  registry = registryRoot,
  fetchImpl = fetch,
  runCommand = run,
  inspect = inspectExactVersion,
  root = workspaceRoot,
}) {
  const selected = selectPackage(packageName);
  const manifest = await readManifest(selected, root);
  approvedRegistry(registry);
  assert(semver.valid(version), "VERSION must be an exact semantic version");
  assert(channelPattern.test(channel ?? ""), "CHANNEL is invalid");
  assert.equal(
    semver.validRange(channel),
    null,
    "CHANNEL must not be a semantic-version range",
  );
  assertAuthentication({
    authMode,
    dryRun,
    environment,
    metadata: { preparedBy: { kind: "local" } },
    operation: "promote",
  });
  const result = await inspect({
    name: manifest.name,
    version,
    registry,
    fetchImpl,
  });
  if (result.state === "absent")
    throw releaseError(
      "version-absent",
      `${manifest.name}@${version} is not published`,
    );
  assert.equal(result.state, "present", "unexpected promotion registry state");
  if (!dryRun) {
    const mutationAuth = await mutationAuthentication({
      authMode,
      environment,
      registry,
    });
    try {
      await runCommand(
        "npm",
        [
          "dist-tag",
          "add",
          `${manifest.name}@${version}`,
          channel,
          "--registry",
          registry,
          "--json",
        ],
        {
          cwd: root,
          env: mutationAuth.environment,
          ...(mutationAuth.interactive ? { stdio: "inherit" } : {}),
        },
      );
    } catch (error) {
      const failure = error instanceof Error ? error : new Error(String(error));
      failure.npmLog = await mutationAuth.failureDetails();
      throw definiteNpmFailure(failure) ?? failure;
    } finally {
      await mutationAuth.cleanup();
    }
  }
  return {
    channel,
    name: manifest.name,
    state: dryRun ? "dry-run" : "promoted",
    version,
  };
}

export async function main(argv = process.argv, environment = process.env) {
  const operation = argv[2];
  if (argv.length !== 3)
    throw releaseError(
      "invalid-option",
      "release inputs must be passed through the Make environment boundary",
    );
  if (!["prepare", "publish", "verify", "promote"].includes(operation))
    throw releaseError(
      "invalid-operation",
      "operation must be prepare, publish, verify, or promote",
    );
  const {
    authMode,
    channel,
    dryRun,
    packageName,
    registry,
    releaseDirectory,
    version,
  } = readReleaseInputs({ environment, operation });
  const common = {
    packageName,
    ...(releaseDirectory ? { releaseDirectory } : {}),
    registry,
  };
  let result;
  if (operation === "prepare")
    result = await prepareRelease({ ...common, environment });
  else if (operation === "publish")
    result = await publishRelease({
      ...common,
      authMode,
      dryRun,
      environment,
    });
  else if (operation === "verify") result = await verifyRelease(common);
  else if (operation === "promote")
    result = await promoteRelease({
      ...common,
      authMode,
      channel,
      dryRun,
      environment,
      version,
    });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    await main();
  } catch (error) {
    process.stderr.write(
      `${error.code ? `${error.code}: ` : ""}${error.message}\n`,
    );
    process.exitCode = 1;
  }
}
