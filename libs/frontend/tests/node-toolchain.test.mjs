// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFile,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { loadReleaseToolchain } from "../scripts/release-toolchain.mjs";

const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));

test("current release policies agree with the exact repository Node baseline", async () => {
  const node = (
    await readFile(path.join(repositoryRoot, ".nvmrc"), "utf8")
  ).trim();
  assert.match(node, /^24\.\d+\.\d+$/);
  for (const policy of [
    "development-fixture-contract.json",
    "proposed-release-contract.json",
  ]) {
    const selected = await loadReleaseToolchain(
      path.join(repositoryRoot, "libs/frontend/release", policy),
    );
    assert.equal(selected.node, node);
  }
  const dockerBuild = spawnSync("make", ["-n", "docker-build"], {
    cwd: path.join(repositoryRoot, "apps/frontend"),
    encoding: "utf8",
  });
  assert.equal(dockerBuild.status, 0, dockerBuild.stderr);
  assert(dockerBuild.stdout.includes(`--build-arg NODE_VERSION=${node}`));
});

test("release preparation rejects a policy that diverges from .nvmrc", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-node-policy-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const policy = path.join(root, "policy.json");
  await writeFile(
    policy,
    JSON.stringify({
      releaseToolchain: { node: "24.15.0", npm: "11.19.0" },
      applicationToolchain: { node: "24.15.0", npm: "11.19.0" },
    }),
  );
  await assert.rejects(loadReleaseToolchain(policy), /differs from .nvmrc/);
});

test("devcontainer preparation reads the pin independently of the working directory", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-node-container-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const scripts = path.join(root, ".devcontainer/scripts");
  await mkdir(scripts, { recursive: true });
  for (const relative of [
    ".devcontainer/scripts/prepare-build.sh",
    ".devcontainer/Dockerfile-devcontainer",
    ".nvmrc",
  ])
    await copyFile(
      path.join(repositoryRoot, relative),
      path.join(root, relative),
    );
  const run = () =>
    spawnSync("bash", [path.join(scripts, "prepare-build.sh")], {
      cwd: os.tmpdir(),
      env: { ...process.env, HOME: root },
      encoding: "utf8",
    });
  const result = run();
  assert.equal(result.status, 0, result.stderr);
  const node = (await readFile(path.join(root, ".nvmrc"), "utf8")).trim();
  const generated = await readFile(
    path.join(root, ".devcontainer/target/Dockerfile-devcontainer"),
    "utf8",
  );
  assert(generated.startsWith(`ARG NODE_VERSION=${node}\n`));
  assert(generated.includes("FROM mirror.gcr.io/node:${NODE_VERSION}"));
  await writeFile(path.join(root, ".nvmrc"), "24\n");
  assert.notEqual(run().status, 0);
});

test("application and producer builds reject unsupported Node before invoking npm with a cached dependency tree", async (context) => {
  const bin = await mkdtemp(path.join(os.tmpdir(), "fred-node-toolchain-"));
  context.after(() => rm(bin, { recursive: true, force: true }));
  await writeFile(
    path.join(bin, "node"),
    '#!/bin/sh\nprintf "%s\\n" "$FRED_TEST_NODE_VERSION"\n',
    { mode: 0o755 },
  );
  const npmLog = path.join(bin, "npm-calls");
  await writeFile(
    path.join(bin, "npm"),
    '#!/bin/sh\nprintf "%s\\n" "$*" >> "$FRED_TEST_NPM_LOG"\n',
    { mode: 0o755 },
  );
  for (const directory of ["apps/frontend", "libs/frontend"]) {
    for (const version of [
      "22.22.2",
      "24.20.999",
      "24.21.0",
      "24.22.0",
      "25.0.0",
      "26.0.0",
    ]) {
      await writeFile(npmLog, "");
      const result = spawnSync(
        "make",
        ["--no-print-directory", "-o", "node_modules", "build"],
        {
          cwd: path.join(repositoryRoot, directory),
          env: {
            ...process.env,
            PATH: `${bin}${path.delimiter}${process.env.PATH}`,
            FRED_TEST_NODE_VERSION: version,
            FRED_TEST_NPM_LOG: npmLog,
          },
          encoding: "utf8",
        },
      );
      assert.ifError(result.error);
      const npmCalls = await readFile(npmLog, "utf8");
      if (["24.21.0", "24.22.0"].includes(version)) {
        assert.equal(result.status, 0, result.stderr);
        assert.equal(npmCalls, "run build\n");
      } else {
        assert.notEqual(result.status, 0, `${directory}: ${version}`);
        assert.match(result.stderr, /Node.js >=24\.21\.0 <25 is required/);
        assert.equal(npmCalls, "");
      }
    }
  }
});
