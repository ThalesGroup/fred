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
import { COMPOSER_CHIP_WIDGETS, ReasoningChip, modelLabel, modelLabelFromCapabilityId } from "./ReasoningChip";
import type { ChatControlDescriptor, EffectiveChatModel } from "../../../slices/controlPlane/controlPlaneOpenApi";
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

function effectiveModel(over: Partial<EffectiveChatModel> = {}): EffectiveChatModel {
  return { enabled_for_team: true, ...over } as EffectiveChatModel;
}

function render(
  controls: ChatControlDescriptor[],
  reasoning: boolean,
  disabled = false,
  model?: EffectiveChatModel,
): string {
  return renderToStaticMarkup(
    <ReasoningChip
      chatControls={controls}
      composer={composerState({ reasoning })}
      disabled={disabled}
      effectiveModel={model}
    />,
  );
}

describe("ReasoningChip (REASON-01 level 4, mockup text button)", () => {
  it("renders nothing when the agent does not offer the reasoning control", () => {
    expect(render([], false)).toBe("");
  });

  it("reads the setting name when off — never a level", () => {
    const html = render([reasoningControl({ default: false })], false);
    expect(html).toContain("chatbot.composerSettings.reasoningRowLabel");
    expect(html).not.toContain("chatbot.composerSettings.reasoningOn");
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('data-icon="keyboard_arrow_down"');
  });

  it("is disabled while a response streams", () => {
    expect(render([reasoningControl()], false, true)).toContain("disabled");
  });

  it("leads the button with the bold model identity and a muted state", () => {
    const html = render([reasoningControl({ default: false })], true, false, {
      ...effectiveModel({ capability_id: "model__openai__mistral-small-latest" }),
    });
    // Two spans, weight/color contrast as the separator (no middot).
    expect(html).toMatch(/Mistral Small Latest<\/span>.*chatbot\.composerSettings\.reasoningOn/);
    expect(html).not.toContain("·");
  });

  it("keeps the bare reasoning labels when no model is served", () => {
    const html = render([reasoningControl({ default: false })], false);
    expect(html).not.toContain("Mistral");
  });

  it("shows the ops-authored display name instead of the derived guess", () => {
    const html = render([reasoningControl({ default: false })], true, false, {
      ...effectiveModel({
        capability_id: "model__anthropic__claude-sonnet-4-6",
        display_name: "Claude Sonnet 4.6",
      }),
    });
    expect(html).toContain("Claude Sonnet 4.6");
    // What the heuristic gets wrong: it reads "4-6" as two words.
    expect(html).not.toContain("Claude Sonnet 4 6");
  });

  // #2387 — the model label and the reasoning menu are independent. What went
  // wrong before: the chip took its model identity from the reasoning control's
  // params, i.e. the single model whose REASONING was enabled platform-wide, so
  // it contradicted any platform binding or team override in force.

  it("names the resolved model even when the agent offers no reasoning", () => {
    const html = render([], false, false, effectiveModel({ capability_id: "model__openai__gpt-4.1" }));
    expect(html).toContain("GPT 4.1");
    // No menu, no chevron, nothing clickable — there is no action being withheld.
    expect(html).not.toContain('aria-haspopup="menu"');
    expect(html).not.toContain("<button");
  });

  it("renders nothing when there is neither a reasoning control nor a model", () => {
    expect(render([], false, false, undefined)).toBe("");
  });

  it("ignores a model identity smuggled in through the reasoning control params", () => {
    // The old source of truth. It must no longer be read at all, or the chip
    // would keep naming the reasoning-enabled model.
    const html = render(
      [
        reasoningControl({
          default: false,
          model_id: "model__openai__mistral-small-latest",
          display_name: "Mistral Small 4",
        }),
      ],
      false,
    );
    expect(html).not.toContain("Mistral Small 4");
    expect(html).not.toContain("Mistral");
  });

  it("prefers the resolved model over anything the control claims", () => {
    const html = render(
      [reasoningControl({ default: false, model_id: "model__openai__mistral-small-latest" })],
      false,
      false,
      effectiveModel({ capability_id: "model__openai__gpt-4.1", display_name: "GPT-4.1" }),
    );
    expect(html).toContain("GPT-4.1");
    expect(html).not.toContain("Mistral");
  });

  it("flags a model the team is not enabled for, in the interactive chip", () => {
    const html = render(
      [reasoningControl({ default: false })],
      false,
      false,
      effectiveModel({ capability_id: "model__openai__gpt-4.1", enabled_for_team: false }),
    );
    expect(html).toContain("GPT 4.1");
    expect(html).toContain("data-unavailable");
    expect(html).toContain('data-icon="error_outline"');
    // The reason must reach the accessible name, not only the colour.
    expect(html).toContain("chatbot.composerSettings.modelNotEnabledForTeam");
  });

  it("flags a model the team is not enabled for, with no reasoning control", () => {
    const html = render(
      [],
      false,
      false,
      effectiveModel({ capability_id: "model__openai__gpt-4.1", enabled_for_team: false }),
    );
    expect(html).toContain("data-unavailable");
    expect(html).toContain("chatbot.composerSettings.modelNotEnabledForTeam");
  });

  it("does not flag an enabled model", () => {
    const html = render(
      [reasoningControl({ default: false })],
      false,
      false,
      effectiveModel({ capability_id: "model__openai__gpt-4.1" }),
    );
    expect(html).not.toContain("data-unavailable");
    expect(html).not.toContain('data-icon="error_outline"');
  });

  // The bug seen in production: reasoning enabled on mistral-small-latest, a team
  // override routing to mistral-medium-latest, and the composer offered a toggle
  // the pod would then strip. The routed model has the last word.

  it("hides the reasoning menu when the routed model has reasoning off", () => {
    const html = render(
      [reasoningControl({ default: false })],
      false,
      false,
      effectiveModel({
        capability_id: "model__openai__mistral-medium-latest",
        name: "mistral-medium-latest",
        display_name: "Mistral Medium 3.5",
        reasoning_enabled: false,
      }),
    );
    // The model is still named — only the inert toggle goes away.
    expect(html).toContain("Mistral Medium 3.5");
    expect(html).not.toContain('aria-haspopup="menu"');
    expect(html).not.toContain("<button");
    expect(html).not.toContain("chatbot.composerSettings.reasoningOff");
  });

  it("keeps the reasoning menu when the routed model has reasoning on", () => {
    const html = render(
      [reasoningControl({ default: false })],
      true,
      false,
      effectiveModel({
        capability_id: "model__openai__mistral-small-latest",
        name: "mistral-small-latest",
        reasoning_enabled: true,
      }),
    );
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain("chatbot.composerSettings.reasoningOn");
  });

  it("leaves the control alone when reasoning support is unknown", () => {
    // No resolution yet, or an older backend: fall back to what the platform
    // served rather than silently hiding a control that may well work.
    const html = render([reasoningControl({ default: false })], false, false, undefined);
    expect(html).toContain('aria-haspopup="menu"');
  });

  it("still hides an inert toggle for a model that is also not enabled for the team", () => {
    const html = render(
      [reasoningControl({ default: false })],
      false,
      false,
      effectiveModel({
        capability_id: "model__openai__gpt-4.1",
        name: "gpt-4.1",
        reasoning_enabled: false,
        enabled_for_team: false,
      }),
    );
    expect(html).not.toContain('aria-haspopup="menu"');
    // Both facts still reach the user.
    expect(html).toContain("GPT 4.1");
    expect(html).toContain("data-unavailable");
  });

  // #2387 — the state reads as two modes, not on/off. "Désactivé" beside a model
  // name read as though the MODEL were off; nothing tied the word to reasoning.

  it("marks the active mode so colour reinforces the word", () => {
    const on = render([reasoningControl({ default: false })], true, false, effectiveModel({ name: "gpt-4.1" }));
    expect(on).toContain("data-on");
    expect(on).toContain("chatbot.composerSettings.reasoningOn");

    const off = render([reasoningControl({ default: false })], false, false, effectiveModel({ name: "gpt-4.1" }));
    // The resting mode carries no marker — and still says which mode it is,
    // so the accent is reinforcement and never the only signal.
    expect(off).not.toContain("data-on");
    expect(off).toContain("chatbot.composerSettings.reasoningOff");
  });

  it("ties the state to reasoning in the accessible name", () => {
    // The visible words name the mode alone; a screen-reader user gets the
    // subject too, which sighted users read off the menu header.
    const html = render([reasoningControl({ default: false })], false, false, effectiveModel({ name: "gpt-4.1" }));
    expect(html).toContain(
      'aria-label="chatbot.composerSettings.reasoningRowLabel: chatbot.composerSettings.reasoningOff"',
    );
  });

  it("owns the reasoning_toggle promotion out of the tune popover", () => {
    // ComposerControlSlot and ManagedChatPage filter on this set; the button
    // and the filters must agree or the setting shows up twice (or nowhere).
    expect(COMPOSER_CHIP_WIDGETS.has("reasoning_toggle")).toBe(true);
    expect(COMPOSER_CHIP_WIDGETS.has("rag_scope")).toBe(false);
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

describe("modelLabel (ops-authored name, then the real model name, then the id)", () => {
  it("returns the authored name verbatim", () => {
    // Verbatim: no re-casing, no token rewriting. Ops already decided.
    expect(modelLabel("Mistral Small", "mistral-small-latest", "model__openai__mistral-small-latest")).toBe(
      "Mistral Small",
    );
    expect(modelLabel("Mistral (Ollama)", "mistral:latest", "model__ollama__mistral:latest")).toBe("Mistral (Ollama)");
  });

  it("prefers the real model name over the capability id (#2387)", () => {
    // `model_capability_id` normalizes non-id-safe characters, so the id path
    // would mangle this one — the whole reason `name` is carried.
    expect(modelLabel(undefined, "mistral:latest", "model__ollama__mistral-latest")).toBe("Mistral:latest");
    expect(modelLabel(undefined, "gpt-4.1-mini", "model__openai__gpt-4.1-mini")).toBe("GPT 4.1 Mini");
  });

  it("falls back to the derived label when neither a display name nor a model name is served", () => {
    expect(modelLabel(undefined, undefined, "model__openai__gpt-4.1-mini")).toBe("GPT 4.1 Mini");
    expect(modelLabel(null, null, "model__openai__gpt-4o")).toBe("GPT 4o");
  });

  it("treats a blank or non-string name as unauthored", () => {
    // A YAML key left as `model_display_name: ""` must not blank the button.
    expect(modelLabel("   ", undefined, "model__openai__gpt-4o")).toBe("GPT 4o");
    expect(modelLabel(42, undefined, "model__openai__gpt-4o")).toBe("GPT 4o");
    expect(modelLabel(undefined, "  ", "model__openai__gpt-4o")).toBe("GPT 4o");
  });

  it("stays null when no source can name the model", () => {
    expect(modelLabel(undefined, undefined, "document_access")).toBeNull();
    expect(modelLabel(undefined, undefined, undefined)).toBeNull();
  });
});
