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

// The right-edge reasoning chip is an EFFORT PICKER (REASON-01 level 4 + 4b):
// a ContextualPicker over the closed set off/low/medium/high, whose chip text
// leads with the session's model identity (Claude-style). "off" is the
// tri-state decline; the three levels ride RuntimeContext.reasoning_effort.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ContextualPickerProps } from "@shared/molecules/ContextualPicker/ContextualPicker";
import { COMPOSER_CHIP_WIDGETS, ReasoningChip, modelLabelFromProfileId } from "./ReasoningChip";
import type { ChatControlDescriptor } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState, ReasoningEffortName } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Capture the picker's props instead of rendering its DOM: what this component
// owns is the wiring (gating, value, options, accent), not the chip visuals.
let pickerProps: ContextualPickerProps<ReasoningEffortName> | null = null;
vi.mock("@shared/molecules/ContextualPicker/ContextualPicker", () => ({
  ContextualPicker: (props: ContextualPickerProps<ReasoningEffortName>) => {
    pickerProps = props;
    return <div data-picker />;
  },
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
    reasoningEffort: "off",
    onReasoningEffortChange: () => undefined,
    ...over,
  } as ChatTurnControlComposerState;
}

function render(
  controls: ChatControlDescriptor[],
  reasoningEffort: ReasoningEffortName,
  disabled = false,
  modelProfileId: string | null = null,
): string {
  pickerProps = null;
  return renderToStaticMarkup(
    <ReasoningChip
      chatControls={controls}
      composer={composerState({ reasoningEffort })}
      modelProfileId={modelProfileId}
      disabled={disabled}
    />,
  );
}

describe("ReasoningChip (REASON-01 level 4 + 4b, right-edge effort picker)", () => {
  it("renders nothing when the agent does not offer the reasoning control", () => {
    expect(render([], "off")).toBe("");
    expect(pickerProps).toBeNull();
  });

  it("offers the full closed set, off first", () => {
    render([REASONING_CONTROL], "off");
    expect(pickerProps?.options.map((option) => option.value)).toEqual(["off", "low", "medium", "high"]);
  });

  it("reflects the current effort and stays neutral when off", () => {
    render([REASONING_CONTROL], "off");
    expect(pickerProps?.value).toBe("off");
    expect(pickerProps?.accent).toBe(false);
  });

  it("accents the chip whenever an effort level is active", () => {
    render([REASONING_CONTROL], "medium");
    expect(pickerProps?.value).toBe("medium");
    expect(pickerProps?.accent).toBe(true);
  });

  it("is disabled while a response streams", () => {
    render([REASONING_CONTROL], "off", true);
    expect(pickerProps?.disabled).toBe(true);
  });

  it("leads the chip text with the model identity when a profile is known", () => {
    render([REASONING_CONTROL], "high", false, "chat.mistral.small");
    expect(pickerProps?.valueLabel).toBe("Mistral Small · chatbot.composerSettings.reasoningHigh");
  });

  it("falls back to the effort alone when no team default profile exists", () => {
    render([REASONING_CONTROL], "high", false, null);
    expect(pickerProps?.valueLabel).toBe("chatbot.composerSettings.reasoningHigh");
  });

  it("explains the effort/latency trade-off in the menu header", () => {
    render([REASONING_CONTROL], "off");
    expect(pickerProps?.description).toBe("chatbot.composerSettings.reasoningEffortHint");
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
