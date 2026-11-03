// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));

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
