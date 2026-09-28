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

// ConversationThread's own memo covers the thread; UserTurn is memoized too, and
// a callback built per message would defeat that one instead — silently, since
// behaviour stays correct and only the render count regresses. The thread
// re-renders on every streamed frame, so a command turn would then re-render
// per token.
//
// Its own file rather than a block in ConversationThread.test.tsx: that suite
// renders through `renderToStaticMarkup` under the default `node` environment,
// and this one needs a real client root to re-render at all.

import { act, createRef, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ThreadMessage } from "@rework/types/thread";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const seenOnOpenCommand: unknown[] = [];

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/organisms/ChatMessagesArea/ChatMessagesArea", () => ({
  ChatMessagesArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@shared/organisms/UserTurn/UserTurn", () => ({
  UserTurn: ({ onOpenCommand }: { onOpenCommand?: unknown }) => {
    seenOnOpenCommand.push(onOpenCommand);
    return null;
  },
}));
vi.mock("@shared/organisms/AssistantTurn/AssistantTurn", () => ({ AssistantTurn: () => null }));
vi.mock("@shared/molecules/HitlPrompt/HitlPrompt.tsx", () => ({ HitlPrompt: () => null }));

import { ConversationThread } from "./ConversationThread";

const COMMAND_TURN: ThreadMessage = {
  id: "e1:user",
  role: "user",
  text: "Résume le document : 33 lignes",
  isStreaming: false,
  traceMessages: [],
  sources: [],
  uiParts: [],
  command: { command: "summary", appended_text: "33 lignes" },
};

describe("ConversationThread row callbacks", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    seenOnOpenCommand.length = 0;
  });

  it("hands every row the same onOpenCommand across re-renders", () => {
    const onOpenCommandPrompt = vi.fn();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    const render = () =>
      act(() => {
        root.render(
          <ConversationThread
            messages={[COMMAND_TURN]}
            pendingHitl={null}
            isLoading={false}
            isStreaming={false}
            scrollContainerRef={createRef<HTMLDivElement>()}
            onHitlAnswer={() => {}}
            hitlFreeText=""
            onHitlFreeTextChange={() => {}}
            onOpenCommandPrompt={onOpenCommandPrompt}
          />,
        );
      });

    render();
    // A streamed frame gives the thread a new `messages` array; the row's
    // callback must not change with it.
    render();

    expect(seenOnOpenCommand.length).toBeGreaterThanOrEqual(2);
    expect(seenOnOpenCommand[1]).toBe(seenOnOpenCommand[0]);
    expect(seenOnOpenCommand[0]).toBe(onOpenCommandPrompt);
  });
});
