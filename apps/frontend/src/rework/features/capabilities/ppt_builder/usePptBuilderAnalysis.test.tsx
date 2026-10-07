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

// The hook polls the analysis while it runs, keeps the last answer through a
// failed poll, re-checks the agent once per finished analysis, and refetches
// after a re-run.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalysisStatusResponse } from "./api/pptBuilderCapabilityOpenApi";

interface QueryState {
  data?: AnalysisStatusResponse;
  isError?: boolean;
  isLoading?: boolean;
}
const analysis = vi.hoisted(() => ({
  state: {} as QueryState,
  options: [] as { skip?: boolean; pollingInterval?: number }[],
  refetch: vi.fn(),
  readinessCheck: vi.fn(),
  rerun: vi.fn(),
}));

vi.mock("./api/pptBuilderCapabilityOpenApi", () => ({
  useGetPptBuilderAnalysisQuery: (_arg: unknown, options: { skip?: boolean; pollingInterval?: number }) => {
    analysis.options.push(options);
    return { ...analysis.state, refetch: analysis.refetch };
  },
  useGetPptBuilderBuiltinQuery: () => ({ data: undefined }),
  useRerunPptBuilderAnalysisMutation: () => [analysis.rerun, { isLoading: false }],
}));
vi.mock("./api/pptBuilderCapabilityApi", () => ({ CAPABILITY_ID: "ppt_builder" }));
vi.mock("../useCapabilityRouted", () => ({ useCapabilityRouted: () => true }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAgentReadinessCheckMutation: () => [analysis.readinessCheck],
}));

import { usePptBuilderAnalysis, type PptBuilderAnalysis } from "./usePptBuilderAnalysis";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const SHA = "abc";
const status = (fields: Partial<AnalysisStatusResponse>): AnalysisStatusResponse => ({
  status: "running",
  template_sha256: SHA,
  labelling_key: "heuristic:1",
  analysis_version: 1,
  current: true,
  updated_at: "t1",
  ...fields,
});

let container: HTMLDivElement;
let root: Root;
let result: PptBuilderAnalysis;

function Harness() {
  result = usePptBuilderAnalysis({
    teamId: "team",
    agentInstanceId: "agent",
    configValues: { template_sha256: SHA },
    onConfigChange: () => {},
    assetFiles: {},
    onAssetFileChange: () => {},
  });
  return null;
}

function show(state: QueryState) {
  analysis.state = state;
  act(() => root.render(<Harness />));
}

const polling = () => analysis.options[analysis.options.length - 1].pollingInterval;

beforeEach(() => {
  analysis.options = [];
  analysis.readinessCheck.mockReset().mockReturnValue(Promise.resolve());
  analysis.refetch.mockReset();
  analysis.rerun.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("usePptBuilderAnalysis", () => {
  it("polls while the analysis runs and stops once it has ended", () => {
    show({ data: status({ status: "pending" }) });
    expect(polling()).toBe(3000);
    show({ data: status({ status: "running" }) });
    expect(polling()).toBe(3000);
    show({ data: status({ status: "succeeded", updated_at: "t2" }) });
    expect(result.phase).toBe("succeeded");
    expect(polling()).toBe(0);
  });

  it("keeps polling, with the last known phase, after a failed poll", () => {
    show({ data: status({ status: "running" }) });
    show({ data: status({ status: "running" }), isError: true });
    expect(result.phase).toBe("running");
    expect(polling()).toBe(3000);
    show({ data: status({ status: "succeeded", updated_at: "t2" }) });
    expect(polling()).toBe(0);
  });

  it("shows the last succeeded analysis rather than nothing after a failed refetch", () => {
    show({ data: status({ status: "succeeded", inventory: { slide_width: 1, slide_height: 1, patterns: [] } }) });
    show({
      data: status({ status: "succeeded", inventory: { slide_width: 1, slide_height: 1, patterns: [] } }),
      isError: true,
    });
    expect(result.phase).toBe("succeeded");
    expect(result.effective).not.toBeNull();
  });

  it("re-checks the agent's readiness once per finished analysis", () => {
    show({ data: status({ status: "running" }) });
    expect(analysis.readinessCheck).not.toHaveBeenCalled();
    show({ data: status({ status: "succeeded", updated_at: "t2" }) });
    show({ data: status({ status: "succeeded", updated_at: "t2" }) });
    expect(analysis.readinessCheck).toHaveBeenCalledTimes(1);
    expect(analysis.readinessCheck).toHaveBeenCalledWith({ teamId: "team", agentInstanceId: "agent" });
    show({ data: status({ status: "failed", updated_at: "t3" }) });
    expect(analysis.readinessCheck).toHaveBeenCalledTimes(2);
  });

  it("refetches the status after a re-run, even a refused one", async () => {
    show({ data: status({ status: "failed" }) });
    expect(result.canRerun).toBe(true);
    analysis.rerun.mockReturnValue({ unwrap: () => Promise.reject(new Error("409")) });
    await act(() => result.rerun());
    expect(analysis.rerun).toHaveBeenCalledWith({ instanceId: "agent" });
    expect(analysis.refetch).toHaveBeenCalledTimes(1);
  });
});
