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
import { filterAgents } from "./agentFilter";

// --- helpers ---------------------------------------------------------------

function agent(overrides: Partial<ManagedAgentInstanceSummary>): ManagedAgentInstanceSummary {
  return {
    agent_instance_id: "a-1",
    template_id: "tpl-1",
    display_name: "Support Assistant",
    role: "Customer support",
    description: "Answers customer questions",
    ...overrides,
  } as ManagedAgentInstanceSummary;
}

const SUPPORT = agent({ agent_instance_id: "a-1" });
const INVOICES = agent({
  agent_instance_id: "a-2",
  display_name: "Invoice Reader",
  description: "Extracts totals from PDFs",
});

function ids(instances: ManagedAgentInstanceSummary[]): string[] {
  return instances.map((i) => i.agent_instance_id);
}

// --- tests -----------------------------------------------------------------

describe("filterAgents", () => {
  it("returns everything for an empty or whitespace-only query", () => {
    // The page passes the raw input value, so a user who typed only spaces
    // must not be shown an empty list.
    expect(ids(filterAgents([SUPPORT, INVOICES], ""))).toEqual(["a-1", "a-2"]);
    expect(ids(filterAgents([SUPPORT, INVOICES], "   "))).toEqual(["a-1", "a-2"]);
  });

  it("matches the display name, case-insensitively", () => {
    expect(ids(filterAgents([SUPPORT, INVOICES], "INVOICE"))).toEqual(["a-2"]);
  });

  it("matches the role, which the card renders under the name", () => {
    const payroll = agent({ agent_instance_id: "a-5", role: "Answers payroll questions" });
    expect(ids(filterAgents([SUPPORT, payroll], "payroll"))).toEqual(["a-5"]);
  });

  it("matches the description too", () => {
    expect(ids(filterAgents([SUPPORT, INVOICES], "totals"))).toEqual(["a-2"]);
  });

  it("matches on a substring, not just a prefix", () => {
    expect(ids(filterAgents([SUPPORT, INVOICES], "sist"))).toEqual(["a-1"]);
  });

  it("ignores surrounding whitespace in the query", () => {
    expect(ids(filterAgents([SUPPORT, INVOICES], "  invoice  "))).toEqual(["a-2"]);
  });

  it("returns an empty list when nothing matches", () => {
    // Drives the page's dedicated no-match state rather than the
    // "create your first agent" empty state.
    expect(filterAgents([SUPPORT, INVOICES], "zzz")).toEqual([]);
  });

  it("preserves the incoming order", () => {
    expect(ids(filterAgents([INVOICES, SUPPORT], "e"))).toEqual(["a-2", "a-1"]);
  });

  it("tolerates a missing description", () => {
    // `description` is optional on the payload; a null must not throw or
    // stringify into something matchable.
    const bare = agent({ agent_instance_id: "a-3", display_name: "Bare", description: null });
    expect(ids(filterAgents([bare], "bare"))).toEqual(["a-3"]);
    expect(filterAgents([bare], "null")).toEqual([]);
  });

  it("does not let a query span the name/description boundary", () => {
    // Name and description are joined to build the haystack; the join must not
    // create matches that exist in neither field.
    const a = agent({ agent_instance_id: "a-4", display_name: "alpha", description: "beta" });
    expect(filterAgents([a], "alphabeta")).toEqual([]);
  });
});
