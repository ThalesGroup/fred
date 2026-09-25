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

import { describe, expect, it } from "vitest";

import { findPathToNode, parseMindMapPayload } from "./mindmapParser";

describe("parseMindMapPayload", () => {
  it("parses a valid mindmap payload", () => {
    const parsed = parseMindMapPayload(`{
      "title": "Transcript",
      "root": {
        "id": "root",
        "name": "Overview",
        "children": [{ "id": "topic-1", "name": "Theme A", "children": [] }]
      }
    }`);

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.payload.root.name).toBe("Overview");
    expect(parsed.nodeCount).toBe(2);
  });

  it("returns a friendly error for invalid JSON", () => {
    const parsed = parseMindMapPayload("{ not-json }");
    expect(parsed.ok).toBe(false);
    if (parsed.ok !== false) return;
    expect(parsed.error.length).toBeGreaterThan(0);
  });

  it("rejects payloads without a valid root name", () => {
    const parsed = parseMindMapPayload(`{
      "title": "Transcript",
      "root": { "id": "root", "children": [] }
    }`);

    expect(parsed.ok).toBe(false);
    if (parsed.ok !== false) return;
    expect(parsed.error).toContain("root node");
  });

  it("finds a breadcrumb path to a child node", () => {
    const parsed = parseMindMapPayload(`{
      "title": "Transcript",
      "root": {
        "id": "root",
        "name": "Overview",
        "children": [{
          "id": "topic-1",
          "name": "Theme A",
          "children": [{ "id": "topic-1a", "name": "Detail", "children": [] }]
        }]
      }
    }`);

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    const path = findPathToNode(parsed.payload.root, "topic-1a");
    expect(path?.map((node) => node.id)).toEqual(["root", "topic-1", "topic-1a"]);
  });

  it("preserves presentation.initialDepth and layout when provided", () => {
    const parsed = parseMindMapPayload(`{
      "title": "Transcript",
      "root": {
        "id": "root",
        "name": "Overview",
        "children": []
      },
      "presentation": {
        "initialDepth": 2,
        "layout": "radial",
        "focusMode": true
      }
    }`);

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.payload.presentation?.initialDepth).toBe(2);
    expect(parsed.payload.presentation?.layout).toBe("radial");
    expect(parsed.payload.presentation?.focusMode).toBe(true);
  });
});
