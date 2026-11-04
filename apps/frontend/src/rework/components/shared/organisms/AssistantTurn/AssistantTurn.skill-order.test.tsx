// @vitest-environment jsdom
// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import { toThreadMessages } from "@rework/components/pages/ManagedChatPage/toThreadMessages";
import { TraceDrawerProvider } from "@shared/molecules/ThoughtTrace/traceDrawerContext";
import { AssistantTurn } from "./AssistantTurn";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <span data-icon={type} />,
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));
vi.mock("@shared/molecules/AssistantMessage/AssistantMessage", () => ({
  AssistantMessage: ({ text }: { text: string }) => <p>{text}</p>,
}));

function message(rank: number, overrides: Partial<ChatMessage>): ChatMessage {
  return {
    session_id: "session",
    exchange_id: "exchange",
    rank,
    timestamp: "2026-10-28T10:00:00Z",
    role: "assistant",
    channel: "final",
    parts: [],
    ...overrides,
  };
}

function load(rank: number, name: string, origin: "user" | "agent", child = false): ChatMessage {
  return message(rank, {
    role: "system",
    channel: "system_note",
    metadata: { extras: { skill_load: { name, origin, child, load_id: `pin:${name}` } } },
  });
}

const thought = message(6, {
  channel: "thought",
  parts: [{ type: "text", text: "Follow the loaded procedures" }],
  metadata: { extras: { thought_id: "thought", source: "model_native", duration_ms: 1200 } },
});
const openTrace = vi.fn();
let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  localStorage.clear();
  openTrace.mockClear();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

async function render(messages: ChatMessage[], streaming: boolean) {
  const turn = toThreadMessages(messages, streaming).find((row) => row.role === "assistant");
  if (!turn) throw new Error("Expected an assistant turn");
  await act(async () =>
    root.render(
      <TraceDrawerProvider value={{ openTrace }}>
        <AssistantTurn
          text={turn.text}
          traceMessages={turn.traceMessages}
          sources={[]}
          uiParts={[]}
          isStreaming={turn.isStreaming}
        />
      </TraceDrawerProvider>,
    ),
  );
}

function skill(name: string): HTMLButtonElement | undefined {
  return [...host.querySelectorAll<HTMLButtonElement>("button")].find((button) =>
    button.getAttribute("aria-label")?.endsWith(`chatbot.skills.loaded: ${name}`),
  );
}

describe("AssistantTurn skill load placement", () => {
  it.each([false, true])("keeps explicit pins before the reasoning group (streaming: %s)", async (streaming) => {
    await render(
      [
        message(3, { role: "user", parts: [{ type: "text", text: "/graph /meeting-minutes Summarize" }] }),
        load(4, "graph", "user"),
        load(5, "meeting-minutes", "user"),
        thought,
        load(7, "compare-options", "agent"),
        message(8, {
          channel: "tool_call",
          parts: [{ type: "tool_call", call_id: "read", name: "read_file", args: { file_path: "/notes.md" } }],
        }),
        message(9, {
          role: "tool",
          channel: "tool_result",
          parts: [{ type: "tool_result", call_id: "read", ok: true, content: "Notes" }],
        }),
        message(10, { parts: [{ type: "text", text: "Answer" }] }),
      ],
      streaming,
    );
    const toggle = host.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    expect(skill("graph")).toBeDefined();
    expect(skill("meeting-minutes")).toBeDefined();
    expect(
      skill("graph")!.compareDocumentPosition(skill("meeting-minutes")!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(skill("meeting-minutes")!.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(skill("graph")!.getAttribute("aria-label")).toMatch(/^1\. /);
    expect(skill("meeting-minutes")!.getAttribute("aria-label")).toMatch(/^2\. /);

    await act(async () => skill("graph")!.click());
    expect(openTrace).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "solo", message: expect.objectContaining({ rank: 4 }) }),
    );
    if (!streaming) await act(async () => toggle.click());
    const reasoning = host.querySelector<HTMLButtonElement>('button[aria-label="Follow the loaded procedures"]')!;
    expect(toggle.compareDocumentPosition(reasoning) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      reasoning.compareDocumentPosition(skill("compare-options")!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(skill("compare-options")!.getAttribute("aria-label")).toMatch(/^3\. /);
    const tool = host.querySelector<HTMLElement>('[role="button"][aria-label^="4. "]')!;
    expect(skill("compare-options")!.compareDocumentPosition(tool) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await act(async () => toggle.click());
    expect(skill("graph")).toBeDefined();
    expect(skill("compare-options")).toBeUndefined();
  });

  it.each([
    { origin: "agent" as const, child: false },
    { origin: "agent" as const, child: true },
    { origin: "user" as const, child: true },
  ])("leaves $origin/child=$child loads and following activities below the header", async ({ origin, child }) => {
    await render(
      [
        message(3, { role: "user", parts: [{ type: "text", text: "Summarize" }] }),
        load(4, "compare-options", origin, child),
        load(5, "graph", "user"),
        thought,
      ],
      true,
    );
    const toggle = host.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    const reasoning = host.querySelector<HTMLButtonElement>('button[aria-label="Follow the loaded procedures"]')!;
    expect(toggle.compareDocumentPosition(skill("compare-options")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      skill("compare-options")!.compareDocumentPosition(skill("graph")!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(skill("graph")!.compareDocumentPosition(reasoning) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows only the preload rows until another activity arrives", async () => {
    const initial = [
      message(3, { role: "user", parts: [{ type: "text", text: "/graph Summarize" }] }),
      load(4, "graph", "user"),
    ];
    await render(initial, true);
    expect(skill("graph")).toBeDefined();
    expect(host.querySelector("button[aria-expanded]")).toBeNull();

    await render([...initial, thought], true);
    const toggle = host.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    expect(skill("graph")!.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
