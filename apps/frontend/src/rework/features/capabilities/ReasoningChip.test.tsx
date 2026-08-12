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

// The right-edge reasoning control (REASON-01 level 4), per the designer's
// Composer.html mockup: a plain text button + chevron reading "Raisonnement"
// when off and the model's ops-authored effort level when on. The level comes
// from the control's params.effort (derived from settings.reasoning_effort —
// the single source of truth); the wire stays the tri-state boolean.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { COMPOSER_CHIP_WIDGETS, ReasoningChip, effortLabelKey } from "./ReasoningChip";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <i data-icon={type} />,
}));

function reasoningControl(params: Record<string, unknown> = { default: false }): ChatControlDescriptor {
  return { capability_id: "platform", widget: "reasoning_toggle", params };
}

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

function render(controls: ChatControlDescriptor[], reasoning: boolean, disabled = false): string {
  return renderToStaticMarkup(
    <ReasoningChip chatControls={controls} composer={composerState({ reasoning })} disabled={disabled} />,
  );
}

describe("ReasoningChip (REASON-01 level 4, mockup text button)", () => {
  it("renders nothing when the agent does not offer the reasoning control", () => {
    expect(render([], false)).toBe("");
  });

  it("reads the setting name when off — never a level", () => {
    const html = render([reasoningControl({ default: false, effort: "high" })], false);
    expect(html).toContain("chatbot.composerSettings.reasoningRowLabel");
    expect(html).not.toContain("chatbot.composerSettings.reasoningHigh");
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('data-icon="keyboard_arrow_down"');
  });

  it("reads the model's ops-authored level when on", () => {
    const html = render([reasoningControl({ default: false, effort: "high" })], true);
    expect(html).toContain("chatbot.composerSettings.reasoningHigh");
  });

  it("falls back to a generic On label when no effort is served", () => {
    const html = render([reasoningControl()], true);
    expect(html).toContain("chatbot.composerSettings.reasoningOn");
  });

  it("is disabled while a response streams", () => {
    expect(render([reasoningControl()], false, true)).toContain("disabled");
  });

  it("owns the reasoning_toggle promotion out of the tune popover", () => {
    // ComposerControlSlot and ManagedChatPage filter on this set; the button
    // and the filters must agree or the setting shows up twice (or nowhere).
    expect(COMPOSER_CHIP_WIDGETS.has("reasoning_toggle")).toBe(true);
    expect(COMPOSER_CHIP_WIDGETS.has("rag_scope")).toBe(false);
  });
});

describe("effortLabelKey", () => {
  it("maps the closed set and rejects anything else", () => {
    expect(effortLabelKey("low")).toBe("chatbot.composerSettings.reasoningLow");
    expect(effortLabelKey("medium")).toBe("chatbot.composerSettings.reasoningMedium");
    expect(effortLabelKey("high")).toBe("chatbot.composerSettings.reasoningHigh");
    // Unknown provider-specific values (xhigh, max…) must not crash the menu
    // — they fall back to the generic On label.
    expect(effortLabelKey("xhigh")).toBeNull();
    expect(effortLabelKey(undefined)).toBeNull();
  });
});
