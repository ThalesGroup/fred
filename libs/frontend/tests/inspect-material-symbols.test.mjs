import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  inspectMaterialSymbols,
  workspaceRoot,
} from "../scripts/inspect-material-symbols.mjs";

const repositoryRoot = path.resolve(workspaceRoot, "../..");
const fontPath = path.join(
  repositoryRoot,
  "apps/frontend/src/assets/fonts/material-symbols-outlined.woff2",
);
const typesPath = path.join(
  repositoryRoot,
  "apps/frontend/src/rework/components/shared/utils/Type.ts",
);

test("the canonical font supports the complete reviewed icon inventory", async () => {
  const evidence = await inspectMaterialSymbols();
  assert.equal(
    evidence.sha256,
    "98817d23c038afb643c659819b194fa4146880c54f2f14d12c1710a5c41760d7",
  );
  assert(evidence.glyphs.includes("info"));
});

test("an unsupported public glyph fails inspection", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-glyph-"));
  const source = await readFile(typesPath, "utf8");
  const changed = source.replace(
    '  "book_2",',
    '  "book_2",\n  "not_a_fred_material_symbol",',
  );
  const changedTypes = path.join(temporary, "Type.ts");
  await writeFile(changedTypes, changed);
  await assert.rejects(
    inspectMaterialSymbols({ typesPath: changedTypes }),
    /unsupported Material Symbols names: not_a_fred_material_symbol/,
  );
});

test("a modified or truncated binary fails provenance inspection", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-font-"));
  const changedFont = path.join(temporary, "font.woff2");
  const binary = await readFile(fontPath);
  await writeFile(changedFont, binary.subarray(0, binary.length - 1));
  await assert.rejects(
    inspectMaterialSymbols({ fontPath: changedFont }),
    /binary size differs from provenance/,
  );
});
