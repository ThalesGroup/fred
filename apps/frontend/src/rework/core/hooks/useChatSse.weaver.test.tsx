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
  },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "fr-FR", t: (key: string) => key } }),
}));
vi.mock("../../../common/platformAccess", () => ({ handlePlatformAccessResponse: vi.fn() }));

import { useChatSse, type RuntimeAwaitingHumanEvent } from "./useChatSse";
import type { ExecutionPreparation } from "../../../slices/controlPlane/controlPlaneOpenApi";

const spaceId = "f0137825-89b0-4d36-bdc3-b007a9777122";
const preparation: ExecutionPreparation = {
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

  it.each(["send", "hitl", "controls"])("passes the explicit choice to preparation for %s", async (turn) => {
    const choice = { source_id: "source", upstream_model_id: "model" };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 403 })),
    );
    await act(async () => {
      if (turn === "hitl") await latest.sendHitlResume(pending, "yes", undefined, { model_choice: choice });
      else if (turn === "controls") await latest.prepareChatControls("saved-session", choice);
      else await latest.send("bonjour", "saved-session", { model_choice: choice });
    });
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({ modelSourceId: "source", modelUpstreamId: "model" }),
    );
  });

  it.each([
    { detail: "A canonical space_id is required", expected: "A canonical space_id is required" },
    {
      detail: { message: "Execution refused", code: "refused", input: "private-input" },
      expected: "Execution refused",
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
  ])("reports only the diagnostic from $expected", async ({ detail, expected }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail }), { status: 422 })),
    );
    await act(async () => {
      await latest.send("bonjour", "saved-session");
    });
    expect(onError).toHaveBeenCalledWith(expect.stringContaining(expected));
    const displayed = JSON.stringify(onError.mock.calls);
    expect(displayed).not.toContain("private-input");
    expect(displayed).not.toContain("private-token");
    expect(JSON.stringify(vi.mocked(console.error).mock.calls)).not.toContain("private-input");
  });
});
