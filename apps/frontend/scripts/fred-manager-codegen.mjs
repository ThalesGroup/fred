// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// codegen-openapi 2.2 hardcodes required=true for request-body arguments.
// Correct its one affected manager argument as part of generation, never by hand.
// Fail on contract/generator changes so this workaround cannot silently drift.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";

const schema = JSON.parse(readFileSync(new URL("../../fred-manager/openapi.json", import.meta.url), "utf8"));
const body = schema.paths["/fred-manager/v1/documents/{id}/ingest"].post.requestBody;
assert.equal(body.required, false);
assert.equal(body.content["application/json"].schema.$ref, "#/components/schemas/IngestRequest");
const file = new URL("../src/slices/fredManager/fredManagerOpenApi.ts", import.meta.url);
const source = readFileSync(file, "utf8");
const required = "  ingestRequest: IngestRequest;";
assert.equal(source.split(required).length, 2, "Revisit the optional-body workaround after generator changes");
writeFileSync(file, source.replace(required, "  ingestRequest?: IngestRequest;"));
