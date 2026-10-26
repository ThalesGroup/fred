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

import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { readReleaseInputs } from "./release-operation-inputs.mjs";
import {
  assertReleaseToolchain,
  loadReleaseToolchain,
} from "./release-toolchain.mjs";

export async function main(argv = process.argv, environment = process.env) {
  const operation = argv[2];
  if (argv.length !== 3)
    throw new Error(
      "release inputs must be passed through the Make environment boundary",
    );
  if (!["prepare", "publish", "verify", "promote"].includes(operation))
    throw new Error("operation must be prepare, publish, verify, or promote");
  readReleaseInputs({ environment, operation });
  if (operation === "prepare") {
    const expected = await loadReleaseToolchain();
    const npm = execFileSync("npm", ["--version"], {
      encoding: "utf8",
      env: environment,
    }).trim();
    assertReleaseToolchain(expected, { node: process.versions.node, npm });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    await main();
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
