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

// Canonical preparation polling and retries must preserve the unsaved form.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalysisStatusResponse, Pattern } from "./api/pptBuilderCapabilityOpenApi";

interface QueryState {
  data?: AnalysisStatusResponse;
  isError?: boolean;
  isLoading?: boolean;
}
const analysis = vi.hoisted(() => ({
  state: {} as QueryState,
  source: "agent" as "agent" | "organization" | "builtin",
  teamId: "team",
  staleData: undefined as AnalysisStatusResponse | undefined,
  retry: vi.fn(),
  savedRefetch: vi.fn(),
  retryState: {
    isLoading: false,
    error: undefined as unknown,
    originalArgs: undefined as { spaceId: string; agentInstanceId: string } | undefined,
  },
  cpState: "ready" as "ready" | "pending" | "failed",
  options: [] as { skip?: boolean; pollingInterval?: number }[],
  refetch: vi.fn(),
  readinessCheck: vi.fn(),
  builtinOptions: [] as { skip?: boolean }[],
  builtin: undefined as unknown,
  configValues: { template_sha256: "abc" } as Record<string, unknown>,
  assetFiles: {} as Record<string, File | undefined>,
  configChange: vi.fn(),
  assetChange: vi.fn(),
  agentInstanceId: "agent",
}));

vi.mock("./api/pptBuilderCapabilityOpenApi", () => ({
  useGetPptBuilderAnalysisQuery: (_arg: unknown, options: { skip?: boolean; pollingInterval?: number }) => {
    analysis.options.push(options);
    return {
      ...analysis.state,
      currentData: analysis.state.data,
      data: analysis.staleData ?? analysis.state.data,
      refetch: analysis.refetch,
    };
  },
  useGetPptBuilderBuiltinQuery: (_arg: unknown, options: { skip?: boolean }) => {
    analysis.builtinOptions.push(options);
    return { data: options.skip ? undefined : analysis.builtin };
  },
}));
vi.mock("./api/pptBuilderCapabilityApi", () => ({ CAPABILITY_ID: "ppt_builder" }));
vi.mock("../useCapabilityRouted", () => ({ useCapabilityRouted: () => true }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useUpdateAgentInstanceMutation: () => [analysis.retry, analysis.retryState],
  useResolvePowerpointTemplateQuery: () => ({
    refetch: analysis.savedRefetch,
    currentData: {
      source: analysis.source,
      file: analysis.configValues.template_sha256 ? { sha256: analysis.configValues.template_sha256 } : null,
      analysis_reference: "prep:reference",
      preparation_state: analysis.cpState,
      preparation_error: analysis.cpState === "failed" ? "No layouts" : null,
    },
  }),
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

const PATTERN: Pattern = {
  id: "slide:1",
  source: "slide",
  source_index: 1,
  name: "Cover",
  label: "Cover",
  kind: "cover",
};

let container: HTMLDivElement;
let root: Root;
let result: PptBuilderAnalysis;

function Harness() {
  result = usePptBuilderAnalysis({
    teamId: analysis.teamId,
    agentInstanceId: analysis.agentInstanceId,
    configValues: analysis.configValues,
    onConfigChange: analysis.configChange,
    assetFiles: analysis.assetFiles,
    onAssetFileChange: analysis.assetChange,
  });
  return null;
}

function show(state: QueryState) {
  analysis.state = state;
  act(() => root.render(<Harness />));
}

const polling = () => analysis.options[analysis.options.length - 1].pollingInterval;

beforeEach(() => {
  analysis.cpState = "ready";
  analysis.source = "agent";
  analysis.teamId = "team";
  analysis.staleData = undefined;
  analysis.retryState = { isLoading: false, error: undefined, originalArgs: undefined };
  analysis.retry.mockReset().mockReturnValue({ unwrap: () => Promise.resolve() });
  analysis.savedRefetch.mockReset().mockResolvedValue({});
  analysis.options = [];
  analysis.builtinOptions = [];
  analysis.builtin = undefined;
  analysis.configValues = { template_sha256: SHA };
  analysis.assetFiles = {};
  analysis.configChange.mockReset();
  analysis.assetChange.mockReset();
  analysis.readinessCheck.mockReset().mockReturnValue({ unwrap: () => Promise.resolve() });
  analysis.agentInstanceId = "agent";
  analysis.refetch.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("usePptBuilderAnalysis", () => {
  it("shows the canonical CP pending or failed state after reload, without an analysis read", () => {
    analysis.cpState = "pending";
    show({});
    expect(result.phase).toBe("pending");
    analysis.cpState = "failed";
    show({});
    expect(result.phase).toBe("failed");
    expect(result.error).toBe("No layouts");
    expect(result.canRerun).toBe(true);
  });
  it("removes a saved template and staged replacement without changing other settings", () => {
    const stagedFile = new File(["deck"], "replacement.pptx");
    analysis.configValues = {
      template_sha256: SHA,
      template_key: `template:${SHA}`,
      overrides: [{ pattern_id: "slide:1", label: "My slide" }],
      use_vision: false,
      validate_plan: true,
    };
    analysis.assetFiles = { template: stagedFile };
    show({});
    expect(result.phase).toBe("staged");

    act(() => result.handleUsePlatformTemplate());
    expect(analysis.assetChange).toHaveBeenCalledWith("template", null);
    expect(analysis.configChange.mock.calls).toEqual([
      ["remove_template", true],
      ["template_sha256", null],
      ["template_key", null],
      ["overrides", []],
    ]);

    analysis.configValues = {
      ...analysis.configValues,
      remove_template: true,
      template_sha256: null,
      template_key: null,
      overrides: [],
    };
    analysis.assetFiles = {};
    show({});
    expect(result.phase).toBe("builtin");
    expect(result.hasPersistedTemplate).toBe(false);
    expect(analysis.configValues.use_vision).toBe(false);
    expect(analysis.configValues.validate_plan).toBe(true);
  });

  it("clears only the selected file while keeping the saved template", () => {
    analysis.assetFiles = { template: new File(["deck"], "replacement.pptx") };
    show({});
    act(() => result.handleClear());
    expect(analysis.assetChange).toHaveBeenCalledWith("template", null);
    expect(analysis.configChange).not.toHaveBeenCalled();
  });

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

  it("keeps finished analysis readable without calling the removed Swift readiness route", () => {
    show({ data: status({ status: "succeeded", updated_at: "t2" }) });
    expect(result.phase).toBe("succeeded");
    expect(analysis.readinessCheck).not.toHaveBeenCalled();
  });

  it("polls an outdated analysis while it is refreshed, then shows the new inventory", () => {
    const inventory = (id: string) => ({ slide_width: 1, slide_height: 1, patterns: [{ ...PATTERN, id }] });
    show({ data: status({ status: "succeeded", current: false, inventory: inventory("old") }) });
    expect(result.canRerun).toBe(true);
    expect(polling()).toBe(0);
    show({ data: status({ status: "succeeded", refreshing: true, inventory: inventory("old") }) });
    expect(result.refreshing).toBe(true);
    expect(result.canRerun).toBe(false);
    expect(result.effective?.patterns?.[0].id).toBe("old");
    expect(polling()).toBe(3000);
    show({ data: status({ status: "succeeded", analysis_version: 2, updated_at: "t2", inventory: inventory("new") }) });
    expect(result.refreshing).toBe(false);
    expect(result.effective?.patterns?.[0].id).toBe("new");
    expect(polling()).toBe(0);
  });

  it("uses the built-in file until CP-owned templates are prepared and activated", () => {
    analysis.configValues = {};
    analysis.builtin = { inventory: { slide_width: 1, slide_height: 1, patterns: [PATTERN] } };
    show({});
    expect(result.phase).toBe("builtin");
    expect(result.previewSource).toEqual({ kind: "builtin" });
    expect(result.effective?.patterns?.[0].label).toBe(PATTERN.label);
    expect(analysis.builtinOptions[analysis.builtinOptions.length - 1].skip).toBe(false);
  });
});

describe("retrying the saved agent template", () => {
  it("sends one empty patch to the saved identity and preserves unsaved config", async () => {
    analysis.cpState = "failed";
    analysis.configValues = {
      template_sha256: SHA,
      validate_plan: false,
      overrides: [{ pattern_id: "slide:1", label: "Draft" }],
    };
    let complete!: () => void;
    analysis.retry.mockReturnValue({
      unwrap: () =>
        new Promise<void>((resolve) => {
          complete = resolve;
        }),
    });
    show({});
    let request!: Promise<void>;
    act(() => {
      request = result.retry!();
      void result.retry!();
    });
    expect(analysis.retry).toHaveBeenCalledExactlyOnceWith({
      spaceId: "team",
      agentInstanceId: "agent",
      updateAgentInstanceRequest: {},
    });
    expect(analysis.configChange).not.toHaveBeenCalled();
    expect(analysis.assetChange).not.toHaveBeenCalled();
    await act(async () => {
      complete();
      await request;
    });
    expect(analysis.savedRefetch).toHaveBeenCalledOnce();
    analysis.cpState = "pending";
    show({});
    expect(result.phase).toBe("pending");
    expect(result.retry).toBeNull();
    expect(analysis.configValues.overrides).toEqual([{ pattern_id: "slide:1", label: "Draft" }]);
  });

  it("never retries a common template, staged replacement, removal or unfailed CP state", () => {
    analysis.cpState = "failed";
    analysis.source = "organization";
    show({});
    expect(result.retry).toBeNull();
    analysis.source = "agent";
    analysis.assetFiles = { template: new File(["deck"], "draft.pptx") };
    show({});
    expect(result.retry).toBeNull();
    analysis.assetFiles = {};
    analysis.configValues.remove_template = true;
    show({});
    expect(result.retry).toBeNull();
    analysis.configValues.remove_template = false;
    analysis.cpState = "ready";
    show({ data: status({ status: "interrupted" }) });
    expect(result.retry).toBeNull();
    analysis.cpState = "failed";
    analysis.agentInstanceId = "";
    show({});
    expect(result.retry).toBeNull();
    expect(analysis.retry).not.toHaveBeenCalled();
  });

  it("keeps a refused retry visible without changing the draft or using another agent's error", async () => {
    analysis.cpState = "failed";
    analysis.retry.mockReturnValue({ unwrap: () => Promise.reject({ status: 403 }) });
    show({});
    await act(async () => {
      await result.retry!();
    });
    analysis.retryState.error = { status: 403 };
    analysis.retryState.originalArgs = { spaceId: "team", agentInstanceId: "agent" };
    show({});
    expect(result.retryFailed).toBe(true);
    expect(result.retry).not.toBeNull();
    expect(analysis.configChange).not.toHaveBeenCalled();
    analysis.agentInstanceId = "other-agent";
    show({});
    expect(result.retryFailed).toBe(false);
    await act(async () => {
      await result.retry!();
    });
    expect(analysis.retry).toHaveBeenLastCalledWith({
      spaceId: "team",
      agentInstanceId: "other-agent",
      updateAgentInstanceRequest: {},
    });
  });

  it("does not reuse a previous agent's pod analysis while the new query loads", () => {
    analysis.staleData = status({
      status: "succeeded",
      inventory: { slide_width: 1, slide_height: 1, patterns: [PATTERN] },
    });
    show({ isLoading: true });
    expect(result.phase).toBe("unknown");
    expect(result.effective).toBeNull();
    expect(result.previewSource).toBeNull();
  });
});
