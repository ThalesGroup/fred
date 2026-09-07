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
import type { ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { sortAgents } from "./agentSort";

// --- helpers ---------------------------------------------------------------

function agent(overrides: Partial<ManagedAgentInstanceSummary>): ManagedAgentInstanceSummary {
  return {
    agent_instance_id: "a-1",
    template_id: "tpl-1",
    display_name: "Agent",
    role: "Role",
    description: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as ManagedAgentInstanceSummary;
}

function ids(instances: ManagedAgentInstanceSummary[]): string[] {
  return instances.map((i) => i.agent_instance_id);
}

// --- tests -----------------------------------------------------------------

describe("sortAgents", () => {
  it("never mutates the caller's array", () => {
    // The list is RTK Query state, frozen by immer in dev — an in-place sort
    // would throw at runtime rather than fail a type check.
    const input = Object.freeze([
      agent({ agent_instance_id: "b", display_name: "Beta" }),
      agent({ agent_instance_id: "a", display_name: "Alpha" }),
    ]) as ManagedAgentInstanceSummary[];

    expect(ids(sortAgents(input, "name"))).toEqual(["a", "b"]);
    expect(ids(input)).toEqual(["b", "a"]);
  });

  describe("name", () => {
    it("orders alphabetically, ignoring case", () => {
      const list = [
        agent({ agent_instance_id: "c", display_name: "charlie" }),
        agent({ agent_instance_id: "a", display_name: "Alpha" }),
        agent({ agent_instance_id: "b", display_name: "Bravo" }),
      ];
      expect(ids(sortAgents(list, "name"))).toEqual(["a", "b", "c"]);
    });

    it("files an accented name next to its unaccented form", () => {
      // Base sensitivity: "Élan" belongs beside "Elan", not after "Zulu".
      const list = [
        agent({ agent_instance_id: "z", display_name: "Zulu" }),
        agent({ agent_instance_id: "e", display_name: "Élan" }),
        agent({ agent_instance_id: "f", display_name: "Fox" }),
      ];
      expect(ids(sortAgents(list, "name"))).toEqual(["e", "f", "z"]);
    });
  });

  describe("created_at:desc", () => {
    it("puts the most recently created first", () => {
      const list = [
        agent({ agent_instance_id: "old", created_at: "2026-01-01T00:00:00Z" }),
        agent({ agent_instance_id: "new", created_at: "2026-06-01T00:00:00Z" }),
      ];
      expect(ids(sortAgents(list, "created_at:desc"))).toEqual(["new", "old"]);
    });

    it("pushes an undated agent to the end", () => {
      // `created_at` is nullable on the payload.
      const list = [
        agent({ agent_instance_id: "none", created_at: null }),
        agent({ agent_instance_id: "dated", created_at: "2026-01-01T00:00:00Z" }),
      ];
      expect(ids(sortAgents(list, "created_at:desc"))).toEqual(["dated", "none"]);
    });

    it("pushes an unparseable date to the end rather than to the front", () => {
      const list = [
        agent({ agent_instance_id: "junk", created_at: "not-a-date" }),
        agent({ agent_instance_id: "dated", created_at: "2026-01-01T00:00:00Z" }),
      ];
      expect(ids(sortAgents(list, "created_at:desc"))).toEqual(["dated", "junk"]);
    });

    it("leaves two undated agents in their incoming order", () => {
      const list = [
        agent({ agent_instance_id: "first", created_at: null }),
        agent({ agent_instance_id: "second", created_at: null }),
      ];
      expect(ids(sortAgents(list, "created_at:desc"))).toEqual(["first", "second"]);
    });
  });

  describe("updated_at:desc", () => {
    it("sorts on updated_at, not created_at", () => {
      // An old agent edited yesterday must outrank a new one never touched.
      const list = [
        agent({ agent_instance_id: "fresh", created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z" }),
        agent({ agent_instance_id: "revised", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z" }),
      ];
      expect(ids(sortAgents(list, "updated_at:desc"))).toEqual(["revised", "fresh"]);
    });
  });
});
