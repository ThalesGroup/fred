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
  access,
  chmod,
  mkdtemp,
  mkdir,
  readFile,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import semver from "semver";

import {
  assertAuthentication,
  inspectExactVersion,
  main,
  parseDryRun,
  prepareRelease,
  promoteRelease,
  publishRelease,
  releasePackages,
  readReleaseInputs,
  resolveUiDesignTokens,
  selectPackage,
  validateReleaseDirectory,
  verifyRelease,
  withCachedVerifiedUiToken,
  workspaceRoot,
} from "../scripts/npm-release.mjs";
import { run } from "../scripts/process.mjs";
import { sha512Integrity } from "../scripts/release-evidence.mjs";
import {
  isExactSemanticVersion,
  isSemanticVersionRangeLikeTag,
} from "../scripts/release-operation-inputs.mjs";

const archiveBytesA = Buffer.from("registry archive A");
const archiveBytesB = Buffer.from("registry archive B");
const integrityA = `sha512-${createHash("sha512").update(archiveBytesA).digest("base64")}`;
const integrityB = `sha512-${createHash("sha512").update(archiveBytesB).digest("base64")}`;
const tokenTarball =
  "https://registry.npmjs.org/@fred-oss/design-tokens/-/design-tokens-0.1.1-alpha.0.tgz";
const localEnvironment = Object.freeze({ CI: "false" });

test("process execution accepts only named commands without a shell", async () => {
  await assert.rejects(
    run("/tmp/untrusted-executable", []),
    /unsupported executable/,
  );
  await assert.rejects(
    run("node", ["-e", "process.exit(0)"], { shell: true }),
    /shell execution is forbidden/,
  );
});

test("dependency-free release guards match node-semver on tag-like boundaries", () => {
  for (const version of [
    "0.0.0",
    "1.2.3-alpha.1+build.5",
    "1.2.3-alpha.01",
    "01.2.3",
    "999999999999999999999.1.1",
    "1.2.3-999999999999999999999",
    "1.2.3+999999999999999999999",
  ])
    assert.equal(
      isExactSemanticVersion(version),
      semver.valid(version) !== null,
      version,
    );
  for (const channel of [
    "1",
    "1.2",
    "1.2.3",
    "v1",
    "v1.2.3",
    "v",
    "vx",
    "x",
    "x.0",
    "x.0.0-alpha",
    "x.01",
    "1.x",
    "1.x.0",
    "1.x.0-alpha",
    "1.x.01",
    "0.x.1-alpha",
    "1.2.x",
    "1.2.x-alpha",
    "1.2.x-alpha.01",
    "1.2.3-alpha.1",
    "1.2.3-01",
    "999999999999999999999",
    "999999999999999999999.x",
    "9007199254740991",
    "9007199254740991.x",
    "1.9007199254740991.x",
    "next",
    "latest",
    "beta",
    "canary",
  ])
    assert.equal(
      isSemanticVersionRangeLikeTag(channel),
      semver.validRange(channel) !== null,
      channel,
    );
  const components = [
    "0",
    "1",
    "2",
    "01",
    "x",
    "999999999999999999999",
    "9007199254740991",
  ];
  const suffixes = ["", "-alpha", "-01", "-alpha.1", "-alpha.01"];
  for (let length = 1; length <= 3; length += 1) {
    const visit = (selected) => {
      if (selected.length < length) {
        for (const component of components) visit([...selected, component]);
        return;
      }
      for (const prefix of ["", "v"])
        for (const suffix of suffixes) {
          const channel = `${prefix}${selected.join(".")}${suffix}`;
          assert.equal(
            isSemanticVersionRangeLikeTag(channel),
            semver.validRange(channel) !== null,
            channel,
          );
        }
    };
    visit([]);
  }
});

function response(status, body, options = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    url: options.url,
    headers: { get: (name) => options.headers?.[name.toLowerCase()] ?? null },
    json: async () => body,
    arrayBuffer: async () => options.bytes,
  };
}

function releaseContract(packages = {}) {
  return {
    packages,
    releaseToolchain: { node: "24.21.0", npm: "11.19.0" },
  };
}

async function fixtureRoot() {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-npm-release-test-"));
  await Promise.all(
    Object.entries(releasePackages).map(async ([packageName, selected]) => {
      await mkdir(path.join(root, selected.workspace), { recursive: true });
      await writeFile(
        path.join(root, selected.workspace, "package.json"),
        `${JSON.stringify({
          name: `@fred-oss/${packageName}`,
          version:
            packageName === "iframe-sdk" ? "0.1.1-alpha.1" : "0.1.1-alpha.0",
          ...(packageName === "ui"
            ? {
                peerDependencies: {
                  "@fred-oss/design-tokens": "^0.1.0-alpha.1 || ^0.1.1-alpha.0",
                },
              }
            : {}),
        })}\n`,
      );
    }),
  );
  return root;
}

async function preparedFixture(
  packageName = "iframe-sdk",
  releaseDirectoryName = "release",
) {
  const root = await fixtureRoot();
  const selected = selectPackage(packageName);
  const manifest = JSON.parse(
    await readFile(path.join(root, selected.workspace, "package.json"), "utf8"),
  );
  const releaseDirectory = path.join(root, releaseDirectoryName);
  await mkdir(releaseDirectory);
  const archive = `${manifest.name.split("/").at(-1)}-${manifest.version}.tgz`;
  const archivePath = path.join(releaseDirectory, archive);
  await writeFile(archivePath, `archive:${manifest.name}:${manifest.version}`);
  const metadata = {
    schemaVersion: 1,
    package: packageName,
    name: manifest.name,
    version: manifest.version,
    sourceCommit: "a".repeat(40),
    archive,
    integrity: await sha512Integrity(archivePath),
    preparedBy: { kind: "local" },
  };
  await writeFile(
    path.join(releaseDirectory, "release.json"),
    `${JSON.stringify(metadata, null, 2)}\n`,
  );
  const runCommand = async (command, arguments_) => {
    if (command === "tar")
      return { stdout: JSON.stringify(manifest), stderr: "" };
    throw new Error(`unexpected command ${command} ${arguments_.join(" ")}`);
  };
  return { manifest, metadata, releaseDirectory, root, runCommand };
}

test("package selection accepts only the public Make selectors", () => {
  assert.equal(selectPackage("design-tokens").id, "designTokens");
  assert.equal(selectPackage("ui").id, "ui");
  assert.equal(selectPackage("iframe-sdk").id, "iframeSdk");
  for (const invalid of [
    undefined,
    "",
    "designTokens",
    "iframeSdk",
    "root",
    "ui,iframe-sdk",
  ])
    assert.throws(
      () => selectPackage(invalid),
      /PACKAGE must be exactly one of/,
    );
});

test("captured release inputs are parsed explicitly before operations", async () => {
  const valid = {
    FRED_RELEASE_PACKAGE: "iframe-sdk",
    FRED_RELEASE_RELEASE_DIR: "/tmp/release with '$() and `ticks`",
    FRED_RELEASE_AUTH_MODE: "token",
    FRED_RELEASE_DRY_RUN: "yes",
    FRED_RELEASE_REGISTRY: "http://127.0.0.1:4873/custom/",
    FRED_RELEASE_VERSION: "0.1.1-alpha.1",
    FRED_RELEASE_CHANNEL: "next-2026.10",
  };
  assert.deepEqual(
    readReleaseInputs({ environment: valid, operation: "promote" }),
    {
      authMode: "token",
      channel: "next-2026.10",
      dryRun: true,
      packageName: "iframe-sdk",
      registry: "http://127.0.0.1:4873/custom/",
      releaseDirectory: "/tmp/release with '$() and `ticks`",
      version: "0.1.1-alpha.1",
    },
  );
  for (const [value, expected] of [
    ["", false],
    ["0", false],
    ["false", false],
    ["no", false],
    ["1", true],
    ["true", true],
    ["yes", true],
  ])
    assert.equal(parseDryRun(value), expected);
  assert.throws(() => parseDryRun("TRUE"), /DRY_RUN must be/);
  for (const channel of ["1", "1.2", "1.2.3", "1.x", "v1.2.3", "1.2.3-alpha.1"])
    assert.throws(
      () =>
        readReleaseInputs({
          environment: { ...valid, FRED_RELEASE_CHANNEL: channel },
          operation: "promote",
        }),
      /semantic-version range/,
      channel,
    );
  for (const [name, value, message] of [
    ["FRED_RELEASE_PACKAGE", "ui\nnext", /single line/],
    ["FRED_RELEASE_AUTH_MODE", "fallback", /AUTH_MODE/],
    ["FRED_RELEASE_DRY_RUN", "sometimes", /DRY_RUN/],
    ["FRED_RELEASE_REGISTRY", "https://example.test/no-slash", /slash/],
  ])
    assert.throws(
      () =>
        readReleaseInputs({
          environment: { ...valid, [name]: value },
          operation: "promote",
        }),
      message,
    );
  await assert.rejects(
    main(
      ["node", "npm-release.mjs", "promote", "--package", "iframe-sdk"],
      valid,
    ),
    /Make environment boundary/,
  );
});

test("preparation derives identity, runs selected checks, and writes exact metadata", async () => {
  const root = await fixtureRoot();
  const releaseDirectory = path.join(root, "portable");
  const archivePath = path.join(root, "built.tgz");
  await writeFile(archivePath, "prepared bytes");
  const calls = [];
  const result = await prepareRelease({
    packageName: "iframe-sdk",
    releaseDirectory,
    root,
    environment: {},
    hashArchive: async () => integrityA,
    loadContract: async () => releaseContract(),
    nodeVersion: "24.21.0",
    pack: async ({ validate }) => {
      calls.push(["pack", validate]);
      return { archivePath };
    },
    runChecks: async ({ selected, integrity }) =>
      calls.push(["checks", selected.package, integrity]),
    runCommand: async (command, arguments_) => {
      if (command === "npm") return { stdout: "11.19.0\n", stderr: "" };
      if (command === "git" && arguments_[0] === "status")
        return { stdout: "", stderr: "" };
      if (command === "git" && arguments_[0] === "rev-parse")
        return { stdout: `${"b".repeat(40)}\n`, stderr: "" };
      if (command === "tar")
        return {
          stdout: JSON.stringify({
            name: "@fred-oss/iframe-sdk",
            version: "0.1.1-alpha.1",
          }),
          stderr: "",
        };
      throw new Error(`unexpected command ${command}`);
    },
  });
  assert.deepEqual(calls, [
    ["pack", true],
    ["checks", "iframe-sdk", integrityA],
  ]);
  assert.equal(result.metadata.name, "@fred-oss/iframe-sdk");
  assert.equal(result.metadata.version, "0.1.1-alpha.1");
  assert.equal(result.metadata.sourceCommit, "b".repeat(40));
  assert.equal(result.metadata.integrity, integrityA);
  assert.deepEqual(result.metadata.preparedBy, { kind: "local" });
});

test("preparation dispatches independently for all three packages", async () => {
  const root = await fixtureRoot();
  const calls = [];
  for (const packageName of Object.keys(releasePackages)) {
    const selected = selectPackage(packageName);
    const manifest = JSON.parse(
      await readFile(
        path.join(root, selected.workspace, "package.json"),
        "utf8",
      ),
    );
    const archivePath = path.join(root, `${packageName}.tgz`);
    await writeFile(archivePath, `${packageName} bytes`);
    const result = await prepareRelease({
      packageName,
      releaseDirectory: path.join(root, `portable-${packageName}`),
      root,
      environment: {},
      hashArchive: async () => integrityA,
      loadContract: async () =>
        releaseContract({
          designTokens: { name: "@fred-oss/design-tokens" },
        }),
      nodeVersion: "24.21.0",
      fetchImpl: async (endpoint) =>
        endpoint.pathname.endsWith(".tgz")
          ? response(200, undefined, {
              bytes: archiveBytesA,
              url: endpoint.href,
            })
          : response(200, {
              name: "@fred-oss/design-tokens",
              versions: {
                "0.1.1-alpha.0": {
                  name: "@fred-oss/design-tokens",
                  version: "0.1.1-alpha.0",
                  dist: { integrity: integrityA, tarball: tokenTarball },
                },
              },
            }),
      pack: async ({ validate }) => {
        calls.push([packageName, "pack", validate]);
        return { archivePath };
      },
      runChecks: async ({ selected: checked }) =>
        calls.push([packageName, "checks", checked.package]),
      runCommand: async (command, arguments_) => {
        if (command === "npm") return { stdout: "11.19.0\n", stderr: "" };
        if (command === "git" && arguments_[0] === "status")
          return { stdout: "", stderr: "" };
        if (command === "git" && arguments_[0] === "rev-parse")
          return { stdout: `${"c".repeat(40)}\n`, stderr: "" };
        if (command === "tar")
          return { stdout: JSON.stringify(manifest), stderr: "" };
        throw new Error(`unexpected command ${command}`);
      },
    });
    assert.equal(result.metadata.package, packageName);
    assert.equal(result.metadata.version, manifest.version);
  }
  assert.deepEqual(
    calls,
    Object.keys(releasePackages).flatMap((packageName) => [
      [packageName, "pack", true],
      [packageName, "checks", packageName],
    ]),
  );
});

test("preparation rejects dirty source before packing", async () => {
  const root = await fixtureRoot();
  let packed = false;
  await assert.rejects(
    prepareRelease({
      packageName: "design-tokens",
      releaseDirectory: path.join(root, "portable"),
      root,
      loadContract: async () => releaseContract(),
      nodeVersion: "24.21.0",
      pack: async () => {
        packed = true;
        return {};
      },
      runCommand: async (command, arguments_) => ({
        stdout:
          command === "npm"
            ? "11.19.0\n"
            : command === "git" && arguments_[0] === "status"
              ? " M design-tokens/package.json\n"
              : `${"c".repeat(40)}\n`,
      }),
    }),
    (error) => error.code === "dirty-source",
  );
  assert.equal(packed, false);
});

test("preparation enforces the actual release toolchain before registry, pack, or checks", async () => {
  for (const mismatch of [
    { nodeVersion: "24.21.1", npmVersion: "11.19.0\n" },
    { nodeVersion: "24.21.0", npmVersion: "11.19.1\n" },
  ]) {
    const root = await fixtureRoot();
    let laterWork = 0;
    await assert.rejects(
      prepareRelease({
        packageName: "ui",
        root,
        loadContract: async () =>
          releaseContract({
            designTokens: { name: "@fred-oss/design-tokens" },
          }),
        nodeVersion: mismatch.nodeVersion,
        fetchImpl: async () => {
          laterWork += 1;
          return response(404);
        },
        pack: async () => {
          laterWork += 1;
          return {};
        },
        runChecks: async () => {
          laterWork += 1;
        },
        runCommand: async (command) => {
          assert.equal(command, "npm");
          return { stdout: mismatch.npmVersion, stderr: "" };
        },
      }),
      /release (?:Node|npm) version differs/,
    );
    assert.equal(laterWork, 0);
  }

  const root = await fixtureRoot();
  let laterWork = 0;
  await assert.rejects(
    prepareRelease({
      packageName: "ui",
      root,
      loadContract: async () => releaseContract(),
      nodeVersion: "24.21.0",
      fetchImpl: async () => {
        laterWork += 1;
        return response(404);
      },
      pack: async () => {
        laterWork += 1;
        return {};
      },
      runChecks: async () => {
        laterWork += 1;
      },
      runCommand: async (command) => {
        assert.equal(command, "npm");
        throw new Error("npm is missing");
      },
    }),
    /npm is missing/,
  );
  assert.equal(laterWork, 0);
});

test("preparation checks the toolchain before reading package or full-contract data", async () => {
  const root = await fixtureRoot();
  await writeFile(path.join(root, "ui/package.json"), "not JSON\n");
  let contractReads = 0;
  await assert.rejects(
    prepareRelease({
      packageName: "ui",
      root,
      nodeVersion: "24.21.1",
      loadToolchain: async () => ({ node: "24.21.0", npm: "11.19.0" }),
      loadContract: async () => {
        contractReads += 1;
        throw new Error("full contract must not be read");
      },
      runCommand: async (command) => {
        assert.equal(command, "npm");
        return { stdout: "11.19.0\n", stderr: "" };
      },
    }),
    /release Node version differs/,
  );
  assert.equal(contractReads, 0);
});

test("preparation rejects source changes made while checks run", async () => {
  const root = await fixtureRoot();
  const archivePath = path.join(root, "built.tgz");
  await writeFile(archivePath, "prepared bytes");
  let statusReads = 0;
  await assert.rejects(
    prepareRelease({
      packageName: "iframe-sdk",
      releaseDirectory: path.join(root, "portable"),
      root,
      hashArchive: async () => integrityA,
      loadContract: async () => releaseContract(),
      nodeVersion: "24.21.0",
      pack: async () => ({ archivePath }),
      runChecks: async () => {},
      runCommand: async (command, arguments_) => {
        if (command === "npm") return { stdout: "11.19.0\n", stderr: "" };
        if (command === "git" && arguments_[0] === "status") {
          statusReads += 1;
          return {
            stdout: statusReads === 1 ? "" : " M iframe-sdk/package.json\n",
            stderr: "",
          };
        }
        if (command === "git" && arguments_[0] === "rev-parse")
          return { stdout: `${"d".repeat(40)}\n`, stderr: "" };
        throw new Error(`unexpected command ${command}`);
      },
    }),
    (error) =>
      error.code === "dirty-source" &&
      /changed during preparation/.test(error.message),
  );
});

test("release validation rejects altered bytes, identity, and unexpected files", async () => {
  const fixture = await preparedFixture();
  const valid = await validateReleaseDirectory({
    ...fixture,
    packageName: "iframe-sdk",
  });
  assert.equal(valid.metadata.package, "iframe-sdk");
  await writeFile(valid.archivePath, "altered");
  await assert.rejects(
    validateReleaseDirectory({ ...fixture, packageName: "iframe-sdk" }),
    /integrity differs/,
  );

  const another = await preparedFixture();
  await writeFile(path.join(another.releaseDirectory, "manual.json"), "{}");
  await assert.rejects(
    validateReleaseDirectory({ ...another, packageName: "iframe-sdk" }),
    /unexpected release file/,
  );

  const drifted = await preparedFixture();
  await writeFile(
    path.join(drifted.root, "iframe-sdk/package.json"),
    `${JSON.stringify({ name: "@fred-oss/iframe-sdk", version: "9.9.9" })}\n`,
  );
  await assert.rejects(
    validateReleaseDirectory({ ...drifted, packageName: "iframe-sdk" }),
    /version differs from manifest/,
  );
});

test("exact registry inspection distinguishes absence, matching bytes, conflict, and access failures", async () => {
  const input = {
    name: "@fred-oss/iframe-sdk",
    version: "0.1.1-alpha.1",
    integrity: integrityA,
  };
  const tarball =
    "https://registry.npmjs.org/@fred-oss/iframe-sdk/-/iframe-sdk-0.1.1-alpha.1.tgz";
  const registryFetch =
    ({ metadataIntegrity, bytes = archiveBytesA }) =>
    async (endpoint) =>
      endpoint.pathname.endsWith(".tgz")
        ? response(200, undefined, { bytes, url: endpoint.href })
        : response(
            200,
            {
              name: input.name,
              version: input.version,
              dist: { integrity: metadataIntegrity, tarball },
            },
            { url: endpoint.href },
          );
  assert.equal(
    (
      await inspectExactVersion({
        ...input,
        fetchImpl: async () => response(404),
      })
    ).state,
    "absent",
  );
  assert.equal(
    (
      await inspectExactVersion({
        ...input,
        fetchImpl: registryFetch({ metadataIntegrity: integrityA }),
      })
    ).state,
    "matching",
  );
  assert.equal(
    (
      await inspectExactVersion({
        ...input,
        fetchImpl: registryFetch({
          bytes: archiveBytesB,
          metadataIntegrity: integrityB,
        }),
      })
    ).state,
    "conflict",
  );
  await assert.rejects(
    inspectExactVersion({ ...input, fetchImpl: async () => response(401) }),
    (error) => error.code === "registry-authentication",
  );
  await assert.rejects(
    inspectExactVersion({ ...input, fetchImpl: async () => response(403) }),
    (error) => error.code === "registry-authorization",
  );
  await assert.rejects(
    inspectExactVersion({
      ...input,
      fetchImpl: async () => {
        throw new Error("offline");
      },
    }),
    (error) => error.code === "registry-network",
  );
  await assert.rejects(
    inspectExactVersion({
      ...input,
      fetchImpl: registryFetch({
        bytes: archiveBytesB,
        metadataIntegrity: integrityA,
      }),
    }),
    (error) => error.code === "registry-integrity",
  );
  for (const invalidTarball of [
    "https://evil.example/iframe-sdk.tgz",
    "https://registry.npmjs.org/@fred-oss/iframe-sdk/-/other.tgz",
    `${tarball}?token=secret`,
  ])
    await assert.rejects(
      inspectExactVersion({
        ...input,
        fetchImpl: async (endpoint) =>
          response(
            200,
            {
              name: input.name,
              version: input.version,
              dist: { integrity: integrityA, tarball: invalidTarball },
            },
            { url: endpoint.href },
          ),
      }),
      (error) => error.code === "registry-tarball",
    );
  await assert.rejects(
    inspectExactVersion({
      ...input,
      fetchImpl: async (endpoint) =>
        endpoint.pathname.endsWith(".tgz")
          ? response(302, undefined, { url: endpoint.href })
          : response(
              200,
              {
                name: input.name,
                version: input.version,
                dist: { integrity: integrityA, tarball },
              },
              { url: endpoint.href },
            ),
    }),
    (error) => error.code === "registry-redirect",
  );
  for (const [tarballResponse, expectedCode] of [
    [response(401), "registry-authentication"],
    [response(403), "registry-authorization"],
    [response(404), "registry-response"],
    [
      response(200, undefined, {
        bytes: archiveBytesA,
        headers: { "content-length": String(50 * 1024 * 1024 + 1) },
      }),
      "registry-tarball",
    ],
  ])
    await assert.rejects(
      inspectExactVersion({
        ...input,
        fetchImpl: async (endpoint) =>
          endpoint.pathname.endsWith(".tgz")
            ? { ...tarballResponse, url: endpoint.href }
            : response(
                200,
                {
                  name: input.name,
                  version: input.version,
                  dist: { integrity: integrityA, tarball },
                },
                { url: endpoint.href },
              ),
      }),
      (error) => error.code === expectedCode,
    );
  await assert.rejects(
    inspectExactVersion({
      ...input,
      fetchImpl: async (endpoint) => {
        if (endpoint.pathname.endsWith(".tgz")) {
          const error = new Error("timed out");
          error.name = "TimeoutError";
          throw error;
        }
        return response(
          200,
          {
            name: input.name,
            version: input.version,
            dist: { integrity: integrityA, tarball },
          },
          { url: endpoint.href },
        );
      },
    }),
    (error) => error.code === "registry-timeout",
  );
  await assert.rejects(
    inspectExactVersion({
      ...input,
      fetchImpl: async (endpoint) => ({
        ...response(200, undefined, { url: endpoint.href }),
        json: async () => {
          const error = new Error("metadata body timed out");
          error.name = "AbortError";
          throw error;
        },
      }),
    }),
    (error) => error.code === "registry-timeout",
  );
  await assert.rejects(
    inspectExactVersion({
      ...input,
      fetchImpl: async (endpoint) =>
        endpoint.pathname.endsWith(".tgz")
          ? {
              ...response(200, undefined, { url: endpoint.href }),
              arrayBuffer: async () => {
                const error = new Error("tarball body timed out");
                error.name = "AbortError";
                throw error;
              },
            }
          : response(
              200,
              {
                name: input.name,
                version: input.version,
                dist: { integrity: integrityA, tarball },
              },
              { url: endpoint.href },
            ),
    }),
    (error) => error.code === "registry-timeout",
  );
});

test("publish preflight, post-upload visibility, and verification hash selected-registry bytes", async () => {
  const registry = "http://127.0.0.1:4873/custom/";
  const exactPath = "/custom/@fred-oss%2fiframe-sdk/0.1.1-alpha.1";
  const tarball =
    "http://127.0.0.1:4873/custom/@fred-oss/iframe-sdk/-/iframe-sdk-0.1.1-alpha.1.tgz";
  const createFetch = ({ absentReads = 0 } = {}) => {
    const calls = [];
    const fetchImpl = async (endpoint) => {
      calls.push(endpoint.href);
      if (endpoint.pathname === exactPath && absentReads > 0) {
        absentReads -= 1;
        return response(404, undefined, { url: endpoint.href });
      }
      if (endpoint.pathname.endsWith(".tgz"))
        return response(200, undefined, {
          bytes: fetchImpl.archiveBytes,
          url: endpoint.href,
        });
      return response(
        200,
        {
          name: "@fred-oss/iframe-sdk",
          version: "0.1.1-alpha.1",
          dist: {
            integrity: fetchImpl.integrity,
            tarball,
          },
        },
        { url: endpoint.href },
      );
    };
    return { calls, fetchImpl };
  };

  const existing = await preparedFixture();
  const existingFetch = createFetch();
  existingFetch.fetchImpl.archiveBytes = await readFile(
    path.join(existing.releaseDirectory, existing.metadata.archive),
  );
  existingFetch.fetchImpl.integrity = existing.metadata.integrity;
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: existing.releaseDirectory,
    root: existing.root,
    environment: localEnvironment,
    registry,
    fetchImpl: existingFetch.fetchImpl,
    runCommand: existing.runCommand,
  });
  assert.equal(outcome.state, "already-published");
  assert(existingFetch.calls.some((url) => url === tarball));
  const verified = await verifyRelease({
    packageName: "iframe-sdk",
    releaseDirectory: existing.releaseDirectory,
    root: existing.root,
    registry,
    fetchImpl: existingFetch.fetchImpl,
    runCommand: existing.runCommand,
  });
  assert.equal(verified.state, "verified");

  const uploaded = await preparedFixture();
  const uploadedFetch = createFetch({ absentReads: 1 });
  uploadedFetch.fetchImpl.archiveBytes = await readFile(
    path.join(uploaded.releaseDirectory, uploaded.metadata.archive),
  );
  uploadedFetch.fetchImpl.integrity = uploaded.metadata.integrity;
  let npmPublishes = 0;
  const published = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: uploaded.releaseDirectory,
    root: uploaded.root,
    environment: localEnvironment,
    registry,
    fetchImpl: uploadedFetch.fetchImpl,
    runCommand: async (command, arguments_) => {
      if (command === "tar") return uploaded.runCommand(command, arguments_);
      npmPublishes += 1;
      return { stdout: "", stderr: "" };
    },
    visibilityDelayMilliseconds: 0,
  });
  assert.equal(published.state, "published");
  assert.equal(npmPublishes, 1);
  assert(uploadedFetch.calls.some((url) => url === tarball));
});

test("UI dependency resolution uses the declared range and exact published integrity", async () => {
  const root = await fixtureRoot();
  const manifest = JSON.parse(
    await readFile(path.join(root, "ui/package.json"), "utf8"),
  );
  const contract = {
    packages: { designTokens: { name: "@fred-oss/design-tokens" } },
  };
  const resolved = await resolveUiDesignTokens({
    contract,
    manifest,
    fetchImpl: async (endpoint) =>
      endpoint.pathname.endsWith(".tgz")
        ? response(200, undefined, {
            bytes: archiveBytesB,
            url: endpoint.href,
          })
        : response(200, {
            name: "@fred-oss/design-tokens",
            versions: {
              "0.1.0-alpha.1": {
                name: "@fred-oss/design-tokens",
                version: "0.1.0-alpha.1",
                dist: { integrity: integrityA, tarball: tokenTarball },
              },
              "0.1.1-alpha.0": {
                name: "@fred-oss/design-tokens",
                version: "0.1.1-alpha.0",
                dist: { integrity: integrityB, tarball: tokenTarball },
              },
              "0.2.0-alpha.0": {
                name: "@fred-oss/design-tokens",
                version: "0.2.0-alpha.0",
                dist: { integrity: integrityA, tarball: tokenTarball },
              },
              "1.0.0": {
                name: "@fred-oss/design-tokens",
                version: "1.0.0",
                dist: { integrity: integrityA, tarball: tokenTarball },
              },
            },
          }),
  });
  assert.equal(resolved.coordinate, "@fred-oss/design-tokens@0.1.1-alpha.0");
  assert.equal(resolved.integrity, integrityB);
  assert.equal(resolved.registry, "https://registry.npmjs.org/");
  assert.equal(resolved.tarball, tokenTarball);
  assert.deepEqual(resolved.archiveBytes, archiveBytesB);
  let cachedPath;
  let consumedBytes;
  let coordinateReresolution = false;
  await withCachedVerifiedUiToken({
    uiToken: resolved,
    cachePath: path.join(root, "selected-token-cache"),
    runCommand: async (command, arguments_) => {
      assert.equal(command, "npm");
      assert.deepEqual(arguments_.slice(0, 2), ["cache", "add"]);
      coordinateReresolution ||= arguments_.includes(resolved.coordinate);
      cachedPath = arguments_[2];
      assert.deepEqual(await readFile(cachedPath), archiveBytesB);
      return { stdout: "", stderr: "" };
    },
    action: async (archivePath) => {
      assert.equal(archivePath, cachedPath);
      consumedBytes = await readFile(archivePath);
    },
  });
  assert.equal(coordinateReresolution, false);
  assert.deepEqual(consumedBytes, archiveBytesB);
  await assert.rejects(access(cachedPath), { code: "ENOENT" });
  const customRegistry = "http://127.0.0.1:4873/custom/";
  const customTarball =
    "http://127.0.0.1:4873/custom/@fred-oss/design-tokens/-/design-tokens-0.1.1-alpha.0.tgz";
  const customResolved = await resolveUiDesignTokens({
    contract,
    manifest,
    registry: customRegistry,
    fetchImpl: async (endpoint) =>
      endpoint.pathname.endsWith(".tgz")
        ? response(200, undefined, {
            bytes: archiveBytesB,
            url: endpoint.href,
          })
        : response(200, {
            name: "@fred-oss/design-tokens",
            versions: {
              "0.1.1-alpha.0": {
                name: "@fred-oss/design-tokens",
                version: "0.1.1-alpha.0",
                dist: { integrity: integrityB, tarball: customTarball },
              },
            },
          }),
  });
  assert.equal(customResolved.registry, customRegistry);
  assert.equal(customResolved.tarball, customTarball);
  await assert.rejects(
    resolveUiDesignTokens({
      contract,
      manifest,
      registry: customRegistry,
      fetchImpl: async () =>
        response(200, {
          name: "@fred-oss/design-tokens",
          versions: {
            "0.1.1-alpha.0": {
              name: "@fred-oss/design-tokens",
              version: "0.1.1-alpha.0",
              dist: {
                integrity: integrityB,
                tarball:
                  "http://127.0.0.1:4873/custom/@fred-oss/design-tokens/-/other-0.1.1-alpha.0.tgz",
              },
            },
          },
        }),
    }),
    (error) => error.code === "registry-tarball",
  );
  await assert.rejects(
    resolveUiDesignTokens({
      contract,
      manifest,
      fetchImpl: async () => response(404),
    }),
    (error) =>
      error.code === "dependency-unavailable" &&
      /publish design-tokens first/.test(error.message),
  );
  await assert.rejects(
    resolveUiDesignTokens({
      contract,
      manifest,
      fetchImpl: async () => response(401),
    }),
    (error) => error.code === "registry-authentication",
  );
  await assert.rejects(
    resolveUiDesignTokens({
      contract,
      manifest,
      fetchImpl: async () => {
        throw new Error("offline");
      },
    }),
    (error) => error.code === "registry-network",
  );
  await assert.rejects(
    resolveUiDesignTokens({
      contract,
      manifest,
      fetchImpl: async () => response(200, { name: "wrong", versions: {} }),
    }),
    /registry identity differs/,
  );
  await assert.rejects(
    resolveUiDesignTokens({
      contract,
      manifest,
      fetchImpl: async () =>
        response(200, {
          name: "@fred-oss/design-tokens",
          versions: {
            "0.1.1-alpha.0": {
              name: "@fred-oss/design-tokens",
              version: "0.1.1-alpha.0",
              dist: { integrity: "sha512-short" },
            },
          },
        }),
    }),
    /integrity is missing/,
  );
});

test("UI publication validates the peer range packed in the prepared archive", async () => {
  const fixture = await preparedFixture("ui");
  await writeFile(
    path.join(fixture.root, "ui/package.json"),
    `${JSON.stringify({
      name: fixture.manifest.name,
      version: fixture.manifest.version,
      peerDependencies: { "@fred-oss/design-tokens": "^9.0.0" },
    })}\n`,
  );
  const result = await publishRelease({
    packageName: "ui",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    environment: localEnvironment,
    dryRun: true,
    runCommand: fixture.runCommand,
    loadContract: async () => ({
      packages: { designTokens: { name: "@fred-oss/design-tokens" } },
    }),
    fetchImpl: async (endpoint) =>
      endpoint.pathname.endsWith(".tgz")
        ? response(200, undefined, {
            bytes: archiveBytesA,
            url: endpoint.href,
          })
        : response(200, {
            name: "@fred-oss/design-tokens",
            versions: {
              "0.1.1-alpha.0": {
                name: "@fred-oss/design-tokens",
                version: "0.1.1-alpha.0",
                dist: { integrity: integrityA, tarball: tokenTarball },
              },
            },
          }),
    inspect: async () => ({ state: "absent" }),
  });
  assert.equal(result.state, "dry-run");
});

test("matching existing publication succeeds without invoking npm", async () => {
  const fixture = await preparedFixture();
  let mutations = 0;
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    environment: localEnvironment,
    runCommand: async (command, arguments_) => {
      if (command === "tar") return fixture.runCommand(command, arguments_);
      mutations += 1;
    },
    inspect: async () => ({ state: "matching" }),
  });
  assert.equal(outcome.state, "already-published");
  assert.equal(mutations, 0);
});

test("publication outcome preserves the selected registry and shell-quotes recovery data", async () => {
  const shellMarker = "FRED_COMMAND_MARKER";
  const backtickMarker = "FRED_BACKTICK_MARKER";
  const releaseDirectoryName = `release with 'quotes' $(touch ${shellMarker}) and \`touch ${backtickMarker}\``;
  const fixture = await preparedFixture("iframe-sdk", releaseDirectoryName);
  const registry = "http://127.0.0.1:4873/custom/";
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    environment: localEnvironment,
    registry,
    runCommand: fixture.runCommand,
    inspect: async (candidate) => {
      assert.equal(candidate.registry, registry);
      return { state: "matching" };
    },
  });
  assert.equal(outcome.registry, registry);
  assert.equal(
    outcome.verificationCommand,
    `make verify-release PACKAGE='iframe-sdk' RELEASE_DIR='${fixture.releaseDirectory.replaceAll("'", `'"'"'`)}' REGISTRY='${registry}'`,
  );
  const bin = path.join(fixture.root, "bin");
  const capture = path.join(fixture.root, "make-arguments.json");
  await mkdir(bin);
  const fakeMake = path.join(bin, "make");
  await writeFile(
    fakeMake,
    `#!/usr/bin/env node
import { writeFileSync } from "node:fs";
writeFileSync(process.env.FRED_TEST_CAPTURE, JSON.stringify(process.argv.slice(2)));
`,
  );
  await chmod(fakeMake, 0o755);
  await run("sh", ["-c", outcome.verificationCommand], {
    cwd: fixture.root,
    env: {
      ...process.env,
      FRED_TEST_CAPTURE: capture,
      PATH: `${bin}:${process.env.PATH}`,
    },
  });
  assert.deepEqual(JSON.parse(await readFile(capture, "utf8")), [
    "verify-release",
    "PACKAGE=iframe-sdk",
    `RELEASE_DIR=${fixture.releaseDirectory}`,
    `REGISTRY=${registry}`,
  ]);
  await assert.rejects(access(path.join(fixture.root, shellMarker)), {
    code: "ENOENT",
  });
  await assert.rejects(access(path.join(fixture.root, backtickMarker)), {
    code: "ENOENT",
  });
});

test("conflicting existing publication stops before npm", async () => {
  const fixture = await preparedFixture();
  let mutations = 0;
  await assert.rejects(
    publishRelease({
      packageName: "iframe-sdk",
      releaseDirectory: fixture.releaseDirectory,
      root: fixture.root,
      environment: localEnvironment,
      runCommand: async (command, arguments_) => {
        if (command === "tar") return fixture.runCommand(command, arguments_);
        mutations += 1;
      },
      inspect: async () => ({ state: "conflict" }),
    }),
    (error) => error.code === "version-conflict",
  );
  assert.equal(mutations, 0);
});

test("publication uploads exact bytes once and tolerates delayed visibility", async () => {
  const fixture = await preparedFixture();
  const states = ["absent", "absent", "matching"];
  const commands = [];
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    environment: localEnvironment,
    visibilityDelayMilliseconds: 0,
    runCommand: async (command, arguments_, options) => {
      if (command === "tar") return fixture.runCommand(command, arguments_);
      commands.push([command, arguments_, options]);
      return { stdout: "", stderr: "" };
    },
    inspect: async () => ({ state: states.shift() }),
    wait: async () => {},
  });
  assert.equal(outcome.state, "published");
  assert.equal(commands.length, 1);
  assert.equal(commands[0][0], "npm");
  assert.deepEqual(commands[0][1].slice(0, 2), [
    "publish",
    path.join(fixture.releaseDirectory, fixture.metadata.archive),
  ]);
  assert(commands[0][1].includes("--ignore-scripts"));
  assert(commands[0][1].includes("next"));
  assert(commands[0][1].includes("--provenance=false"));
  assert.equal(commands[0][2].stdio, "inherit");
  for (const selected of Object.values(releasePackages)) {
    const manifest = JSON.parse(
      await readFile(
        path.join(workspaceRoot, selected.workspace, "package.json"),
        "utf8",
      ),
    );
    assert.equal(manifest.publishConfig.provenance, true);
  }
});

test("OIDC publication preserves a matching GitHub workflow identity", async () => {
  const fixture = await preparedFixture();
  fixture.metadata.preparedBy = {
    kind: "github-actions",
    repository: "ThalesGroup/fred",
    workflow: "ThalesGroup/fred/.github/workflows/publish.yml@refs/heads/swift",
    runId: "41",
  };
  await writeFile(
    path.join(fixture.releaseDirectory, "release.json"),
    `${JSON.stringify(fixture.metadata, null, 2)}\n`,
  );
  const sourceCommit = fixture.metadata.sourceCommit;
  let publishArguments;
  let publishEnvironment;
  let oidcUserConfig;
  const states = ["absent", "matching"];
  const environment = {
    CI: "true",
    GITHUB_ACTIONS: "true",
    ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.test",
    ACTIONS_ID_TOKEN_REQUEST_TOKEN: "test",
    GITHUB_REPOSITORY: "ThalesGroup/fred",
    GITHUB_WORKFLOW_REF:
      "ThalesGroup/fred/.github/workflows/publish.yml@refs/heads/swift",
    GITHUB_SHA: sourceCommit,
  };
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    authMode: "oidc",
    environment,
    runCommand: async (command, arguments_, options) => {
      if (command === "tar") return fixture.runCommand(command, arguments_);
      if (command === "git") return { stdout: `${sourceCommit}\n`, stderr: "" };
      publishArguments = arguments_;
      publishEnvironment = options.env;
      oidcUserConfig = await readFile(
        publishEnvironment.NPM_CONFIG_USERCONFIG,
        "utf8",
      );
      return { stdout: "", stderr: "" };
    },
    inspect: async () => ({ state: states.shift() }),
  });
  assert.equal(outcome.state, "published");
  assert(publishArguments.includes("--provenance"));
  assert(!publishArguments.includes("--provenance=false"));
  assert.equal(publishEnvironment.GITHUB_SHA, sourceCommit);
  assert.equal(environment.GITHUB_SHA, sourceCommit);
  assert.equal(publishEnvironment.NODE_AUTH_TOKEN, undefined);
  assert.equal(oidcUserConfig, "");
});

test("OIDC publication rejects a different workflow source before npm", async () => {
  const fixture = await preparedFixture();
  fixture.metadata.preparedBy = {
    kind: "github-actions",
    repository: "ThalesGroup/fred",
    workflow: "ThalesGroup/fred/.github/workflows/publish.yml@refs/heads/swift",
    runId: "41",
  };
  await writeFile(
    path.join(fixture.releaseDirectory, "release.json"),
    `${JSON.stringify(fixture.metadata, null, 2)}\n`,
  );
  const sourceCommit = fixture.metadata.sourceCommit;
  const triggeringCommit = "b".repeat(40);
  const environment = {
    CI: "true",
    GITHUB_ACTIONS: "true",
    ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.test",
    ACTIONS_ID_TOKEN_REQUEST_TOKEN: "test",
    GITHUB_REPOSITORY: "ThalesGroup/fred",
    GITHUB_WORKFLOW_REF:
      "ThalesGroup/fred/.github/workflows/publish.yml@refs/heads/swift",
    GITHUB_SHA: triggeringCommit,
  };
  let registryReads = 0;
  let npmInvocations = 0;
  await assert.rejects(
    publishRelease({
      packageName: "iframe-sdk",
      releaseDirectory: fixture.releaseDirectory,
      root: fixture.root,
      authMode: "oidc",
      environment,
      runCommand: async (command, arguments_) => {
        if (command === "tar") return fixture.runCommand(command, arguments_);
        if (command === "git")
          return { stdout: `${sourceCommit}\n`, stderr: "" };
        npmInvocations += 1;
        return { stdout: "", stderr: "" };
      },
      inspect: async () => {
        registryReads += 1;
        return { state: "absent" };
      },
    }),
    (error) =>
      error.code === "provenance" &&
      error.message.includes("GitHub workflow source differs"),
  );
  assert.equal(environment.GITHUB_SHA, triggeringCommit);
  assert.equal(registryReads, 0);
  assert.equal(npmInvocations, 0);
});

test("OIDC publication dry run validates nonsecret identity without requesting credentials", async () => {
  const fixture = await preparedFixture();
  fixture.metadata.preparedBy = {
    kind: "github-actions",
    repository: "ThalesGroup/fred",
    workflow:
      "ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift",
    runId: "41",
  };
  await writeFile(
    path.join(fixture.releaseDirectory, "release.json"),
    `${JSON.stringify(fixture.metadata, null, 2)}\n`,
  );
  const environment = {
    CI: "true",
    GITHUB_ACTIONS: "true",
    GITHUB_REPOSITORY: "ThalesGroup/fred",
    GITHUB_WORKFLOW_REF: fixture.metadata.preparedBy.workflow,
    GITHUB_SHA: fixture.metadata.sourceCommit,
  };
  let npmInvocations = 0;
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    authMode: "oidc",
    dryRun: true,
    environment,
    runCommand: async (command, arguments_) => {
      if (command === "tar") return fixture.runCommand(command, arguments_);
      if (command === "git")
        return { stdout: `${fixture.metadata.sourceCommit}\n`, stderr: "" };
      npmInvocations += 1;
      return { stdout: "", stderr: "" };
    },
    inspect: async () => ({ state: "absent" }),
  });
  assert.equal(outcome.state, "dry-run");
  assert.equal(npmInvocations, 0);

  for (const changed of [
    { GITHUB_SHA: "b".repeat(40) },
    { GITHUB_REPOSITORY: "example/fork" },
  ]) {
    let registryReads = 0;
    await assert.rejects(
      publishRelease({
        packageName: "iframe-sdk",
        releaseDirectory: fixture.releaseDirectory,
        root: fixture.root,
        authMode: "oidc",
        dryRun: true,
        environment: { ...environment, ...changed },
        runCommand: async (command, arguments_) => {
          if (command === "tar") return fixture.runCommand(command, arguments_);
          if (command === "git")
            return { stdout: `${fixture.metadata.sourceCommit}\n`, stderr: "" };
          npmInvocations += 1;
          return { stdout: "", stderr: "" };
        },
        inspect: async () => {
          registryReads += 1;
          return { state: "absent" };
        },
      }),
      (error) => error.code === "provenance",
    );
    assert.equal(registryReads, 0);
  }

  const local = await preparedFixture();
  await assert.rejects(
    publishRelease({
      packageName: "iframe-sdk",
      releaseDirectory: local.releaseDirectory,
      root: local.root,
      authMode: "oidc",
      dryRun: true,
      environment,
      runCommand: async (command, arguments_) => {
        if (command === "tar") return local.runCommand(command, arguments_);
        if (command === "git")
          return { stdout: `${local.metadata.sourceCommit}\n`, stderr: "" };
        npmInvocations += 1;
        return { stdout: "", stderr: "" };
      },
      inspect: async () => ({ state: "absent" }),
    }),
    /prepared outside GitHub Actions/,
  );
  assert.equal(npmInvocations, 0);
});

test("token publication uses an isolated registry-scoped npm configuration", async () => {
  const fixture = await preparedFixture();
  const states = ["absent", "matching"];
  let invocation;
  let userConfigPath;
  let userConfig;
  let globalConfig;
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    authMode: "token",
    environment: { CI: "true", NODE_AUTH_TOKEN: "controlled-token" },
    runCommand: async (command, arguments_, options) => {
      if (command === "tar") return fixture.runCommand(command, arguments_);
      invocation = { arguments_, options };
      userConfigPath = options.env.NPM_CONFIG_USERCONFIG;
      userConfig = await readFile(userConfigPath, "utf8");
      globalConfig = await readFile(
        options.env.NPM_CONFIG_GLOBALCONFIG,
        "utf8",
      );
      return { stdout: "", stderr: "" };
    },
    inspect: async () => ({ state: states.shift() }),
  });
  assert.equal(outcome.state, "published");
  assert(invocation.arguments_.includes("--provenance=false"));
  assert.equal(invocation.options.stdio, undefined);
  assert.equal(
    userConfig,
    "//registry.npmjs.org/:_authToken=${NODE_AUTH_TOKEN}\n",
  );
  assert.equal(globalConfig, "");
  await assert.rejects(readFile(userConfigPath), { code: "ENOENT" });
});

test("definite npm authentication failures are not recorded as uncertain", async () => {
  for (const [npmCode, expected] of [
    ["E401", "registry-authentication"],
    ["E403", "registry-authorization"],
    ["EOTP", "registry-authentication"],
  ]) {
    const fixture = await preparedFixture();
    await assert.rejects(
      publishRelease({
        packageName: "iframe-sdk",
        releaseDirectory: fixture.releaseDirectory,
        root: fixture.root,
        environment: localEnvironment,
        runCommand: async (command, arguments_) => {
          if (command === "tar") return fixture.runCommand(command, arguments_);
          const error = new Error(`npm error code ${npmCode}`);
          error.code = npmCode;
          throw error;
        },
        inspect: async () => ({ state: "absent" }),
      }),
      (error) => error.code === expected,
    );
    await assert.rejects(
      readFile(path.join(fixture.releaseDirectory, "publish-result.json")),
      { code: "ENOENT" },
    );
  }

  const fixture = await preparedFixture();
  await assert.rejects(
    publishRelease({
      packageName: "iframe-sdk",
      releaseDirectory: fixture.releaseDirectory,
      root: fixture.root,
      environment: localEnvironment,
      runCommand: async (command, arguments_, options) => {
        if (command === "tar") return fixture.runCommand(command, arguments_);
        await writeFile(
          path.join(options.env.NPM_CONFIG_LOGS_DIR, "npm-debug.log"),
          "npm error code E401\n",
        );
        throw new Error("npm exited with code 1");
      },
      inspect: async () => ({ state: "absent" }),
    }),
    (error) => error.code === "registry-authentication",
  );
});

test("ambiguous upload writes an actionable uncertain result without retry", async () => {
  const fixture = await preparedFixture();
  let publishes = 0;
  await assert.rejects(
    publishRelease({
      packageName: "iframe-sdk",
      releaseDirectory: fixture.releaseDirectory,
      root: fixture.root,
      environment: localEnvironment,
      runCommand: async (command, arguments_) => {
        if (command === "tar") return fixture.runCommand(command, arguments_);
        publishes += 1;
        throw new Error("connection closed");
      },
      inspect: async () => ({ state: "absent" }),
    }),
    (error) =>
      error.code === "publication-uncertain" &&
      error.message.includes("make verify-release PACKAGE='iframe-sdk'"),
  );
  assert.equal(publishes, 1);
  const outcome = JSON.parse(
    await readFile(
      path.join(fixture.releaseDirectory, "publish-result.json"),
      "utf8",
    ),
  );
  assert.equal(outcome.state, "uncertain");
});

test("post-publication registry failure is uncertain and never republishes", async () => {
  const fixture = await preparedFixture();
  let publishes = 0;
  let inspections = 0;
  await assert.rejects(
    publishRelease({
      packageName: "iframe-sdk",
      releaseDirectory: fixture.releaseDirectory,
      root: fixture.root,
      environment: localEnvironment,
      runCommand: async (command, arguments_) => {
        if (command === "tar") return fixture.runCommand(command, arguments_);
        publishes += 1;
        return { stdout: "", stderr: "" };
      },
      inspect: async () => {
        inspections += 1;
        if (inspections === 1) return { state: "absent" };
        const error = new Error("registry timed out");
        error.code = "registry-timeout";
        throw error;
      },
    }),
    (error) =>
      error.code === "publication-uncertain" &&
      error.message.includes("make verify-release PACKAGE='iframe-sdk'"),
  );
  assert.equal(publishes, 1);
  assert.equal(inspections, 2);
});

test("publication dry run validates preflight but invokes no mutation", async () => {
  const fixture = await preparedFixture();
  let mutations = 0;
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    environment: localEnvironment,
    dryRun: true,
    runCommand: async (command, arguments_) => {
      if (command === "tar") return fixture.runCommand(command, arguments_);
      mutations += 1;
    },
    inspect: async () => ({ state: "absent" }),
  });
  assert.equal(outcome.state, "dry-run");
  assert.equal(mutations, 0);
});

test("authentication modes do not fall back and provenance stays truthful", () => {
  const localMetadata = {
    preparedBy: { kind: "local" },
    sourceCommit: "a".repeat(40),
  };
  assert.deepEqual(
    assertAuthentication({
      authMode: "local",
      dryRun: false,
      environment: {},
      metadata: localMetadata,
      operation: "publish",
    }),
    { provenance: false },
  );
  assert.throws(
    () =>
      assertAuthentication({
        authMode: "local",
        dryRun: false,
        environment: { CI: "true" },
        metadata: localMetadata,
        operation: "publish",
      }),
    /CI must select token or oidc/,
  );
  assert.throws(
    () =>
      assertAuthentication({
        authMode: "local",
        dryRun: false,
        environment: { NODE_AUTH_TOKEN: "token" },
        metadata: localMetadata,
        operation: "publish",
      }),
    /cannot be combined/,
  );
  assert.throws(
    () =>
      assertAuthentication({
        authMode: "token",
        dryRun: false,
        environment: { CI: "true" },
        metadata: localMetadata,
        operation: "publish",
      }),
    /NODE_AUTH_TOKEN/,
  );
  assert.throws(
    () =>
      assertAuthentication({
        authMode: "token",
        dryRun: false,
        environment: {
          CI: "true",
          NODE_AUTH_TOKEN: "token",
          ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.test",
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: "oidc",
        },
        metadata: localMetadata,
        operation: "publish",
      }),
    /cannot be combined with OIDC/,
  );
  assert.throws(
    () =>
      assertAuthentication({
        authMode: "token",
        dryRun: false,
        environment: {
          CI: "true",
          NODE_AUTH_TOKEN: "token",
          NPM_ID_TOKEN: "alternate-oidc",
        },
        metadata: localMetadata,
        operation: "publish",
      }),
    /cannot be combined with OIDC/,
  );
  assert.throws(
    () =>
      assertAuthentication({
        authMode: "oidc",
        dryRun: false,
        environment: {
          CI: "true",
          GITHUB_ACTIONS: "true",
          ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.test",
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: "test",
          GITHUB_REPOSITORY: "ThalesGroup/fred",
          GITHUB_WORKFLOW_REF: "workflow",
          GITHUB_SHA: "a".repeat(40),
        },
        metadata: localMetadata,
        operation: "publish",
      }),
    /prepared outside GitHub Actions/,
  );
  assert.deepEqual(
    assertAuthentication({
      authMode: "oidc",
      dryRun: false,
      environment: {
        CI: "true",
        GITHUB_ACTIONS: "true",
        ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.test",
        ACTIONS_ID_TOKEN_REQUEST_TOKEN: "test",
        GITHUB_REPOSITORY: "ThalesGroup/fred",
        GITHUB_WORKFLOW_REF: "workflow",
        GITHUB_SHA: "a".repeat(40),
      },
      metadata: {
        preparedBy: {
          kind: "github-actions",
          repository: "ThalesGroup/fred",
          workflow: "workflow",
          runId: "1",
        },
        sourceCommit: "a".repeat(40),
      },
      operation: "publish",
    }),
    { provenance: true },
  );
  assert.throws(
    () =>
      assertAuthentication({
        authMode: "oidc",
        dryRun: false,
        environment: {
          CI: "true",
          NODE_AUTH_TOKEN: "token",
          GITHUB_ACTIONS: "true",
          ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.test",
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: "oidc",
          GITHUB_REPOSITORY: "ThalesGroup/fred",
          GITHUB_WORKFLOW_REF: "workflow",
          GITHUB_SHA: "a".repeat(40),
        },
        metadata: {
          preparedBy: {
            kind: "github-actions",
            repository: "ThalesGroup/fred",
            workflow: "workflow",
            runId: "1",
          },
          sourceCommit: "a".repeat(40),
        },
        operation: "publish",
      }),
    /cannot be combined with npm token/,
  );
});

test("verification accepts matching bytes and rejects absence", async () => {
  const fixture = await preparedFixture();
  const verified = await verifyRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    runCommand: fixture.runCommand,
    inspect: async () => ({ state: "matching" }),
  });
  assert.equal(verified.state, "verified");
  await assert.rejects(
    verifyRelease({
      packageName: "iframe-sdk",
      releaseDirectory: fixture.releaseDirectory,
      root: fixture.root,
      runCommand: fixture.runCommand,
      inspect: async () => ({ state: "absent" }),
    }),
    (error) => error.code === "version-absent",
  );
});

test("all release inputs remain opaque across every actual Make boundary", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "fred-release-boundary-test-"),
  );
  const bin = path.join(directory, "bin");
  const capture = path.join(directory, "capture.jsonl");
  await mkdir(bin);
  const fakeNode = path.join(bin, "node");
  await writeFile(
    fakeNode,
    `#!${process.execPath}
import { appendFileSync } from "node:fs";
const names = ${JSON.stringify([
      "PACKAGE",
      "RELEASE_DIR",
      "AUTH_MODE",
      "DRY_RUN",
      "REGISTRY",
      "VERSION",
      "CHANNEL",
    ])};
appendFileSync(process.env.FRED_TEST_CAPTURE, JSON.stringify({
  argv: process.argv.slice(2),
  captured: Object.fromEntries(names.map((name) => [name, process.env["FRED_RELEASE_" + name]])),
  public: Object.fromEntries(names.map((name) => [name, process.env[name]])),
}) + "\\n");
`,
  );
  await chmod(fakeNode, 0o755);
  const valid = {
    PACKAGE: "iframe-sdk",
    RELEASE_DIR: "/tmp/release with 'quotes' $() and `ticks`",
    AUTH_MODE: "token",
    DRY_RUN: "1",
    REGISTRY: "http://127.0.0.1:4873/custom/",
    VERSION: "0.1.1-alpha.1",
    CHANNEL: "next-2026.10",
  };
  const targets = {
    "prepare-release": "prepare",
    publish: "publish",
    "verify-release": "verify",
    promote: "promote",
  };
  const invoke = async ({ target, environmentValues, commandValues = {} }) => {
    const environment = {
      ...process.env,
      PATH: `${bin}:${process.env.PATH}`,
      FRED_TEST_CAPTURE: capture,
    };
    for (const name of Object.keys(valid))
      delete environment[`FRED_RELEASE_${name}`];
    Object.assign(environment, environmentValues);
    const arguments_ = ["--no-print-directory", "-o", "node_modules", target];
    for (const [name, value] of Object.entries(commandValues))
      arguments_.push(`${name}=${value}`);
    await run("make", arguments_, {
      cwd: workspaceRoot,
      env: environment,
    });
    const records = (await readFile(capture, "utf8"))
      .trimEnd()
      .split("\n")
      .map((line) => JSON.parse(line));
    return records.slice(-2);
  };

  for (const [target, operation] of Object.entries(targets)) {
    const records = await invoke({ target, environmentValues: valid });
    assert.deepEqual(
      records.map(({ argv }) => argv),
      [
        ["scripts/release-preflight.mjs", operation],
        ["scripts/npm-release.mjs", operation],
      ],
    );
    for (const record of records) {
      assert.deepEqual(record.captured, valid);
      assert.deepEqual(record.public, {});
    }
  }

  const payloads = [
    (marker) => `$(printf REVIEW_INJECTION >${marker})`,
    (marker) => `"'; printf REVIEW_INJECTION >${marker}; : '"`,
    (marker) => `line-one\nprintf REVIEW_INJECTION >${marker}`,
    (marker) => `$(shell printf REVIEW_INJECTION >${marker})`,
    (marker) => `$(file >${marker},REVIEW_INJECTION)`,
    (marker) => `\`printf REVIEW_INJECTION >${marker}\``,
  ];
  let sequence = 0;
  for (const origin of ["environment", "command-line"])
    for (const field of Object.keys(valid))
      for (const payload of payloads) {
        const marker = path.join(directory, `${origin}-${field}-${sequence++}`);
        const value = payload(marker);
        const environmentValues = { ...valid };
        const commandValues = {};
        if (origin === "environment") environmentValues[field] = value;
        else {
          delete environmentValues[field];
          commandValues[field] = value;
        }
        const records = await invoke({
          target: "publish",
          environmentValues,
          commandValues,
        });
        for (const record of records)
          assert.equal(record.captured[field], value);
        assert.deepEqual(
          records.map(({ argv }) => argv),
          [
            ["scripts/release-preflight.mjs", "publish"],
            ["scripts/npm-release.mjs", "publish"],
          ],
        );
        await assert.rejects(access(marker), { code: "ENOENT" });
      }

  for (const origin of ["environment", "command-line"]) {
    const marker = path.join(directory, `internal-${origin}`);
    const injected = `$(shell printf REVIEW_INJECTION >${marker})`;
    const environmentValues = { ...valid };
    const commandValues = {};
    if (origin === "environment")
      environmentValues.FRED_RELEASE_PACKAGE = injected;
    else commandValues.FRED_RELEASE_PACKAGE = injected;
    const records = await invoke({
      target: "publish",
      environmentValues,
      commandValues,
    });
    for (const record of records)
      assert.equal(record.captured.PACKAGE, valid.PACKAGE);
    await assert.rejects(access(marker), { code: "ENOENT" });
  }

  const sideEffectBin = path.join(directory, "side-effect-bin");
  await mkdir(sideEffectBin);
  const fakeNpm = path.join(sideEffectBin, "npm");
  await writeFile(
    fakeNpm,
    `#!/bin/sh
printf side-effect > "$FRED_TEST_NESTED_MARKER"
exit 99
`,
  );
  await chmod(fakeNpm, 0o755);
  for (const origin of ["environment", "command-line"])
    for (const [field, invalidValue, expected] of [
      ["PACKAGE", "invalid", /PACKAGE must be exactly one of/],
      ["RELEASE_DIR", "invalid\npath", /single line/],
      ["AUTH_MODE", "fallback", /AUTH_MODE/],
      ["DRY_RUN", "sometimes", /DRY_RUN/],
      ["REGISTRY", "invalid\nregistry", /single line/],
      ["VERSION", "not-a-version", /exact semantic version/],
      ["VERSION", "1.2.3-alpha.01", /exact semantic version/],
      ["VERSION", "999999999999999999999.1.1", /exact semantic version/],
      ["CHANNEL", "1.2.3", /semantic-version range/],
      ["CHANNEL", "1.2.x-alpha", /semantic-version range/],
      ["CHANNEL", "x.0", /semantic-version range/],
      ["CHANNEL", "1.x.0", /semantic-version range/],
      ["CHANNEL", "0.x.1-alpha", /semantic-version range/],
    ]) {
      const marker = path.join(directory, `invalid-${origin}-${field}`);
      const environmentValues = {
        ...valid,
        CI: "true",
        FRED_TEST_NESTED_MARKER: marker,
        PATH: `${sideEffectBin}:${process.env.PATH}`,
      };
      const commandValues = {};
      if (origin === "environment") environmentValues[field] = invalidValue;
      else {
        delete environmentValues[field];
        commandValues[field] = invalidValue;
      }
      const arguments_ = ["--no-print-directory", "-B", "prepare-release"];
      for (const [name, value] of Object.entries(commandValues))
        arguments_.push(`${name}=${value}`);
      await assert.rejects(
        run("make", arguments_, {
          cwd: workspaceRoot,
          env: environmentValues,
        }),
        expected,
      );
      await assert.rejects(access(marker), { code: "ENOENT" });
    }
});

test("invalid promotion inputs perform no registry read or mutation", async () => {
  let registryReads = 0;
  let mutations = 0;
  for (const invalid of [
    { version: "0.1.1$(printf injected)", channel: "latest" },
    { version: "0.1.1", channel: "latest\nprintf injected" },
  ])
    await assert.rejects(
      promoteRelease({
        packageName: "iframe-sdk",
        ...invalid,
        dryRun: true,
        authMode: "token",
        environment: { CI: "true" },
        root: await fixtureRoot(),
        inspect: async () => {
          registryReads += 1;
          return { state: "present" };
        },
        runCommand: async () => {
          mutations += 1;
          return { stdout: "", stderr: "" };
        },
      }),
    );
  assert.equal(registryReads, 0);
  assert.equal(mutations, 0);
});

test("promotion verifies existence and dry run never changes a tag", async () => {
  const root = await fixtureRoot();
  let mutations = 0;
  const result = await promoteRelease({
    packageName: "iframe-sdk",
    version: "0.1.1-alpha.1",
    channel: "latest",
    root,
    environment: localEnvironment,
    dryRun: true,
    inspect: async () => ({ state: "present" }),
    runCommand: async () => {
      mutations += 1;
    },
  });
  assert.equal(result.state, "dry-run");
  assert.equal(mutations, 0);
  await assert.rejects(
    promoteRelease({
      packageName: "iframe-sdk",
      version: "0.1.1-alpha.1",
      channel: "latest",
      root,
      environment: localEnvironment,
      inspect: async () => ({ state: "absent" }),
    }),
    (error) => error.code === "version-absent",
  );

  let localInvocation;
  const promoted = await promoteRelease({
    packageName: "iframe-sdk",
    version: "0.1.1-alpha.1",
    channel: "latest",
    root,
    environment: localEnvironment,
    inspect: async () => ({ state: "present" }),
    runCommand: async (command, arguments_, options) => {
      localInvocation = { command, arguments_, options };
      return { stdout: "", stderr: "" };
    },
  });
  assert.equal(promoted.state, "promoted");
  assert.equal(localInvocation.command, "npm");
  assert.equal(localInvocation.options.stdio, "inherit");

  let tokenConfig;
  const tokenPromoted = await promoteRelease({
    packageName: "iframe-sdk",
    version: "0.1.1-alpha.1",
    channel: "latest",
    root,
    authMode: "token",
    environment: { CI: "true", NODE_AUTH_TOKEN: "controlled-token" },
    inspect: async () => ({ state: "present" }),
    runCommand: async (_command, _arguments, options) => {
      tokenConfig = await readFile(options.env.NPM_CONFIG_USERCONFIG, "utf8");
      return { stdout: "", stderr: "" };
    },
  });
  assert.equal(tokenPromoted.state, "promoted");
  assert.equal(
    tokenConfig,
    "//registry.npmjs.org/:_authToken=${NODE_AUTH_TOKEN}\n",
  );
});
