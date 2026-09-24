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
