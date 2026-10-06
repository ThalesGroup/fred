// @vitest-environment happy-dom
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

// The agents page sort survives leaving and coming back to the page.

import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_AGENT_SORT, getStoredAgentSort, storeAgentSort } from "./agentSort";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("stored agent sort", () => {
  it("defaults to alphabetical when nothing was chosen", () => {
    expect(getStoredAgentSort()).toBe(DEFAULT_AGENT_SORT);
  });

  it("returns the last chosen sort", () => {
    storeAgentSort("created_at:desc");
    expect(getStoredAgentSort()).toBe("created_at:desc");
  });

  it("ignores an unknown stored value", () => {
    localStorage.setItem("fred.agentSort", "size:desc");
    expect(getStoredAgentSort()).toBe(DEFAULT_AGENT_SORT);
  });

  it("falls back to the default when storage is blocked", () => {
    const blocked = () => {
      throw new Error("blocked");
    };
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked });
    expect(() => storeAgentSort("updated_at:desc")).not.toThrow();
    expect(getStoredAgentSort()).toBe(DEFAULT_AGENT_SORT);
  });
});
