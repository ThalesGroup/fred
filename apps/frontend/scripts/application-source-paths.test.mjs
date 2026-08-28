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
import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, test } from "node:test";

import { discoverApplicationFrontendDirectories } from "./application-source-paths.mjs";

const temporaryDirectories = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

test("allows only regular application frontend directories", async () => {
  const applicationsDirectory = await mkdtemp(resolve(tmpdir(), "fred-app-source-paths-"));
  temporaryDirectories.push(applicationsDirectory);

  const firstFrontend = resolve(applicationsDirectory, "first/frontend");
  const secondBackend = resolve(applicationsDirectory, "second/backend");
  const thirdFrontend = resolve(applicationsDirectory, "third/frontend");
  const thirdBackend = resolve(applicationsDirectory, "third/backend");
  await mkdir(firstFrontend, { recursive: true });
  await mkdir(secondBackend, { recursive: true });
  await mkdir(thirdFrontend, { recursive: true });
  await mkdir(thirdBackend, { recursive: true });
  await writeFile(resolve(applicationsDirectory, "README.md"), "Packages\n", "utf8");
  await symlink(secondBackend, resolve(applicationsDirectory, "second/frontend"), "dir");
  await symlink(thirdBackend, resolve(thirdFrontend, "backend-link"), "dir");

  assert.deepEqual(discoverApplicationFrontendDirectories(applicationsDirectory), [firstFrontend]);
});

test("returns no paths when the package root is absent", () => {
  assert.deepEqual(discoverApplicationFrontendDirectories("/missing/application-packages"), []);
});
