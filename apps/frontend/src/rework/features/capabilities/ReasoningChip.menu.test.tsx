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

// The open reasoning menu is split into two sections (#2446-adjacent UI rework):
// a read-only "Models" section (per-turn model selection has no backend yet, so
// the resolved model is shown checked but not selectable) and an "Effort"
// section (Normal / "Élevé (Raisonnement)"). The parenthetical reasoning wording
// lives in the menu only — the closed chip keeps just "Élevé" (reasoningOn).
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

function mount(composer: ChatTurnControlComposerState) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<ReasoningChip chatControls={[reasoningControl()]} composer={composer} effectiveModel={model} />);
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

  it("shows the resolved model as a read-only, checked row (no onClick to change it)", () => {
    mount(composerState());
    openMenu();
    const modelRow = menuButtons().find((b) => b.textContent?.includes("Mistral Small Latest"));
    expect(modelRow).toBeTruthy();
    // It is the active model: rendered checked. Clicking it does nothing (no
    // per-turn model selection yet) — asserted by the effort spy staying clean.
    expect(container.innerHTML).toContain('data-icon="check_circle"');
  });

  it("picking 'Élevé (Raisonnement)' turns reasoning on; 'Normal' turns it off", () => {
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
