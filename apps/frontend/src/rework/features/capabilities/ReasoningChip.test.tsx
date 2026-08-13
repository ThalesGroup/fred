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
import {
  COMPOSER_CHIP_WIDGETS,
  ReasoningChip,
  effortLabelKey,
  modelLabel,
  modelLabelFromCapabilityId,
} from "./ReasoningChip";
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

  it("leads the button with the bold model identity and a muted state", () => {
    const html = render(
      [reasoningControl({ default: false, effort: "high", model_id: "model__openai__mistral-small-latest" })],
      true,
    );
    // Two spans, weight/color contrast as the separator (no middot).
    expect(html).toMatch(/Mistral Small Latest<\/span>.*chatbot\.composerSettings\.reasoningHigh/);
    expect(html).not.toContain("·");
  });

  it("keeps the bare reasoning labels when no model is served", () => {
    const html = render([reasoningControl({ default: false, effort: "high" })], false);
    expect(html).not.toContain("Mistral");
  });

  it("shows the ops-authored display name instead of the derived guess", () => {
    const html = render(
      [
        reasoningControl({
          default: false,
          effort: "high",
          model_id: "model__anthropic__claude-sonnet-4-6",
          display_name: "Claude Sonnet 4.6",
        }),
      ],
      true,
    );
    expect(html).toContain("Claude Sonnet 4.6");
    // What the heuristic gets wrong: it reads "4-6" as two words.
    expect(html).not.toContain("Claude Sonnet 4 6");
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

describe("modelLabelFromCapabilityId (the fallback when ops named nothing)", () => {
  it("handles the major providers' real model names", () => {
    // OpenAI — version dots survive, GPT/ChatGPT cased, "latest" kept.
    expect(modelLabelFromCapabilityId("model__openai__gpt-4o")).toBe("GPT 4o");
    expect(modelLabelFromCapabilityId("model__openai__gpt-4.1-mini")).toBe("GPT 4.1 Mini");
    expect(modelLabelFromCapabilityId("model__openai__gpt-5.1")).toBe("GPT 5.1");
    expect(modelLabelFromCapabilityId("model__openai__o3")).toBe("O3");
    expect(modelLabelFromCapabilityId("model__openai__chatgpt-4o-latest")).toBe("ChatGPT 4o Latest");
    // Anthropic — release date stamps dropped, versions kept.
    expect(modelLabelFromCapabilityId("model__anthropic__claude-fable-5")).toBe("Claude Fable 5");
    expect(modelLabelFromCapabilityId("model__anthropic__claude-haiku-4-5-20251001")).toBe("Claude Haiku 4 5");
    // Mistral — the fleet, incl. the catalog's own entry.
    expect(modelLabelFromCapabilityId("model__openai__mistral-small-latest")).toBe("Mistral Small Latest");
    expect(modelLabelFromCapabilityId("model__mistral__codestral-latest")).toBe("Codestral Latest");
    expect(modelLabelFromCapabilityId("model__mistral__open-mixtral-8x7b")).toBe("Open Mixtral 8x7B");
    // Google / Meta / DeepSeek.
    expect(modelLabelFromCapabilityId("model__google__gemini-2.5-pro")).toBe("Gemini 2.5 Pro");
    expect(modelLabelFromCapabilityId("model__ollama__llama-3.3-70b-instruct")).toBe("Llama 3.3 70B Instruct");
    expect(modelLabelFromCapabilityId("model__deepseek__deepseek-r1")).toBe("DeepSeek R1");
  });

  it("rejects anything that is not a model capability id", () => {
    expect(modelLabelFromCapabilityId("document_access")).toBeNull();
    expect(modelLabelFromCapabilityId(undefined)).toBeNull();
  });
});

describe("modelLabel (ops-authored name wins, heuristic is the fallback)", () => {
  it("returns the authored name verbatim", () => {
    // Verbatim: no re-casing, no token rewriting. Ops already decided.
    expect(modelLabel("Mistral Small", "model__openai__mistral-small-latest")).toBe("Mistral Small");
    expect(modelLabel("Mistral (Ollama)", "model__ollama__mistral:latest")).toBe("Mistral (Ollama)");
  });

  it("falls back to the derived label when the catalog names nothing", () => {
    expect(modelLabel(undefined, "model__openai__gpt-4.1-mini")).toBe("GPT 4.1 Mini");
    expect(modelLabel(null, "model__openai__gpt-4o")).toBe("GPT 4o");
  });

  it("treats a blank or non-string name as unauthored", () => {
    // A YAML key left as `model_display_name: ""` must not blank the button.
    expect(modelLabel("   ", "model__openai__gpt-4o")).toBe("GPT 4o");
    expect(modelLabel(42, "model__openai__gpt-4o")).toBe("GPT 4o");
  });

  it("stays null when neither source can name the model", () => {
    expect(modelLabel(undefined, "document_access")).toBeNull();
    expect(modelLabel(undefined, undefined)).toBeNull();
  });
});
