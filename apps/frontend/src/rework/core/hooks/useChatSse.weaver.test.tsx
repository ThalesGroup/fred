// @vitest-environment happy-dom
// Copyright Thales 2026
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { prepare, onError, onTurnStarted } = vi.hoisted(() => ({
  prepare: vi.fn(),
  onError: vi.fn(),
  onTurnStarted: vi.fn(),
}));
vi.mock("../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  usePrepareExecutionMutation: () => [prepare],
}));
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: vi.fn(async () => true),
    GetTokenSecondsLeft: () => 3600,
    GetToken: () => "test-token",
    GetUserId: () => "user-1",
    GetSessionIdentity: () => "user-1-session",
  },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "fr-FR", t: (key: string) => key } }),
}));
vi.mock("../../../common/platformAccess", () => ({ handlePlatformAccessResponse: vi.fn() }));

import { useChatSse, type RuntimeAwaitingHumanEvent } from "./useChatSse";
import type { ExecutionPreparation } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { fullReasoning } from "../../components/shared/molecules/FullReasoningPanel/fullReasoning";
import { groupTraceEntries } from "../../utils/traceUtils";

const spaceId = "f0137825-89b0-4d36-bdc3-b007a9777122";
const preparation: ExecutionPreparation = {
  capability_base_urls: {},
  agent_configuration_revision: 1,
  space_id: spaceId,
  agent_instance_id: "agent-1",
  execute_stream_url: "/runtime/agents/execute/stream",
  execute_url: "/runtime/agents/execute",
  execution_transport: "sse",
  max_chat_input_chars: null,
  messages_url_template: "/runtime/agents/sessions/{session_id}/messages",
  runtime_id: "fred-agents",
  // Exercise the resume contract only; Weaver preparation currently returns false.
  supports_hitl: true,
  supports_ui_parts: false,
  model_choice: null,
  model_error: null,
  inference: {
    key: { source_id: "source", upstream_model_id: "model" },
    source: "default",
    options: {},
    source_revision: 1,
    snapshot_revision: 1,
    policy_revision: 1,
  },
  models: {
    default: null,
    fallback: null,
    legacy_profile_id: null,
    offers: [],
    options: {},
    recommendation: null,
    requires_reselection: false,
  },
  supports_streaming: true,
  chat_controls: [],
};
const pending: RuntimeAwaitingHumanEvent = {
  type: "awaiting_human",
  session_id: "saved-session",
  exchange_id: "exchange-1",
  payload: { interrupt_id: "interrupt-1", occurrence_id: "occurrence-1" },
};
let latest: ReturnType<typeof useChatSse>;
function Host() {
  latest = useChatSse({ agentInstanceId: "agent-1", teamId: "team-1", spaceId, onError, onTurnStarted });
  return null;
}

describe("Weaver execution context and HTTP diagnostics", () => {
  let root: Root;
  let container: HTMLDivElement;
  beforeEach(async () => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    prepare.mockReset();
    prepare.mockImplementation(() => ({ unwrap: async () => preparation }));
    onError.mockClear();
    onTurnStarted.mockClear();
    vi.spyOn(console, "error").mockImplementation(() => {});
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => root.render(<Host />));
  });
  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each([false, true])(
    "renders Ralph's SSE response and shared traces=%s without a history route",
    async (traces) => {
      const ralph: ExecutionPreparation = {
        ...preparation,
        runtime_id: "control-plane",
        execute_stream_url: "/control-plane/v1/agents/execute/stream",
        execute_url: null,
        messages_url_template: null,
        supports_hitl: false,
      };
      prepare.mockImplementation(() => ({ unwrap: async () => ralph }));
      const frames = [
        { kind: "status", sequence: 1, status: "running" },
        ...(traces
          ? [
              { kind: "thought_start", thought_id: "model-1", phase: "planning", source: "model_native" },
              { kind: "thought_delta", thought_id: "model-1", delta: "Provider explanation" },
              { kind: "thought_end", thought_id: "model-1" },
              { kind: "tool_call", tool_name: "search_documents", call_id: "search-1", arguments: { query: "manual" } },
              {
                kind: "tool_result",
                tool_name: "search_documents",
                call_id: "search-1",
                content: "[]",
                is_error: false,
                latency_ms: 12,
              },
            ]
          : []),
        { kind: "assistant_delta", delta: "Bonjour" },
        { kind: "final", content: "Bonjour", finish_reason: "stop" },
      ].map((event, index) => ({ ...event, sequence: index + 1 }));
      const fetchMock = vi.fn(
        async () =>
          new Response(frames.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""), {
            headers: { "content-type": "text/event-stream" },
          }),
      );
      vi.stubGlobal("fetch", fetchMock);
      await act(async () => {
        expect(await latest.send("bonjour", "saved-session")).toBe(true);
      });
      expect(String(vi.mocked(globalThis.fetch).mock.calls[0][0])).toContain(ralph.execute_stream_url);
      expect(latest.waitResponse).toBe(false);
      expect(
        latest.messages.some(
          (message) =>
            message.role === "assistant" &&
            message.parts.some((part) => part.type === "text" && part.text === "Bonjour"),
        ),
      ).toBe(true);
      expect(fullReasoning(latest.messages)).toHaveLength(traces ? 1 : 0);
      expect(groupTraceEntries(latest.messages).filter((entry) => entry.kind === "combo")).toHaveLength(traces ? 1 : 0);
      if (traces) {
        expect(latest.messages.find((message) => message.channel === "tool_result")?.parts).toContainEqual({
          type: "tool_result",
          call_id: "search-1",
          ok: true,
          content: "[]",
          latency_ms: 12,
        });
      }
      expect(onError).not.toHaveBeenCalled();
    },
  );

  it.each(["first", "reopened", "hitl"])("sends canonical space without team on %s turn", async (turn) => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: "Refused" }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    await act(async () => {
      if (turn === "hitl") await latest.sendHitlResume(pending, "yes");
      else await latest.send("bonjour", turn === "first" ? null : "saved-session");
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[0][1]?.body));
    expect(body.runtime_context).toMatchObject({ space_id: spaceId, language: "fr" });
    expect(body.runtime_context.team_id).toBeUndefined();
    if (turn !== "first") expect(body.session_id).toBe("saved-session");
    if (turn === "hitl") {
      expect(body.interrupt_id).toBe("interrupt-1");
      expect(body.occurrence_id).toBe("occurrence-1");
    }
  });

  it.each(["first", "reopened", "hitl"])("blocks %s before runtime on a model preparation error", async (turn) => {
    const message = "No model is selected. Choose a model in the chat.";
    prepare.mockImplementation(() => ({
      unwrap: async () => ({ ...preparation, model_error: { code: "selection_missing", message } }),
    }));
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    let started: boolean | undefined;
    await act(async () => {
      started =
        turn === "hitl"
          ? await latest.sendHitlResume(pending, "cancel")
          : await latest.send("bonjour", turn === "first" ? null : "saved-session");
    });
    expect(started).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onTurnStarted).not.toHaveBeenCalled();
    expect(latest.messages).toEqual([]);
    expect(latest.waitResponse).toBe(false);
    expect(latest.preparation?.model_error?.message).toBe(message);
    expect(onError).toHaveBeenCalledWith(message);
  });

  it.each(["send", "hitl", "controls"])(
    "passes the explicit choice and requested reasoning to preparation for %s",
    async (turn) => {
      const choice = { source_id: "source", upstream_model_id: "model" };
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => new Response("", { status: 403 })),
      );
      await act(async () => {
        if (turn === "hitl")
          await latest.sendHitlResume(pending, "yes", undefined, { model_choice: choice, reasoning: true });
        else if (turn === "controls") await latest.prepareChatControls("saved-session", choice, true);
        else await latest.send("bonjour", "saved-session", { model_choice: choice, reasoning: true });
      });
      expect(prepare).toHaveBeenCalledWith(
        expect.objectContaining({ modelSourceId: "source", modelUpstreamId: "model", reasoning: true }),
      );
    },
  );

  it("blocks runtime when preparation lacks an admitted selection", async () => {
    prepare.mockImplementation(() => ({
      unwrap: async () => ({ ...preparation, inference: null }),
    }));
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await act(async () => {
      expect(await latest.send("bonjour", null)).toBe(false);
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onTurnStarted).not.toHaveBeenCalled();
  });

  it("preserves the configuration refusal code when HITL admission fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: { code: "agent_configuration_changed", message: "Changed" } }), {
            status: 409,
          }),
      ),
    );
    await act(async () => {
      expect(await latest.sendHitlResume(pending, "yes")).toBe(false);
    });
    expect(onError).toHaveBeenCalledExactlyOnceWith(expect.any(String), "agent_configuration_changed");
  });

  it.each([
    { detail: "A canonical space_id is required", expected: "A canonical space_id is required" },
    {
      detail: { message: "Execution refused", code: "refused", input: "private-input" },
      expected: "Execution refused",
      expectedCode: "refused",
    },
    {
      detail: [
        {
          loc: ["body"],
          msg: "Value error, runtime_context.space_id is required",
          input: "private-input",
          ctx: { token: "private-token" },
        },
      ],
      expected: "runtime_context.space_id is required",
    },
    { detail: [{ input: "private-input", ctx: { token: "private-token" } }], expected: "Runtime request failed (422)" },
  ])("reports only the diagnostic from $expected", async ({ detail, expected, expectedCode }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail }), { status: 422 })),
    );
    await act(async () => {
      await latest.send("bonjour", "saved-session");
    });
    expect(onError).toHaveBeenCalledExactlyOnceWith(expect.stringContaining(expected), expectedCode);
    const displayed = JSON.stringify(onError.mock.calls);
    expect(displayed).not.toContain("private-input");
    expect(displayed).not.toContain("private-token");
    expect(JSON.stringify(vi.mocked(console.error).mock.calls)).not.toContain("private-input");
  });
});
