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
import { normalizeReasoningEffort, reasoningControl } from "./creationAssistantReasoning";

describe("reasoningControl", () => {
  it("picks levels, switch or unsupported from the model option", () => {
    const option = { profile_id: "p", name: "P" };
    expect(reasoningControl({ ...option, supports_reasoning: true, reasoning_efforts: ["low", "high"] })).toEqual({
      kind: "levels",
      levels: ["low", "high"],
    });
    expect(reasoningControl({ ...option, supports_reasoning: true, reasoning_efforts: [] })).toEqual({
      kind: "switch",
    });
    expect(reasoningControl({ ...option, supports_reasoning: false })).toEqual({ kind: "unsupported" });
    expect(reasoningControl(undefined)).toEqual({ kind: "unknown" });
  });
});

describe("normalizeReasoningEffort", () => {
  const levels = (...l: ("low" | "medium" | "high")[]) => ({ kind: "levels" as const, levels: l });

  it("keeps off and offered levels", () => {
    expect(normalizeReasoningEffort("off", levels("low", "high"))).toBe("off");
    expect(normalizeReasoningEffort("low", levels("low", "high"))).toBe("low");
  });

  it("maps any level to on (medium) for an on/off model", () => {
    expect(normalizeReasoningEffort("high", { kind: "switch" })).toBe("medium");
    expect(normalizeReasoningEffort("off", { kind: "switch" })).toBe("off");
  });

  it("keeps the stored level for an unknown or unsupported model", () => {
    expect(normalizeReasoningEffort("high", { kind: "unknown" })).toBe("high");
    expect(normalizeReasoningEffort("low", { kind: "unsupported" })).toBe("low");
  });

  it("clamps to the nearest offered level, ties going to the stronger one", () => {
    expect(normalizeReasoningEffort("medium", levels("low", "high"))).toBe("high");
    expect(normalizeReasoningEffort("high", levels("low", "medium"))).toBe("medium");
    expect(normalizeReasoningEffort("low", levels("medium", "high"))).toBe("medium");
  });
});
