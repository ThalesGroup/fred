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

import { fileURLToPath } from "node:url";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";

import { run } from "./process.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(scriptDirectory, "..");
const fixtureRoot = path.join(workspaceRoot, "fixtures/iframe-sdk-consumer");
export const iframeSdkConsumerCache = path.join(
  workspaceRoot,
  "target/iframe-sdk-consumer-cache",
);

export async function provisionIframeSdkConsumer() {
  await rm(iframeSdkConsumerCache, { recursive: true, force: true });
  await mkdir(iframeSdkConsumerCache, { recursive: true });
  await run(
    "npm",
    [
      "ci",
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
      "--cache",
      iframeSdkConsumerCache,
    ],
    {
      cwd: fixtureRoot,
      env: {
        ...process.env,
        npm_config_audit: "false",
        npm_config_fund: "false",
      },
    },
  );
  await rm(path.join(fixtureRoot, "node_modules"), {
    recursive: true,
    force: true,
  });
  return {
    cache: iframeSdkConsumerCache,
    lockfile: path.join(fixtureRoot, "package-lock.json"),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await provisionIframeSdkConsumer(), null, 2)}\n`,
  );
}
