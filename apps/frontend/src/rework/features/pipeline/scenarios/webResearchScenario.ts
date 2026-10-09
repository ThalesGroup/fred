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

import { runStep, SkipStep } from "../step";
import type { Reporter, Scenario, StepStatus } from "../types";

export const WEB_SELF_TEST_AGENT_ID = "fred.github.self_test_web";
/** The fixed header the harness agent puts before its JSON report. */
export const WEB_REPORT_HEADER = "WEB-SELF-TEST";

export interface WebProbe {
  id: string;
  group: "schema" | "guard" | "remote" | "search" | "fetch";
  title: string;
  verdict: "passed" | "failed" | "skipped";
  expected: string;
  observed: string;
  detail?: string | null;
}

export interface WebReport {
  enabled: boolean;
  ready: boolean;
  reason: string | null;
  probes: WebProbe[];
}

const GROUP_LABEL: Record<WebProbe["group"], string> = {
  schema: "Refused by the tool contract",
  guard: "Refused before any connection",
  remote: "Refused on the Internet",
  search: "Search",
  fetch: "Page read",
};

/** Read the harness answer; null when it is not a web self-test report. */
export function parseWebReport(answer: string): WebReport | null {
  const start = answer.indexOf(`${WEB_REPORT_HEADER} `);
  if (start < 0) return null;
  try {
    const report = JSON.parse(answer.slice(start + WEB_REPORT_HEADER.length + 1)) as WebReport;
    return Array.isArray(report.probes) && typeof report.enabled === "boolean" ? report : null;
  } catch {
    return null;
  }
}

/** One step per probe, so the panel shows exactly which protection held. */
export function reportProbes(report: Reporter, probes: WebProbe[]): void {
  for (const probe of probes) {
    const status: StepStatus = probe.verdict;
    const observed = `observed ${probe.observed}, expected ${probe.expected}`;
    const text = probe.detail ? `${observed} — ${probe.detail}` : observed;
    report({
      id: `web-${probe.id}`,
      title: `${GROUP_LABEL[probe.group] ?? probe.group}: ${probe.title}`,
      status,
      ...(status === "failed" ? { error: text } : { detail: text }),
    });
  }
}

/**
 * The web research self-test: a no-LLM harness agent runs a fixed battery of
 * probes through the governed web research port — refused URLs, internal and
 * encoded destinations, redirects, content limits, SafeSearch policy, and a
 * working search and page read. It fails first, and probes nothing, when web
 * research is not enabled on the deployment.
 */
export const webResearchScenario: Scenario = async (deps, report) => {
  let agentInstanceId: string | null = null;
  try {
    agentInstanceId = await runStep(report, "web-provision", "Provision the web research self-test agent", async () => {
      const id = await deps.provisionAgentInstance(WEB_SELF_TEST_AGENT_ID);
      if (!id)
        throw new SkipStep(
          `template '${WEB_SELF_TEST_AGENT_ID}' not found — restart the fred-agents pod with the new code`,
        );
      return { value: id, detail: id };
    });

    const webReport = await runStep(report, "web-run", "Run the probe battery", async () => {
      if (!agentInstanceId) throw new SkipStep("agent instance missing");
      const turn = await deps.runAgentTurn({
        agentInstanceId,
        question: "Run the web research self-test.",
        libraryIds: [],
      });
      const parsed = parseWebReport(turn.answer);
      if (!parsed) throw new Error(`the agent did not return a web self-test report (${turn.answer.slice(0, 80)}…)`);
      return { value: parsed, detail: `${parsed.probes.length} probe(s)` };
    });

    await runStep(report, "web-enabled", "Web research is enabled on this deployment", async () => {
      if (!webReport) throw new SkipStep("no report");
      if (!webReport.enabled) throw new Error(webReport.reason ?? "web research is not enabled");
      if (!webReport.ready) throw new Error(webReport.reason ?? "web research is not ready");
      return { value: undefined, detail: "capability enabled, activity store ready" };
    });

    if (webReport?.enabled && webReport.ready) reportProbes(report, webReport.probes);
  } finally {
    await runStep(
      report,
      "web-delete-agent",
      "Delete the web research self-test agent instance",
      async () => {
        if (!agentInstanceId) throw new SkipStep("no instance was provisioned");
        await deps.deleteAgentInstance(agentInstanceId);
        return { value: undefined, detail: `deleted ${agentInstanceId}` };
      },
      { optional: true },
    );
  }
};
