import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

import ts from "typescript";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(scriptDirectory, "..");
const repositoryRoot = path.resolve(workspaceRoot, "../..");
const defaultSourceRoot = path.join(repositoryRoot, "apps/frontend/src");
const buttonSizes = new Set(["2xs", "small", "medium"]);

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function position(source, node) {
  const { line, character } = source.getLineAndCharacterOfPosition(
    node.getStart(source),
  );
  return { line: line + 1, column: character + 1 };
}

export async function auditCompatibility({
  sourceRoot = defaultSourceRoot,
} = {}) {
  const entries = await readdir(sourceRoot, { recursive: true });
  const files = entries
    .filter((entry) => /\.[cm]?tsx?$/.test(entry))
    .map((entry) => path.join(sourceRoot, entry))
    .sort();
  const buttonCalls = [];
  const dynamicIconFiles = new Set();
  const helperFiles = new Set();

  for (const file of files) {
    const sourceText = await readFile(file, "utf8");
    const source = ts.createSourceFile(
      file,
      sourceText,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX,
    );
    const relativePath = path.relative(repositoryRoot, file);
    if (
      /\b(?:IconCategory|IconType|isCustomIcon|toIconType|materialIcons)\b/.test(
        sourceText,
      )
    ) {
      helperFiles.add(relativePath);
    }
    if (
      /agentIconName|\.icon\b|as\s+(?:IconType|MaterialIconType)/.test(
        sourceText,
      )
    ) {
      dynamicIconFiles.add(relativePath);
    }

    function visit(node) {
      if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        const tag = node.tagName.getText(source);
        if (tag === "Button" || tag === "IconButton") {
          const sizeAttribute = node.attributes.properties.find(
            (attribute) =>
              ts.isJsxAttribute(attribute) &&
              attribute.name.getText(source) === "size",
          );
          let size = "indirect";
          if (
            sizeAttribute &&
            ts.isJsxAttribute(sizeAttribute) &&
            sizeAttribute.initializer
          ) {
            if (ts.isStringLiteral(sizeAttribute.initializer))
              size = sizeAttribute.initializer.text;
            else if (
              ts.isJsxExpression(sizeAttribute.initializer) &&
              sizeAttribute.initializer.expression &&
              ts.isStringLiteral(sizeAttribute.initializer.expression)
            ) {
              size = sizeAttribute.initializer.expression.text;
            }
          }
          assert(
            size === "indirect" || buttonSizes.has(size),
            `${relativePath}: unsupported ${tag} size ${size}`,
          );
          buttonCalls.push({
            component: tag,
            size,
            ...position(source, node),
            path: relativePath,
          });
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(source);
  }

  return {
    reviewedCommit: "c855853371a9baedf7fee22a02ed97c2f80bfde2",
    allowedButtonSizes: [...buttonSizes],
    buttonCalls,
    helperFiles: [...helperFiles].sort(),
    dynamicIconFiles: [...dynamicIconFiles].sort(),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const evidence = await auditCompatibility();
  const evidencePath = optionValue("--evidence");
  if (evidencePath) {
    const resolved = path.resolve(workspaceRoot, evidencePath);
    await mkdir(path.dirname(resolved), { recursive: true });
    await writeFile(resolved, `${JSON.stringify(evidence, null, 2)}\n`);
  }
  process.stdout.write(
    `${JSON.stringify({ buttonCalls: evidence.buttonCalls.length, helperFiles: evidence.helperFiles.length, dynamicIconFiles: evidence.dynamicIconFiles.length })}\n`,
  );
}
