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

import { act, createRef, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const assistantTurnRenderMock = vi.hoisted(() => vi.fn());

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/organisms/ChatMessagesArea/ChatMessagesArea", () => ({
  ChatMessagesArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@shared/organisms/UserTurn/UserTurn", () => ({ UserTurn: () => null }));
vi.mock("@shared/organisms/AssistantTurn/AssistantTurn", async () => {
  const { memo } = await vi.importActual<typeof import("react")>("react");
  return {
    AssistantTurn: memo(function AssistantTurn(props: { pendingToolCallIds?: readonly string[] | null }) {
      assistantTurnRenderMock(props);
      return null;
    }),
  };
});
vi.mock("@shared/molecules/HitlPrompt/HitlPrompt.tsx", () => ({
  HitlPrompt: (props: {
    maxChatInputChars?: number;
    freeTextValue?: string;
    onAnswer: unknown;
    onFreeTextChange?: unknown;
  }) => (
    <div
      data-limit={props.maxChatInputChars}
      data-free-text={props.freeTextValue}
      data-has-answer-handler={typeof props.onAnswer === "function"}
      data-has-change-handler={typeof props.onFreeTextChange === "function"}
    />
  ),
}));

import { ConversationThread } from "./ConversationThread";

describe("ConversationThread HITL input policy wiring", () => {
  it("forwards the runtime limit and controlled draft to the active HITL prompt", () => {
    const html = renderToStaticMarkup(
      <ConversationThread
        messages={[]}
        pendingHitl={{
          type: "awaiting_human",
          session_id: "session-1",
          exchange_id: "exchange-1",
          payload: { free_text: true },
        }}
        isLoading={false}
        isStreaming={false}
        scrollContainerRef={createRef<HTMLDivElement>()}
        onHitlAnswer={() => undefined}
        maxChatInputChars={5}
        hitlFreeText="full draft"
        onHitlFreeTextChange={() => undefined}
      />,
    );

    expect(html).toContain('data-limit="5"');
    expect(html).toContain('data-free-text="full draft"');
    expect(html).toContain('data-has-answer-handler="true"');
    expect(html).toContain('data-has-change-handler="true"');
  });

  it("does not re-render historical assistant turns when only the HITL draft changes", () => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    assistantTurnRenderMock.mockClear();
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const pendingHitl = {
      type: "awaiting_human" as const,
      session_id: "session-1",
      exchange_id: "exchange-1",
      payload: { free_text: true, pending_calls: [] },
    };
    const messages = [
      {
        id: "assistant-1",
        role: "assistant" as const,
        text: "historical markdown",
        traceMessages: [],
        sources: [],
        uiParts: [],
        isStreaming: false,
      },
    ];
    const render = (hitlFreeText: string) => (
      <ConversationThread
        messages={messages}
        pendingHitl={pendingHitl}
        isLoading={false}
        isStreaming={false}
        scrollContainerRef={createRef<HTMLDivElement>()}
        onHitlAnswer={() => undefined}
        maxChatInputChars={5_000}
        hitlFreeText={hitlFreeText}
        onHitlFreeTextChange={() => undefined}
      />
    );

    act(() => root.render(render("a")));
    expect(assistantTurnRenderMock).toHaveBeenCalledTimes(1);
    act(() => root.render(render("ab")));
    expect(assistantTurnRenderMock).toHaveBeenCalledTimes(1);

    act(() => root.unmount());
    container.remove();
  });
});
