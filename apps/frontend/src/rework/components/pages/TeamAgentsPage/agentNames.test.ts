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
import type { ManagedAgentInstanceSummary } from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { freeAgentName, isAgentNameConflict, isAgentNameTaken, takenAgentNames } from "./agentNames";

const agent = (id: string, name: string) =>
  ({ agent_instance_id: id, display_name: name }) as ManagedAgentInstanceSummary;

describe("agent names", () => {
  it("compares names without case or surrounding spaces, excluding the edited agent", () => {
    const taken = takenAgentNames([agent("a", "Analyst"), agent("b", " Writer ")], "b");

    expect(isAgentNameTaken("  ANALYST ", taken)).toBe(true);
    expect(isAgentNameTaken("Writer", taken)).toBe(false);
    expect(isAgentNameTaken("   ", taken)).toBe(false);
  });

  it("starts a duplicate on the first free copy name, numbered from 1", () => {
    const taken = takenAgentNames([agent("a", "Analyst"), agent("b", "analyst (copie 1)")]);

    expect(freeAgentName("Analyst", taken, "copie")).toBe("Analyst (copie 2)");
    expect(freeAgentName("Report", takenAgentNames([agent("c", "Report")]), "copy")).toBe("Report (copy 1)");
    expect(freeAgentName("Writer", taken, "copie")).toBe("Writer");
  });

  it("recognises the server's name conflict and nothing else", () => {
    expect(isAgentNameConflict({ data: { detail: { code: "agent_name_conflict", message: "x" } } })).toBe(true);
    expect(isAgentNameConflict({ data: { detail: "Agent name taken" } })).toBe(false);
    expect(isAgentNameConflict(new Error("boom"))).toBe(false);
  });
});
