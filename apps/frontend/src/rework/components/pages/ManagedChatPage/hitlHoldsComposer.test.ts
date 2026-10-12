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
import { hitlHoldsComposer } from "./hitlHoldsComposer";

describe("hitlHoldsComposer", () => {
  const prompt = (stage: string, session_id = "session-1") =>
    ({ session_id, exchange_id: "x", payload: { stage } }) as unknown as Parameters<typeof hitlHoldsComposer>[0];

  it("holds the composer for every pause in the open conversation except an interrupted run", () => {
    for (const stage of ["agent_question", "tool_approval", "graph_choice"]) {
      expect(hitlHoldsComposer(prompt(stage), "session-1")).toBe(true);
    }
    expect(hitlHoldsComposer(prompt("execution_interrupted"), "session-1")).toBe(false);
    expect(hitlHoldsComposer(prompt("tool_approval", "other"), "session-1")).toBe(false);
    expect(hitlHoldsComposer(null, "session-1")).toBe(false);
  });
});
