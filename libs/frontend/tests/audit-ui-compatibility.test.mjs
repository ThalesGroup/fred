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
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { auditCompatibility } from "../scripts/audit-ui-compatibility.mjs";

test("the reviewed checkout uses only implemented literal button sizes", async () => {
  const evidence = await auditCompatibility();
  assert(evidence.buttonCalls.length > 200);
  assert.equal(
    evidence.buttonCalls.some(({ size }) => size === "xs"),
    false,
  );
  assert(
    evidence.helperFiles.some((file) => file.endsWith("shared/utils/Type.ts")),
  );
});

test("an unsupported literal size fails the compatibility audit", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-ui-audit-"));
  await mkdir(path.join(temporary, "component"));
  await writeFile(
    path.join(temporary, "component/Bad.tsx"),
    'export const Bad = () => <IconButton size="xs" />;\n',
  );
  await assert.rejects(
    auditCompatibility({ sourceRoot: temporary }),
    /unsupported IconButton size xs/,
  );
});
