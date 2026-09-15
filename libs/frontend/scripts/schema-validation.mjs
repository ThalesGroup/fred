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
