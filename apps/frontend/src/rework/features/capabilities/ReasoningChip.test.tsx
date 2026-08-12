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

// The right-edge reasoning chip (REASON-01 level 4): model identity + on/off
// state on the trigger, one SWITCH row in its menu (Claude's "Thinking"
// toggle is the reference). No effort levels on purpose — the effort a
// reasoning turn runs with is the ops-authored `reasoning_effort` of the
// routed profile (RUNTIME-EXECUTION-CONTRACT §8.48).

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { COMPOSER_CHIP_WIDGETS, ReasoningChip, modelLabelFromProfileId } from "./ReasoningChip";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <i data-icon={type} />,
}));

vi.mock("@shared/atoms/Tooltip/Tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const REASONING_CONTROL: ChatControlDescriptor = {
  capability_id: "platform",
  widget: "reasoning_toggle",
  params: { default: false },
};

function composerState(over: Partial<ChatTurnControlComposerState> = {}): ChatTurnControlComposerState {
  return {
    teamId: "fredlab",
    onAttach: () => undefined,
    selectedLibraryIds: [],
    onSelectedLibraryIdsChange: () => undefined,
    selectedDocumentUids: [],
    onSelectedDocumentUidsChange: () => undefined,
    searchPolicy: "hybrid",
    onSearchPolicyChange: () => undefined,
    ragScope: "hybrid",
    onRagScopeChange: () => undefined,
    reasoning: false,
    onReasoningChange: () => undefined,
    ...over,
  } as ChatTurnControlComposerState;
}

function render(
  controls: ChatControlDescriptor[],
  reasoning: boolean,
  disabled = false,
  modelProfileId: string | null = null,
): string {
  return renderToStaticMarkup(
    <ReasoningChip
      chatControls={controls}
      composer={composerState({ reasoning })}
      modelProfileId={modelProfileId}
      disabled={disabled}
    />,
  );
}

describe("ReasoningChip (REASON-01 level 4, right-edge chip)", () => {
  it("renders nothing when the agent does not offer the reasoning control", () => {
    expect(render([], false)).toBe("");
  });

  it("shows the off state without the accent styling", () => {
    const html = render([REASONING_CONTROL], false);
    expect(html).toContain("chatbot.composerSettings.reasoningOff");
    expect(html).not.toContain('data-accent="true"');
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain('aria-expanded="false"');
  });

  it("accents the chip and shows the on state when reasoning is on", () => {
    const html = render([REASONING_CONTROL], true);
    expect(html).toContain("chatbot.composerSettings.reasoningOn");
    expect(html).toContain('data-accent="true"');
  });

  it("is disabled while a response streams", () => {
    expect(render([REASONING_CONTROL], false, true)).toContain("disabled");
  });

  it("leads the chip text with the model identity when a profile is known", () => {
    const html = render([REASONING_CONTROL], true, false, "chat.mistral.small");
    expect(html).toContain("Mistral Small · chatbot.composerSettings.reasoningOn");
  });

  it("falls back to the state alone when no team default profile exists", () => {
    const html = render([REASONING_CONTROL], true, false, null);
    expect(html).not.toContain("·");
    expect(html).toContain("chatbot.composerSettings.reasoningOn");
  });

  it("owns the reasoning_toggle promotion out of the tune popover", () => {
    // ComposerControlSlot and ManagedChatPage filter on this set; the chip and
    // the filters must agree or the setting shows up twice (or nowhere).
    expect(COMPOSER_CHIP_WIDGETS.has("reasoning_toggle")).toBe(true);
    expect(COMPOSER_CHIP_WIDGETS.has("rag_scope")).toBe(false);
  });
});

describe("modelLabelFromProfileId (temporary heuristic until multi-model)", () => {
  it("drops routing qualifiers and title-cases the identity", () => {
    expect(modelLabelFromProfileId("chat.mistral.small")).toBe("Mistral Small");
    expect(modelLabelFromProfileId("default.chat.openai.prod")).toBe("Openai Prod");
  });

  it("returns null for null/empty ids", () => {
    expect(modelLabelFromProfileId(null)).toBeNull();
    expect(modelLabelFromProfileId("")).toBeNull();
  });
});
