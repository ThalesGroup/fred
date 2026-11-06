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
import { describe, expect, it } from "vitest";
import { describeError, runStep } from "./step";
import type { StepReport } from "./types";

describe("describeError", () => {
  it("keeps an Error's message", () => {
    expect(describeError(new Error("boom"))).toBe("boom");
  });

  it("reports the status without copying server payloads or credential data", () => {
    expect(describeError({ status: 409, data: { detail: "private request content" } })).toBe("HTTP 409");
    expect(describeError({ status: "FETCH_ERROR", error: "private upstream address" })).toBe("HTTP FETCH_ERROR");
  });
});

describe("runStep", () => {
  it("reports a generated-client failure readably", async () => {
    const steps: StepReport[] = [];
    await runStep(
      (s) => steps.push(s),
      "id",
      "title",
      async () => {
        throw { status: 409, data: { detail: "taken" } };
      },
    );
    expect(steps[steps.length - 1]).toMatchObject({ status: "failed", error: "HTTP 409" });
  });
});
