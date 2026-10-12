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

import { describe, expect, it, vi } from "vitest";
import type { PipelineDeps, StepReport } from "../types";
import { parseWebReport, WEB_REPORT_HEADER, WEB_SELF_TEST_AGENT_ID, webResearchScenario } from "./webResearchScenario";

const probe = (id: string, verdict: "passed" | "failed" | "skipped") => ({
  id,
  group: "guard" as const,
  title: id,
  verdict,
  expected: "unsafe_destination",
  observed: verdict === "passed" ? "unsafe_destination" : "ok (1 result(s))",
  detail: null,
});

function answer(body: object): string {
  return `${WEB_REPORT_HEADER} ${JSON.stringify(body)}`;
}

async function run(agentAnswer: string, instance: string | null = "inst-1") {
  const steps: StepReport[] = [];
  const deps = {
    provisionAgentInstance: vi.fn(async () => instance),
    deleteAgentInstance: vi.fn(async () => undefined),
    runAgentTurn: vi.fn(async () => ({ answer: agentAnswer, sources: [], sessionId: null })),
  } as unknown as PipelineDeps;
  await webResearchScenario(
    deps,
    (step) => {
      const index = steps.findIndex((s) => s.id === step.id);
      if (index < 0) steps.push(step);
      else steps[index] = step;
    },
    new AbortController().signal,
  );
  const status = (id: string) => steps.find((s) => s.id === id)?.status;
  return { steps, deps, status };
}

describe("web research self-test", () => {
  it("fails plainly and probes nothing when web research is not enabled", async () => {
    const { steps, status, deps } = await run(
      answer({ enabled: false, ready: false, reason: "Web research is not enabled on this deployment.", probes: [] }),
    );
    expect(status("web-enabled")).toBe("failed");
    expect(steps.find((s) => s.id === "web-enabled")?.error).toContain("not enabled");
    expect(steps.some((s) => s.id.startsWith("web-") && s.id.includes("loopback"))).toBe(false);
    expect(deps.deleteAgentInstance).toHaveBeenCalledWith("inst-1");
  });

  it("fails when the activity store is not ready", async () => {
    const { status } = await run(answer({ enabled: true, ready: false, reason: "not ready", probes: [] }));
    expect(status("web-enabled")).toBe("failed");
  });

  it("reports one step per probe with its own verdict", async () => {
    const { status, steps } = await run(
      answer({
        enabled: true,
        ready: true,
        reason: null,
        probes: [
          probe("loopback_ipv4", "passed"),
          probe("cloud_metadata", "failed"),
          probe("dns_to_loopback", "skipped"),
        ],
      }),
    );
    expect(status("web-enabled")).toBe("passed");
    expect(status("web-loopback_ipv4")).toBe("passed");
    expect(status("web-cloud_metadata")).toBe("failed");
    expect(steps.find((s) => s.id === "web-cloud_metadata")?.error).toContain("expected unsafe_destination");
    expect(status("web-dns_to_loopback")).toBe("skipped");
    expect(status("web-delete-agent")).toBe("passed");
  });

  it("fails the run step when the answer is not a report", async () => {
    const { status } = await run("some unrelated text");
    expect(status("web-run")).toBe("failed");
    expect(status("web-enabled")).toBe("skipped");
  });

  it("skips everything when the harness template is missing", async () => {
    const { status, deps } = await run("", null);
    expect(status("web-provision")).toBe("skipped");
    expect(deps.provisionAgentInstance).toHaveBeenCalledWith(WEB_SELF_TEST_AGENT_ID);
    expect(deps.runAgentTurn).not.toHaveBeenCalled();
  });

  it("parses the report after any leading text and rejects malformed JSON", () => {
    expect(parseWebReport(`noise\n${answer({ enabled: true, ready: true, reason: null, probes: [] })}`)).not.toBeNull();
    expect(parseWebReport(`${WEB_REPORT_HEADER} {broken`)).toBeNull();
  });
});
