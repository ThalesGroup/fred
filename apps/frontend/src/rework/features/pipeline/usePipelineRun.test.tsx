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
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePipelineRun } from "./usePipelineRun";
import type { PipelineRun } from "./usePipelineRun";
import type { Scenario } from "./types";
import type { CapturedCredential } from "./sessionCredential";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  templates: vi.fn(),
  instances: vi.fn(),
  remove: vi.fn(),
  enroll: vi.fn(),
  stream: vi.fn(),
  prepare: vi.fn(),
}));
vi.mock("./actions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./actions")>()),
  streamAgentTurn: h.stream,
}));
vi.mock("../../../security/KeycloakService", () => ({ KeyCloakService: { GetUserId: () => "synthetic-user" } }));
vi.mock("../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  ...Object.fromEntries(
    [
      "useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation",
      "useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation",
      "usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation",
      "usePrepareAgentExecutionMutation",
      "usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation",
      "usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation",
    ].map((name) => [name, () => [vi.fn()]]),
  ),
  useLazyGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery: () => [h.templates],
  useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery: () => [h.instances],
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation: () => [h.remove],
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation: () => [h.enroll],
  usePrepareAgentExecutionMutation: () => [h.prepare],
}));
vi.mock("../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () =>
  Object.fromEntries(
    ["useCreateTagMutation", "useDeleteTagMutation", "useLazyListTagsQuery"].map((name) => [name, () => [vi.fn()]]),
  ),
);
afterEach(() => vi.clearAllMocks());

function mount(scenario: Scenario) {
  let run!: PipelineRun;
  function Probe() {
    run = usePipelineRun(scenario);
    return null;
  }
  const root = createRoot(document.createElement("div"));
  act(() => {
    root.render(<Probe />);
  });
  return { root, start: () => run.start() };
}

describe("turn arguments", () => {
  it("forwards both progress and status callbacks to the stream", async () => {
    h.prepare.mockReturnValue({ unwrap: async () => ({}) });
    h.stream.mockResolvedValue({ answer: "", sources: [], sessionId: null, statusSeenAt: {} });
    const onProgress = vi.fn();
    const onStatus = vi.fn();
    const view = mount(async (deps) => {
      await deps.runAgentTurn({
        agentInstanceId: "instance",
        question: "q",
        libraryIds: [],
        bearer: "synthetic-bearer" as CapturedCredential,
        onProgress,
        onStatus,
      });
    });
    try {
      await act(async () => {
        view.start();
      });
      expect(h.stream).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ bearer: "synthetic-bearer", onProgress, onStatus }),
      );
    } finally {
      act(() => view.root.unmount());
    }
  });
});

describe("diagnostic enrollment", () => {
  it("preserves existing instances when enrolling a new run", async () => {
    h.templates.mockReturnValue({
      unwrap: async () => [{ source_agent_id: "source", template_id: "template", status: "available" }],
    });
    h.remove.mockReturnValue({ unwrap: async () => undefined });
    h.enroll.mockReturnValue({ unwrap: async () => ({ agent_instance_id: "created" }) });
    let created: string | null = null;
    const view = mount(async (deps, _report, signal) => {
      created = await deps.provisionAgentInstance("source", {}, signal);
    });
    try {
      await act(async () => {
        view.start();
      });
      expect(created).toBe("created");
      expect(h.instances).not.toHaveBeenCalled();
      expect(h.remove).not.toHaveBeenCalled();
    } finally {
      act(() => view.root.unmount());
    }
  });

  it("starts no enrollment after cancellation during template lookup", async () => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    h.templates.mockReturnValue({
      unwrap: async () => {
        await pending;
        return [{ source_agent_id: "source", template_id: "template", status: "available" }];
      },
    });
    let finished!: () => void;
    const done = new Promise<void>((resolve) => {
      finished = resolve;
    });
    let failure: unknown;
    const view = mount(async (deps, _report, signal) => {
      try {
        await deps.provisionAgentInstance("source", {}, signal);
      } catch (error) {
        failure = error;
      } finally {
        finished();
      }
    });
    await act(async () => {
      view.start();
    });
    act(() => view.root.unmount());
    release();
    await done;
    expect(failure).toMatchObject({ name: "AbortError" });
    expect(h.remove).not.toHaveBeenCalled();
    expect(h.enroll).not.toHaveBeenCalled();
  });
});
