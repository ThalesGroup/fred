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

import { beforeEach, describe, expect, it } from "vitest";
import {
  clearToolApprovalGrants,
  hasToolApprovalGrants,
  readToolApprovalGrants,
  rememberToolApprovalGrants,
} from "./toolApprovalGrants";

const scope = { userId: "alice", agentInstanceId: "agent-a", sessionId: "session-a" };

beforeEach(() => localStorage.clear());

describe("conversation tool approval grants", () => {
  it("persists only the shown tool names for the same user, agent, and conversation", () => {
    expect(rememberToolApprovalGrants(scope, ["write_file", "delete"])).toBe(true);
    expect(hasToolApprovalGrants(scope, ["write_file"])).toBe(true);
    expect(hasToolApprovalGrants(scope, ["write_file", "delete"])).toBe(true);
    expect(hasToolApprovalGrants(scope, ["write_file", "other"])).toBe(false);
    expect(hasToolApprovalGrants({ ...scope, userId: "bob" }, ["write_file"])).toBe(false);
    expect(hasToolApprovalGrants({ ...scope, agentInstanceId: "agent-b" }, ["write_file"])).toBe(false);
    expect(hasToolApprovalGrants({ ...scope, sessionId: "session-b" }, ["write_file"])).toBe(false);
    expect(hasToolApprovalGrants(scope, [])).toBe(false);
    expect(rememberToolApprovalGrants({ ...scope, userId: null }, ["write_file"])).toBe(false);
  });

  it("ignores corrupted grants and clears only the deleted conversation", () => {
    rememberToolApprovalGrants(scope, ["write_file"]);
    const otherScope = { ...scope, sessionId: "session-b" };
    rememberToolApprovalGrants(otherScope, ["delete"]);
    const key = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index)).find((item) =>
      item?.includes('"session-a"'),
    );
    expect(key).toBeDefined();
    localStorage.setItem(key!, JSON.stringify(["write_file", 42]));
    expect(readToolApprovalGrants(scope)).toEqual([]);
    clearToolApprovalGrants(scope);
    expect(hasToolApprovalGrants(scope, ["write_file"])).toBe(false);
    expect(hasToolApprovalGrants(otherScope, ["delete"])).toBe(true);
  });
});
