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

import { describe, it, expect } from "vitest";
import { parseSseBlock, taskEventsBasePath } from "./useTaskSseManager";

// ── taskEventsBasePath ──────────────────────────────────────────────────────────

describe("taskEventsBasePath", () => {
  it("routes migration tasks to the control-plane backend", () => {
    expect(taskEventsBasePath("migration")).toBe("/control-plane/v1");
  });

  it("routes ingestion tasks to the knowledge-flow backend", () => {
    expect(taskEventsBasePath("ingestion")).toBe("/knowledge-flow/v1");
  });

  it("falls back to knowledge-flow for an unknown kind", () => {
    expect(taskEventsBasePath("reindex")).toBe("/knowledge-flow/v1");
  });

  it("falls back to knowledge-flow when kind is null", () => {
    expect(taskEventsBasePath(null)).toBe("/knowledge-flow/v1");
  });
});

// ── parseSseBlock ───────────────────────────────────────────────────────────────

const eventJson = (overrides: Record<string, unknown> = {}) =>
  JSON.stringify({ task_id: "t1", kind: "ingestion", state: "running", seq: 3, ...overrides });

describe("parseSseBlock", () => {
  it("ignores heartbeat comment blocks", () => {
    expect(parseSseBlock(": keep-alive")).toEqual({});
  });

  it("parses a block with both id and data", () => {
    const result = parseSseBlock(`id: 7\ndata: ${eventJson()}`);
    expect(result.id).toBe("7");
    expect(result.event).toMatchObject({ task_id: "t1", state: "running", seq: 3 });
  });

  it("parses data even when no id line is present", () => {
    const result = parseSseBlock(`data: ${eventJson()}`);
    expect(result.id).toBeUndefined();
    expect(result.event).toMatchObject({ task_id: "t1" });
  });

  it("returns the id but no event for an id-only frame", () => {
    expect(parseSseBlock("id: 12")).toEqual({ id: "12" });
  });

  it("returns the id but no event when the data is unparseable JSON", () => {
    const result = parseSseBlock("id: 5\ndata: {not json");
    expect(result.id).toBe("5");
    expect(result.event).toBeUndefined();
  });

  it("returns the id but no event for an empty data line", () => {
    expect(parseSseBlock("id: 9\ndata: ")).toEqual({ id: "9" });
  });

  it("is order-independent for id and data lines", () => {
    const result = parseSseBlock(`data: ${eventJson({ seq: 4 })}\nid: 8`);
    expect(result.id).toBe("8");
    expect(result.event).toMatchObject({ seq: 4 });
  });

  it("decodes terminal-state events so the caller can stop streaming", () => {
    const result = parseSseBlock(`id: 99\ndata: ${eventJson({ state: "succeeded", seq: 10 })}`);
    expect(result.event?.state).toBe("succeeded");
  });
});
