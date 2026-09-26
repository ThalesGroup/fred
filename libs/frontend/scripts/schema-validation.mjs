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
import { readFileSync } from "node:fs";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const compiled = new Map();

export function assertDocumentSchema(document, schemaPath, label) {
  let validate = compiled.get(schemaPath);
  if (!validate) {
    validate = ajv.compile(JSON.parse(readFileSync(schemaPath, "utf8")));
    compiled.set(schemaPath, validate);
  }
  assert(
    validate(document),
    `${label} schema invalid: ${ajv.errorsText(validate.errors)}`,
  );
  return document;
}
