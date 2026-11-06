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
import { buildCombinedReport, buildReport } from "./report";

const passed = { id: "a", title: "First", status: "passed" as const, detail: "ok", durationMs: 4 };
const failed = { id: "b", title: "Second", status: "failed" as const, error: "boom" };

describe("report", () => {
  it("formats one run with counts and each step", () => {
    expect(buildReport([passed, failed])).toBe(
      [
        "Self-test: 1 passed, 1 failed, 0 skipped, 2 steps",
        "",
        "1. [PASSED] First — ok (4 ms)",
        "2. [FAILED] Second — ERROR: boom",
      ].join("\n"),
    );
  });

  it("combines only the families that ran, dated and tied to the origin", () => {
    const text = buildCombinedReport(
      [
        { title: "Platform", steps: [passed] },
        { title: "Teams", steps: [] },
        { title: "Agents", steps: [failed] },
      ],
      "https://platform.example",
      new Date("2026-10-20T10:00:00Z"),
    );
    expect(text.split("\n")[0]).toBe("Self-test report — https://platform.example — 2026-10-20T10:00:00.000Z");
    expect(text).toContain("Total: 1 passed, 1 failed, 0 skipped, 2 steps");
    expect(text).toContain("## Platform: 1 passed");
    expect(text).toContain("## Agents: 0 passed, 1 failed");
    expect(text).not.toContain("Teams");
  });
});
