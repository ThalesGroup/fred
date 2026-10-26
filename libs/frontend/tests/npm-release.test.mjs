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
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertAuthentication,
  inspectExactVersion,
  prepareRelease,
  promoteRelease,
  publishRelease,
  releasePackages,
  resolveUiDesignTokens,
  selectPackage,
  validateReleaseDirectory,
  verifyRelease,
  workspaceRoot,
} from "../scripts/npm-release.mjs";
import { sha512Integrity } from "../scripts/release-evidence.mjs";

const integrityA = `sha512-${Buffer.alloc(64, 1).toString("base64")}`;
const integrityB = `sha512-${Buffer.alloc(64, 2).toString("base64")}`;

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
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

async function preparedFixture(packageName = "iframe-sdk") {
  const root = await fixtureRoot();
  const selected = selectPackage(packageName);
  const manifest = JSON.parse(
    await readFile(path.join(root, selected.workspace, "package.json"), "utf8"),
  );
  const releaseDirectory = path.join(root, "release");
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
    loadContract: async () => ({ packages: {} }),
    pack: async ({ validate }) => {
      calls.push(["pack", validate]);
      return { archivePath };
    },
    runChecks: async ({ selected, integrity }) =>
      calls.push(["checks", selected.package, integrity]),
    runCommand: async (command, arguments_) => {
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
      loadContract: async () => ({
        packages: {
          designTokens: { name: "@fred-oss/design-tokens" },
        },
      }),
      fetchImpl: async () =>
        response(200, {
          name: "@fred-oss/design-tokens",
          versions: {
            "0.1.1-alpha.0": {
              name: "@fred-oss/design-tokens",
              version: "0.1.1-alpha.0",
              dist: { integrity: integrityA },
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
      loadContract: async () => ({ packages: {} }),
      pack: async () => {
        packed = true;
        return {};
      },
      runCommand: async (command, arguments_) => ({
        stdout:
          command === "git" && arguments_[0] === "status"
            ? " M design-tokens/package.json\n"
            : `${"c".repeat(40)}\n`,
      }),
    }),
    (error) => error.code === "dirty-source",
  );
  assert.equal(packed, false);
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
      loadContract: async () => ({ packages: {} }),
      pack: async () => ({ archivePath }),
      runChecks: async () => {},
      runCommand: async (command, arguments_) => {
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
        fetchImpl: async () =>
          response(200, {
            name: input.name,
            version: input.version,
            dist: { integrity: integrityA },
          }),
      })
    ).state,
    "matching",
  );
  assert.equal(
    (
      await inspectExactVersion({
        ...input,
        fetchImpl: async () =>
          response(200, {
            name: input.name,
            version: input.version,
            dist: { integrity: integrityB },
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
    fetchImpl: async () =>
      response(200, {
        name: "@fred-oss/design-tokens",
        versions: {
          "0.1.0-alpha.1": {
            name: "@fred-oss/design-tokens",
            version: "0.1.0-alpha.1",
            dist: { integrity: integrityA },
          },
          "0.1.1-alpha.0": {
            name: "@fred-oss/design-tokens",
            version: "0.1.1-alpha.0",
            dist: { integrity: integrityB },
          },
          "0.2.0-alpha.0": {
            name: "@fred-oss/design-tokens",
            version: "0.2.0-alpha.0",
            dist: { integrity: integrityA },
          },
          "1.0.0": {
            name: "@fred-oss/design-tokens",
            version: "1.0.0",
            dist: { integrity: integrityA },
          },
        },
      }),
  });
  assert.equal(resolved.coordinate, "@fred-oss/design-tokens@0.1.1-alpha.0");
  assert.equal(resolved.integrity, integrityB);
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
    dryRun: true,
    runCommand: fixture.runCommand,
    loadContract: async () => ({
      packages: { designTokens: { name: "@fred-oss/design-tokens" } },
    }),
    fetchImpl: async () =>
      response(200, {
        name: "@fred-oss/design-tokens",
        versions: {
          "0.1.1-alpha.0": {
            name: "@fred-oss/design-tokens",
            version: "0.1.1-alpha.0",
            dist: { integrity: integrityA },
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
    runCommand: async (command, arguments_) => {
      if (command === "tar") return fixture.runCommand(command, arguments_);
      mutations += 1;
    },
    inspect: async () => ({ state: "matching" }),
  });
  assert.equal(outcome.state, "already-published");
  assert.equal(mutations, 0);
});

test("conflicting existing publication stops before npm", async () => {
  const fixture = await preparedFixture();
  let mutations = 0;
  await assert.rejects(
    publishRelease({
      packageName: "iframe-sdk",
      releaseDirectory: fixture.releaseDirectory,
      root: fixture.root,
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

test("OIDC publication binds provenance to a transferred release source", async () => {
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
  let publishArguments;
  let publishEnvironment;
  let oidcUserConfig;
  const states = ["absent", "matching"];
  const outcome = await publishRelease({
    packageName: "iframe-sdk",
    releaseDirectory: fixture.releaseDirectory,
    root: fixture.root,
    authMode: "oidc",
    environment: {
      CI: "true",
      GITHUB_ACTIONS: "true",
      ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.test",
      ACTIONS_ID_TOKEN_REQUEST_TOKEN: "test",
      GITHUB_REPOSITORY: "ThalesGroup/fred",
      GITHUB_WORKFLOW_REF:
        "ThalesGroup/fred/.github/workflows/publish.yml@refs/heads/swift",
      GITHUB_SHA: triggeringCommit,
    },
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
  assert.notEqual(publishEnvironment.GITHUB_SHA, triggeringCommit);
  assert.equal(publishEnvironment.NODE_AUTH_TOKEN, undefined);
  assert.equal(oidcUserConfig, "");
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
      runCommand: async (command, arguments_) => {
        if (command === "tar") return fixture.runCommand(command, arguments_);
        publishes += 1;
        throw new Error("connection closed");
      },
      inspect: async () => ({ state: "absent" }),
    }),
    (error) =>
      error.code === "publication-uncertain" &&
      error.message.includes("make verify-release PACKAGE=iframe-sdk"),
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
      error.message.includes("make verify-release PACKAGE=iframe-sdk"),
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

test("promotion verifies existence and dry run never changes a tag", async () => {
  const root = await fixtureRoot();
  let mutations = 0;
  const result = await promoteRelease({
    packageName: "iframe-sdk",
    version: "0.1.1-alpha.1",
    channel: "latest",
    root,
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
