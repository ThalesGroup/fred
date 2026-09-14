import assert from "node:assert/strict";
import test from "node:test";

import { inspectModuleReferences } from "../scripts/module-references.mjs";

test("inspects runtime imports, re-exports, comments, and literal templates", () => {
  const references = inspectModuleReferences(
    `
      import /* comment */ "./side-effect.js";
      import value from "./value.js";
      export { other } from "./other.js";
      export * from "./all.js";
      void import(/* comment */ "./dynamic.js");
      void import(\`./template.js\`);
    `,
    { fileName: "dist/index.js", mode: "runtime" },
  );
  assert.deepEqual(
    references.map(({ specifier }) => specifier),
    [
      "./side-effect.js",
      "./value.js",
      "./other.js",
      "./all.js",
      "./dynamic.js",
      "./template.js",
    ],
  );
});

test("rejects computed runtime imports and malformed syntax", () => {
  assert.throws(
    () =>
      inspectModuleReferences('const name = "./value.js"; import(name);', {
        fileName: "dist/index.js",
        mode: "runtime",
      }),
    /non-literal dynamic import/,
  );
  assert.throws(
    () =>
      inspectModuleReferences("import {", {
        fileName: "dist/index.js",
        mode: "runtime",
      }),
    /malformed module syntax/,
  );
});

test("inspects declaration imports, import types, and reference directives", () => {
  const references = inspectModuleReferences(
    `
      /// <reference path="./ambient.d.ts" />
      /// <reference types="./types.d.ts" />
      import type { Value } from "./value.js";
      export type { Other } from "./other.js";
      export type Dynamic = import /* comment */ ("./dynamic.js").Dynamic;
    `,
    { fileName: "dist/types/index.d.ts", mode: "declaration" },
  );
  assert.deepEqual(
    references.map(({ specifier }) => specifier),
    [
      "./ambient.d.ts",
      "./types.d.ts",
      "./value.js",
      "./other.js",
      "./dynamic.js",
    ],
  );
});
