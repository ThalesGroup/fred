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

  it("reads the status and detail of a generated-client failure", () => {
    expect(describeError({ status: 409, data: { detail: "An agent named 'x' already exists." } })).toBe(
      "HTTP 409: An agent named 'x' already exists.",
    );
    expect(describeError({ status: 422, data: { detail: [{ msg: "field required" }] } })).toBe(
      'HTTP 422: [{"msg":"field required"}]',
    );
    expect(describeError({ status: "FETCH_ERROR", error: "TypeError: Failed to fetch" })).toBe(
      "HTTP FETCH_ERROR: TypeError: Failed to fetch",
    );
    expect(describeError({ status: 500 })).toBe("HTTP 500");
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
    expect(steps[steps.length - 1]).toMatchObject({ status: "failed", error: "HTTP 409: taken" });
  });
});
