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
import type { ChatControlDescriptor, PreparationModels } from "../../../slices/controlPlane/controlPlaneOpenApi";
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
    reasoning_enabled: true,
    diagnostics: [],
    metadata: { display_name: "Shared model" },
  })),
};
const model = models;

let container: HTMLDivElement;
let root: Root;

function mount(
  composer: ChatTurnControlComposerState,
  effectiveModel: PreparationModels = model,
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

describe("Weaver model menu", () => {
  it("keeps same-name offers from different sources distinct and sends the composite key", () => {
    const onChatProfileChange = vi.fn();
    mount(composerState(), models, { onChatProfileChange });
    openMenu();
    const rows = menuButtons();
    expect(rows.some((row) => row.textContent?.includes("source-a"))).toBe(true);
    const other = rows.find((row) => row.textContent?.includes("source-b"))!;
    act(() => other.click());
    expect(onChatProfileChange).toHaveBeenCalledWith(JSON.stringify([second.source_id, second.upstream_model_id]));
  });
  it("does not substitute the recommendation for a missing explicit choice", () => {
    mount(composerState(), models, { chatProfileId: JSON.stringify(["retired", "model"]) });
    expect(container.textContent).toContain("retired");
    expect(container.querySelector("[data-unavailable]")).not.toBeNull();
  });
  it("excludes unselectable offers from new choices without changing the retained reference", () => {
    mount(composerState(), { ...models, offers: models.offers.map((offer) => ({ ...offer, selectable: false })) });
    openMenu();
    expect(menuButtons().filter((row) => row.textContent?.includes("source-b"))).toHaveLength(0);
  });
  it("preserves the existing menu close and reasoning interaction", () => {
    const onReasoningChange = vi.fn();
    mount(composerState({ onReasoningChange }));
    openMenu();
    act(() =>
      menuButtons()
        .find((row) => row.textContent?.includes("reasoningOnMenu"))!
        .click(),
    );
    expect(onReasoningChange).toHaveBeenCalledWith(true);
    expect(container.querySelector('[aria-expanded="true"]')).toBeNull();
  });
});
