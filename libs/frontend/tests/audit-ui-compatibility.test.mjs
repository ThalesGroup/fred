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
