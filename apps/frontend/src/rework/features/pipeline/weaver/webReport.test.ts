// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { expect, it } from "vitest";
import { verifyWebProbes } from "./webReport";
import { reportProbes, type WebProbe } from "../scenarios/webResearchScenario";
import type { StepReport } from "../types";

it("refuses empty, incomplete, malformed and duplicated reports", () => {
  const probe: WebProbe = {
    id: "fetch_public",
    group: "fetch",
    verdict: "passed",
    title: "Read",
    expected: "ok",
    observed: "ok",
  };
  expect(() => verifyWebProbes([])).toThrow("incomplete");
  expect(() => verifyWebProbes([probe])).toThrow("incomplete");
  expect(() => verifyWebProbes([probe, probe])).toThrow("duplicate");
  expect(() => verifyWebProbes([{ ...probe, verdict: "running" } as unknown as WebProbe])).toThrow("malformed");
});
it("states what focused reads and HTTP-error skips actually demonstrate", () => {
  const steps: StepReport[] = [];
  reportProbes(
    (step) => steps.push(step),
    [
      {
        id: "fetch_focus",
        group: "fetch",
        title: "matching passages",
        verdict: "passed",
        expected: "nonempty",
        observed: "nonempty",
      },
      {
        id: "redirect_to_loopback",
        group: "remote",
        title: "Redirect refused",
        verdict: "skipped",
        expected: "unsafe_destination",
        observed: "http_error",
        detail: "unreachable",
      },
    ],
  );
  expect(steps[0].title).toContain("non-empty content");
  expect(steps[0].title).not.toContain("matching");
  expect(steps[1].status).toBe("skipped");
  expect(steps[1].detail).toContain("not demonstrated");
  expect(steps[1].detail).not.toContain("unreachable");
});
