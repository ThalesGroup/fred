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

import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const developmentNames = {
  designTokens: "@fred-oss/design-tokens",
  ui: "@fred-oss/ui",
  iframeSdk: "@fred-oss/iframe-sdk",
};

export async function parameterizeConsumerSources(root, contract, roles) {
  const replacements = roles
    .map((role) => [developmentNames[role], contract.packages[role].name])
    .filter(([from, to]) => from !== to);
  if (replacements.length === 0) return;
  for (const entry of await readdir(root, {
    recursive: true,
    withFileTypes: true,
  })) {
    if (!entry.isFile() || !/\.(?:json|[cm]?[jt]sx?)$/.test(entry.name))
      continue;
    const filePath = path.join(entry.parentPath, entry.name);
    let content = await readFile(filePath, "utf8");
    for (const [from, to] of replacements)
      content = content.replaceAll(from, to);
    await writeFile(filePath, content);
  }
}
