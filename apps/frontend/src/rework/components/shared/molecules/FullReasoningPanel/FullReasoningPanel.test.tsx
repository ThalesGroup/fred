// @vitest-environment happy-dom
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const computed = vi.hoisted(() => ({ calls: 0 }));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../ChatSidePanel/ChatSidePanel", () => ({
  default: ({
    open,
    title,
    headerActions,
    children,
  }: {
    open: boolean;
    title: string;
    headerActions: ReactNode;
    children: ReactNode;
  }) => (
    // Like the real drawer, its content stays mounted while it slides out.
    <aside data-title={title} data-open={open}>
      {headerActions}
      {children}
    </aside>
  ),
}));
vi.mock("../MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }: { text: string }) => <div data-markdown>{text}</div>,
}));
vi.mock("@shared/atoms/Tooltip/Tooltip", () => ({
  Tooltip: ({ text, children }: { text: string; children: ReactNode }) => <span data-tooltip={text}>{children}</span>,
}));
vi.mock("./fullReasoning", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./fullReasoning")>();
  return {
    ...actual,
    fullReasoning: (messages: ChatMessage[]) => {
      computed.calls++;
      return actual.fullReasoning(messages);
    },
  };
});

import { FullReasoningPanel } from "./FullReasoningPanel";

const base = { session_id: "s1", exchange_id: "e1", timestamp: "2026-01-01T00:00:00.000Z", role: "assistant" } as const;
const MESSAGES: ChatMessage[] = [
  { ...base, rank: 0, role: "user", channel: "final", parts: [{ type: "text", text: "List the files" }] },
  {
    ...base,
    rank: 1,
    channel: "thought",
    parts: [{ type: "text", text: "I will call the document tree tool." }],
    metadata: { extras: { thought_id: "t1", duration_ms: 1500 } },
  },
];

const render = (open: boolean, messages = MESSAGES) =>
  renderToStaticMarkup(<FullReasoningPanel open={open} onClose={() => undefined} messages={messages} />);

describe("FullReasoningPanel", () => {
  it("shows each turn's question above its reasoning, with the block's duration", () => {
    const html = render(true);
    expect(html).toContain("List the files");
    expect(html).toContain("I will call the document tree tool.");
    expect(html).toContain("1.5s");
  });

  it("offers the copy action with a tooltip naming it", () => {
    expect(render(true)).toContain('data-tooltip="chatbot.fullReasoning.copy"');
  });

  it("says so when the conversation holds no reasoning yet", () => {
    expect(render(true, [MESSAGES[0]])).toContain("chatbot.fullReasoning.empty");
  });

  // `messages` changes on every streamed token; a closed panel must not pay for it.
  it("does not compute the reasoning while closed", () => {
    computed.calls = 0;
    render(false);
    expect(computed.calls).toBe(0);
  });

  // The drawer still shows its content during the close animation: emptying it
  // on close flashed the empty state and disabled the copy action on the way out.
  it("keeps the last reasoning on screen once closed, without recomputing it", () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const mount = (open: boolean, messages: ChatMessage[]) =>
      act(() => root.render(<FullReasoningPanel open={open} onClose={() => undefined} messages={messages} />));

    mount(true, MESSAGES);
    computed.calls = 0;
    mount(false, [...MESSAGES]);

    expect(container.textContent).toContain("I will call the document tree tool.");
    expect(container.textContent).not.toContain("chatbot.fullReasoning.empty");
    expect(computed.calls).toBe(0);
    act(() => root.unmount());
  });
});
