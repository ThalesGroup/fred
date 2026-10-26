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

// The composer's model and reasoning control, closed: a text button naming the
// model and the reasoning mode, or plain text when nothing can be picked.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { COMPOSER_CHIP_WIDGETS, ReasoningChip, modelLabel, modelLabelFromCapabilityId } from "./ReasoningChip";
import type { ChatControlDescriptor, PreparationModels } from "../../../slices/controlPlane/controlPlaneOpenApi";
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

const first = { source_id: "source-a", upstream_model_id: "same/model" };
const second = { source_id: "source-b", upstream_model_id: "same/model" };
const models: PreparationModels = {
  recommendation: first,
  default: second,
  fallback: null,
  legacy_profile_id: null,
  requires_reselection: false,
  options: { temperature: 0.4, max_tokens: 300 },
  offers: [first, second].map((key) => ({
    key,
    candidate: true,
    selectable: true,
    permitted: true,
    diagnostics: [],
    metadata: { display_name: "Shared model" },
  })),
};

function render(
  controls: ChatControlDescriptor[],
  reasoning: boolean,
  disabled = false,
  model?: PreparationModels,
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

describe("ReasoningChip Weaver preparation", () => {
  it("renders nothing without advertised controls or model facts", () => {
    expect(render([], false)).toBe("");
  });
  it("shows the recommendation with its source and no unadvertised reasoning control", () => {
    const html = render([], false, false, models);
    expect(html).toContain("Shared model (source-a)");
    expect(html).not.toContain("reasoningRowLabel");
  });
  it("shows a retained unavailable recommendation instead of picking a candidate", () => {
    const html = render([], false, false, { ...models, offers: models.offers.slice(1) });
    expect(html).toContain("same/model (source-a)");
    expect(html).toContain("data-unavailable");
  });
  it("flags a forbidden retained offer", () => {
    const html = render([], false, false, {
      ...models,
      offers: models.offers.map((offer) => ({ ...offer, candidate: false, selectable: false })),
    });
    expect(html).toContain("data-unavailable");
  });
  it("only offers reasoning when preparation advertises its widget", () => {
    expect(render([reasoningControl()], false, true, models)).toContain("disabled");
    expect(render([reasoningControl()], true, false, models)).toContain("reasoningOn");
    expect(COMPOSER_CHIP_WIDGETS.has("reasoning_toggle")).toBe(true);
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
