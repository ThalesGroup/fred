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
});
