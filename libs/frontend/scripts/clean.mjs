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
import { rm } from "node:fs/promises";
import path from "node:path";

const workspaceRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

await Promise.all([
  rm(path.join(workspaceRoot, "target"), { recursive: true, force: true }),
  rm(path.join(workspaceRoot, "design-tokens/dist"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "design-tokens/LICENSE"), { force: true }),
  rm(path.join(workspaceRoot, "design-tokens/licenses"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "ui/.generated"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "ui/dist"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "ui/LICENSE"), { force: true }),
  rm(path.join(workspaceRoot, "ui/build-evidence.json"), { force: true }),
  rm(path.join(workspaceRoot, "ui/licenses"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "iframe-sdk/.generated"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "iframe-sdk/dist"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "iframe-sdk/LICENSE"), { force: true }),
  rm(path.join(workspaceRoot, "iframe-sdk/build-evidence.json"), {
    force: true,
  }),
]);
