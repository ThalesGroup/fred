import assert from "node:assert/strict";

import ts from "typescript";

function scriptKind(fileName) {
  if (fileName.endsWith(".d.ts") || fileName.endsWith(".ts")) {
    return ts.ScriptKind.TS;
  }
  if (fileName.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (fileName.endsWith(".jsx")) return ts.ScriptKind.JSX;
  return ts.ScriptKind.JS;
}

function diagnosticText(diagnostic) {
  return ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n");
}

function literalSpecifier(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  return null;
}

function importTypeSpecifier(node) {
  if (!ts.isLiteralTypeNode(node.argument)) return null;
  return literalSpecifier(node.argument.literal);
}

export function inspectModuleReferences(content, { fileName, mode }) {
  assert(
    ["runtime", "declaration"].includes(mode),
    "invalid reference scan mode",
  );
  const source = ts.createSourceFile(
    fileName,
    content,
    ts.ScriptTarget.ESNext,
    true,
    scriptKind(fileName),
  );
  assert.equal(
    source.parseDiagnostics.length,
    0,
    `${fileName} has malformed module syntax: ${source.parseDiagnostics
      .map(diagnosticText)
      .join("; ")}`,
  );

  const references = [];
  const add = (specifier, kind) => {
    assert.notEqual(
      specifier,
      null,
      `${fileName} has a non-literal ${kind} reference`,
    );
    references.push({ specifier, kind });
  };

  if (mode === "declaration") {
    for (const reference of source.referencedFiles) {
      references.push({
        specifier: reference.fileName,
        kind: "reference-path",
      });
    }
    for (const reference of source.typeReferenceDirectives) {
      references.push({
        specifier: reference.fileName,
        kind: "reference-types",
      });
    }
  }

  function visit(node) {
    if (ts.isImportDeclaration(node)) {
      add(literalSpecifier(node.moduleSpecifier), "static import");
    } else if (ts.isExportDeclaration(node) && node.moduleSpecifier) {
      add(literalSpecifier(node.moduleSpecifier), "re-export");
    } else if (
      ts.isImportEqualsDeclaration(node) &&
      ts.isExternalModuleReference(node.moduleReference)
    ) {
      add(
        node.moduleReference.expression
          ? literalSpecifier(node.moduleReference.expression)
          : null,
        "import-equals",
      );
    } else if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword
    ) {
      assert(
        node.arguments.length === 1 || node.arguments.length === 2,
        `${fileName} has a dynamic import without a valid module specifier`,
      );
      add(literalSpecifier(node.arguments[0]), "dynamic import");
    } else if (mode === "declaration" && ts.isImportTypeNode(node)) {
      add(importTypeSpecifier(node), "declaration import type");
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
  return references;
}
