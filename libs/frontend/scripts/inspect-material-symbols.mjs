import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import * as fontkit from "fontkit";
import ts from "typescript";

import { UI_FONT_SOURCE } from "./package-inputs.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const workspaceRoot = path.resolve(scriptDirectory, "..");
const repositoryRoot = path.resolve(workspaceRoot, "../..");
const defaultTypesPath = path.join(
  repositoryRoot,
  "apps/frontend/src/rework/components/shared/utils/Type.ts",
);
const defaultFontPath = path.join(repositoryRoot, UI_FONT_SOURCE.sourcePath);

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function readMaterialIconNames(typesPath) {
  const sourceText = await readFile(typesPath, "utf8");
  const source = ts.createSourceFile(
    typesPath,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  let names;
  source.forEachChild((node) => {
    if (!ts.isVariableStatement(node)) return;
    for (const declaration of node.declarationList.declarations) {
      if (declaration.name.getText(source) !== "materialIcons") continue;
      let initializer = declaration.initializer;
      while (
        initializer &&
        (ts.isAsExpression(initializer) ||
          ts.isSatisfiesExpression(initializer) ||
          ts.isParenthesizedExpression(initializer))
      ) {
        initializer = initializer.expression;
      }
      assert(initializer && ts.isArrayLiteralExpression(initializer));
      names = initializer.elements.map((element) => {
        assert(
          ts.isStringLiteral(element),
          "materialIcons must contain string literals",
        );
        return element.text;
      });
    }
  });
  assert(names, `materialIcons was not found in ${typesPath}`);
  assert.equal(
    new Set(names).size,
    names.length,
    "materialIcons contains duplicates",
  );
  return names;
}

export async function inspectMaterialSymbols({
  fontPath = defaultFontPath,
  typesPath = defaultTypesPath,
  expectedHash = UI_FONT_SOURCE.sha256,
  expectedSize = UI_FONT_SOURCE.size,
} = {}) {
  const content = await readFile(fontPath);
  const fileStat = await stat(fontPath);
  assert.equal(
    fileStat.size,
    expectedSize,
    "Material Symbols binary size differs from provenance",
  );
  assert.equal(
    sha256(content),
    expectedHash,
    "Material Symbols binary hash differs from provenance",
  );

  const font = fontkit.openSync(fontPath);
  const iconNames = await readMaterialIconNames(typesPath);
  const unsupported = iconNames.filter((name) => {
    const run = font.layout(name, ["liga"]);
    return run.glyphs.length !== 1 || run.glyphs[0].id === 0;
  });
  assert.deepEqual(
    unsupported,
    [],
    `unsupported Material Symbols names: ${unsupported.join(", ")}`,
  );

  return {
    source: UI_FONT_SOURCE.sourcePath,
    upstream: UI_FONT_SOURCE.upstream,
    byteSize: fileStat.size,
    sha256: expectedHash,
    font: {
      familyName: font.familyName,
      fullName: font.fullName,
      postscriptName: font.postscriptName,
      subfamilyName: font.subfamilyName,
      version: font.version,
    },
    glyphCount: iconNames.length,
    glyphs: iconNames,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const evidence = await inspectMaterialSymbols({
    fontPath: optionValue("--font") ?? defaultFontPath,
    typesPath: optionValue("--types") ?? defaultTypesPath,
  });
  const evidencePath = optionValue("--evidence");
  if (evidencePath) {
    const resolved = path.resolve(workspaceRoot, evidencePath);
    await mkdir(path.dirname(resolved), { recursive: true });
    await writeFile(resolved, `${JSON.stringify(evidence, null, 2)}\n`);
  }
  process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
}
