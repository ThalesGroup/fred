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
import type { AgentCopyResult, ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { duplicateCopyArgs, duplicateWarning } from "./duplicateAgent";

describe("duplicateCopyArgs", () => {
  it("copies into the source team under the chosen name", () => {
    const source = {
      agent_instance_id: "agent-1",
      team_id: "personal-alice",
      display_name: "Analyst",
    } as ManagedAgentInstanceSummary;

    expect(duplicateCopyArgs(source, "personal", "Analyst (copy)")).toEqual({
      teamId: "personal",
      agentInstanceId: "agent-1",
      agentCopyRequest: { target_team_ids: ["personal-alice"], display_name: "Analyst (copy)" },
    });
  });
});

describe("duplicateWarning", () => {
  const t = (key: string, options?: Record<string, unknown>) =>
    options?.capabilities ? `${key}(${String(options.capabilities)})` : key;

  it("is null when the duplicate carries everything", () => {
    expect(duplicateWarning({ team_id: "t", dropped_capabilities: [], notices: [] }, t)).toBeNull();
  });

  it("names the capabilities left out and what to redo", () => {
    const result: AgentCopyResult = {
      team_id: "t",
      dropped_capabilities: [{ id: "web_search", name: "capability.web_search.name" }],
      notices: [{ capability: { id: "ppt_filler", name: "capability.ppt_filler.name" }, message: "Redo X." }],
    };

    expect(duplicateWarning(result, t)).toBe(
      "rework.agentCard.duplicateDropped(capability.web_search.name) · capability.ppt_filler.name : Redo X.",
    );
  });
});
