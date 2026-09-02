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
import reducer, { clearHtmlArtifacts, selectHtmlArtifact, upsertFromPart } from "./htmlArtifactSlice";
import type { HtmlArtifactPartData } from "./types";

const art = (over: Partial<HtmlArtifactPartData> = {}): HtmlArtifactPartData => ({
  type: "html_artifact",
  artifact_id: "a1",
  title: "Page",
  html: "<h1>x</h1>",
  css: "",
  version: "v1",
  ...over,
});

describe("htmlArtifactSlice", () => {
  it("records a snapshot under its session", () => {
    const state = reducer(undefined, upsertFromPart({ sessionId: "s1", art: art() }));
    expect(state.sessionId).toBe("s1");
    expect(state.liveById.a1.title).toBe("Page");
  });

  it("overwrites per artifact_id (latest rendered wins)", () => {
    let state = reducer(undefined, upsertFromPart({ sessionId: "s1", art: art({ version: "v1" }) }));
    state = reducer(state, upsertFromPart({ sessionId: "s1", art: art({ version: "v2", title: "Revised" }) }));
    expect(Object.keys(state.liveById)).toEqual(["a1"]);
    expect(state.liveById.a1.version).toBe("v2");
    expect(state.liveById.a1.title).toBe("Revised");
  });

  it("resets the map when the session changes", () => {
    let state = reducer(undefined, upsertFromPart({ sessionId: "s1", art: art() }));
    state = reducer(state, selectHtmlArtifact("a1"));
    state = reducer(state, upsertFromPart({ sessionId: "s2", art: art({ artifact_id: "b1" }) }));
    expect(state.sessionId).toBe("s2");
    expect(Object.keys(state.liveById)).toEqual(["b1"]);
    // Selection from the previous session is dropped.
    expect(state.selectedId).toBeNull();
  });

  it("clears everything", () => {
    let state = reducer(undefined, upsertFromPart({ sessionId: "s1", art: art() }));
    state = reducer(state, clearHtmlArtifacts());
    expect(state).toEqual({ sessionId: null, liveById: {}, selectedId: null });
  });
});
