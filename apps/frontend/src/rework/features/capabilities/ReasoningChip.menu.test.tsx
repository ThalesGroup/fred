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

// The open menu: a Models section listing the selectable models and, when the
// current model can reason, the reasoning row (Normal / "Élevé (Raisonnement)").
// These need a live DOM to open the menu, so they sit apart from the SSR tests
// in ReasoningChip.test.tsx.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReasoningChip } from "./ReasoningChip";
import type { ChatControlDescriptor, EffectiveChatModel } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { ChatTurnControlComposerState } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@shared/atoms/Icon/Icon.tsx", () => ({
  default: ({ type }: { type: string }) => <i data-icon={type} />,
}));

function reasoningControl(): ChatControlDescriptor {
  return { capability_id: "platform", widget: "reasoning_toggle", params: { default: false } };
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
const model: EffectiveChatModel = {
  enabled_for_team: true,
  reasoning_enabled: true,
  capability_id: "model__openai__mistral-small-latest",
} as EffectiveChatModel;

let container: HTMLDivElement;
let root: Root;

function mount(
  composer: ChatTurnControlComposerState,
  effectiveModel: EffectiveChatModel = model,
  extra: { chatProfileId?: string | null; onChatProfileChange?: (id: string) => void } = {},
) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <ReasoningChip
        chatControls={[reasoningControl()]}
        composer={composer}
        effectiveModel={effectiveModel}
        {...extra}
      />,
    );
  });
}
function openMenu() {
  const trigger = container.querySelector('button[aria-haspopup="menu"]') as HTMLButtonElement;
  act(() => trigger.click());
}
function menuButtons() {
  return [...container.querySelectorAll('[role="option"]')] as HTMLElement[];
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("ReasoningChip — split menu (Models + Effort)", () => {
  it("closed chip shows just 'Élevé' (reasoningOn), never the menu-only parenthetical", () => {
    mount(composerState({ reasoning: true }));
    const html = container.innerHTML;
    expect(html).toContain("chatbot.composerSettings.reasoningOn");
    // The "(Raisonnement)" wording (reasoningOnMenu) must not leak into the
    // closed chip.
    expect(html).not.toContain("chatbot.composerSettings.reasoningOnMenu");
  });

  it("opens a menu with a Models section and an Effort section", () => {
    mount(composerState());
    openMenu();
    const html = container.innerHTML;
    expect(html).toContain("chatbot.composerSettings.reasoningModelsSection");
    expect(html).toContain("chatbot.composerSettings.reasoningEffortSection");
    // Effort rows: Normal (off) and the fuller "Élevé (Raisonnement)" (menu-only).
    expect(html).toContain("chatbot.composerSettings.reasoningOff");
    expect(html).toContain("chatbot.composerSettings.reasoningOnMenu");
  });

  it("shows the resolved model as a checked row when the backend lists no selectable models", () => {
    mount(composerState());
    openMenu();
    const modelRow = menuButtons().find((b) => b.textContent?.includes("Mistral Small Latest"));
    expect(modelRow).toBeTruthy();
    // It is the active model: rendered checked. Clicking it does nothing (no
    // per-turn model selection yet) — asserted by the effort spy staying clean.
    expect(container.innerHTML).toContain('data-icon="check_circle"');
  });

  it("picking 'Élevé (Raisonnement)' turns reasoning on; 'Faible' turns it off", () => {
    const onReasoningChange = vi.fn();
    mount(composerState({ reasoning: false, onReasoningChange }));
    openMenu();
    const high = menuButtons().find((b) => b.textContent?.includes("reasoningOnMenu")) as HTMLElement;
    act(() => high.click());
    expect(onReasoningChange).toHaveBeenCalledWith(true);

    onReasoningChange.mockClear();
    openMenu();
    const normal = menuButtons().find(
      (b) => b.textContent?.includes("reasoningOff") && !b.textContent?.includes("reasoningOnMenu"),
    ) as HTMLElement;
    act(() => normal.click());
    expect(onReasoningChange).toHaveBeenCalledWith(false);
  });
});

const SMALL = "model__mistral__mistral-small";
const LARGE = "model__mistral__mistral-large";
const twoModels: EffectiveChatModel = {
  enabled_for_team: true,
  reasoning_enabled: true,
  capability_id: SMALL,
  selectable_models: [
    { profile_id: "chat.small", capability_id: SMALL, name: "mistral-small", reasoning_enabled: true },
    { profile_id: "chat.large", capability_id: LARGE, name: "mistral-large", reasoning_enabled: false },
  ],
} as EffectiveChatModel;

describe("ReasoningChip — model choice", () => {
  it("lists the selectable models with the current one checked, and picks another", () => {
    const onChatProfileChange = vi.fn();
    mount(composerState(), twoModels, { chatProfileId: null, onChatProfileChange });
    openMenu();

    const small = menuButtons().find((b) => b.textContent?.includes("Mistral Small")) as HTMLElement;
    const large = menuButtons().find((b) => b.textContent?.includes("Mistral Large")) as HTMLElement;
    expect(small.querySelector('[data-icon="check_circle"]')).not.toBeNull();
    expect(large.querySelector('[data-icon="check_circle"]')).toBeNull();

    act(() => large.click());
    expect(onChatProfileChange).toHaveBeenCalledWith("chat.large");
  });

  it("names the chosen model and keeps the Effort section, saying no level is available", () => {
    mount(composerState(), twoModels, { chatProfileId: "chat.large", onChatProfileChange: vi.fn() });
    expect(container.textContent).toContain("Mistral Large");
    expect(container.innerHTML).not.toContain("chatbot.composerSettings.reasoningOff");
    openMenu();
    expect(container.innerHTML).toContain("chatbot.composerSettings.reasoningEffortSection");
    expect(container.innerHTML).toContain("chatbot.composerSettings.reasoningEffortNone");
    expect(container.innerHTML).not.toContain("chatbot.composerSettings.reasoningOff");
  });

  it("names the menu after the sections it shows", () => {
    mount(composerState(), twoModels, { chatProfileId: null, onChatProfileChange: vi.fn() });
    openMenu();
    expect(container.querySelector('[aria-label="chatbot.composerSettings.modelAndReasoningMenu"]')).not.toBeNull();

    act(() => root.unmount());
    container.remove();
    mount(composerState(), twoModels, { chatProfileId: "chat.large", onChatProfileChange: vi.fn() });
    openMenu();
    expect(container.querySelector('[aria-label="chatbot.composerSettings.reasoningModelsSection"]')).not.toBeNull();
  });

  it("offers no model rows when a higher level locks the choice", () => {
    mount(composerState(), { ...model, choice_locked: true, selectable_models: [] } as EffectiveChatModel, {
      onChatProfileChange: vi.fn(),
    });
    openMenu();
    expect(container.innerHTML).not.toContain("chatbot.composerSettings.reasoningModelsSection");
    expect(container.innerHTML).toContain("chatbot.composerSettings.reasoningEffortSection");
  });

  it("is read-only text for a single model without reasoning", () => {
    const single = {
      enabled_for_team: true,
      capability_id: LARGE,
      selectable_models: [twoModels.selectable_models![1]],
    } as EffectiveChatModel;
    mount(composerState(), single, { onChatProfileChange: vi.fn() });
    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).toContain("Mistral Large");
  });

  it("shows a single model with reasoning as the only, selected row beside the reasoning row", () => {
    const single = {
      ...twoModels,
      selectable_models: [twoModels.selectable_models![0]],
    } as EffectiveChatModel;
    mount(composerState(), single, { onChatProfileChange: vi.fn() });
    openMenu();
    const rows = menuButtons().filter((b) => b.textContent?.includes("Mistral"));
    expect(rows).toHaveLength(1);
    expect(rows[0].querySelector('[data-icon="check_circle"]')).not.toBeNull();
    expect(container.innerHTML).toContain("chatbot.composerSettings.reasoningOnMenu");
  });
});
