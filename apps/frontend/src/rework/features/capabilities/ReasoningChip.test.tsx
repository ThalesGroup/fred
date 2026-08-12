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

// The right-edge reasoning chip is a TOGGLE BUTTON (aria-pressed), the chip
// sibling of the switch affordance contract in ReasoningControl.test.tsx:
// one on/off setting, never a picker, never a checkbox.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { COMPOSER_CHIP_WIDGETS, ReasoningChip } from "./ReasoningChip";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <i data-icon={type} />,
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

function render(controls: ChatControlDescriptor[], reasoning: boolean, disabled = false): string {
  return renderToStaticMarkup(
    <ReasoningChip chatControls={controls} composer={composerState({ reasoning })} disabled={disabled} />,
  );
}

describe("ReasoningChip (REASON-01 level 4, right-edge chip)", () => {
  it("renders nothing when the agent does not offer the reasoning toggle", () => {
    expect(render([], false)).toBe("");
  });

  it("renders a toggle button reflecting the off state", () => {
    const html = render([REASONING_CONTROL], false);
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('data-on="false"');
    expect(html).toContain("chatbot.composerSettings.reasoningRowLabel");
    expect(html).toContain('data-icon="auto_awesome"');
  });

  it("reflects the on state", () => {
    const html = render([REASONING_CONTROL], true);
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('data-on="true"');
  });

  it("is disabled while a response streams", () => {
    expect(render([REASONING_CONTROL], false, true)).toContain("disabled");
  });

  it("owns the reasoning_toggle promotion out of the tune popover", () => {
    // ComposerControlSlot and ManagedChatPage filter on this set; the chip and
    // the filters must agree or the setting shows up twice (or nowhere).
    expect(COMPOSER_CHIP_WIDGETS.has("reasoning_toggle")).toBe(true);
    expect(COMPOSER_CHIP_WIDGETS.has("rag_scope")).toBe(false);
  });
});
