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

// AssistantTurn × chat parts (#1977): the acceptance path "emitting the part
// from the demo capability's tool renders the custom card INLINE in chat" —
// the turn renders raw uiParts through the registry, skipping unknown kinds.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { RawUiPart } from "@rework/types/parts";
import { AssistantTurn } from "./AssistantTurn";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (value: string) => value }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: () => undefined, showSuccess: () => undefined }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <span data-icon={type} />,
}));

vi.mock("@shared/molecules/ThoughtTrace/ThoughtTrace", () => ({
  ThoughtTrace: () => <div>thought-trace</div>,
}));

vi.mock("@shared/molecules/AssistantMessage/AssistantMessage", () => ({
  AssistantMessage: ({ text }: { text: string }) => <p>{text}</p>,
}));

vi.mock("@shared/molecules/ActionBar/ActionBar", () => ({
  ActionBar: () => <div>action-bar</div>,
}));

vi.mock("@shared/molecules/TokenUsageBadge/TokenUsageBadge", () => ({
  TokenUsageBadge: () => <div>token-usage</div>,
}));

function renderTurn(uiParts: RawUiPart[], isStreaming = false): string {
  return renderToStaticMarkup(
    <AssistantTurn
      text="the answer"
      traceMessages={[]}
      sources={[]}
      uiParts={uiParts}
      tokenUsage={null}
      isStreaming={isStreaming}
    />,
  );
}

const DEMO_CARD: RawUiPart = { type: "demo_card", title: "Demo echo", body: "HELLO" };
const UNKNOWN: RawUiPart = { type: "part_kind_from_the_future", payload: "??" };

describe("AssistantTurn × chat parts (#1977)", () => {
  it("renders the demo capability card inline with the answer", () => {
    const html = renderTurn([DEMO_CARD]);
    expect(html).toContain("the answer");
    expect(html).toContain("Demo echo");
    expect(html).toContain("HELLO");
  });

  it("skips unknown kinds without dropping known siblings or crashing", () => {
    const html = renderTurn([UNKNOWN, DEMO_CARD]);
    expect(html).toContain("HELLO");
    expect(html).not.toContain("part_kind_from_the_future");
  });

  it("hides parts while streaming (unchanged behavior)", () => {
    const html = renderTurn([DEMO_CARD], true);
    expect(html).not.toContain("Demo echo");
  });
});
