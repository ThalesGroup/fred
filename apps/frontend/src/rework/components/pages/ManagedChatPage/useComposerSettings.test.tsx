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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatControlDescriptor, PreparationModels } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useComposerSettings } from "./useComposerSettings";
import { modelChoiceKey, parseModelChoice } from "../../../features/capabilities/modelChoice";

vi.mock("../../../../security/KeycloakService", () => ({ KeyCloakService: { GetSessionIdentity: () => "person-a" } }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
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

type Hook = ReturnType<typeof useComposerSettings>;
let latest: Hook;
let container: HTMLDivElement;
let root: Root;
function Host({
  session,
  facts,
  controls,
}: {
  session: string | null;
  facts?: PreparationModels;
  controls: ChatControlDescriptor[];
}) {
  latest = useComposerSettings(session, controls, facts);
  return null;
}
function render(
  session: string | null,
  facts: PreparationModels | undefined = models,
  controls: ChatControlDescriptor[] = [],
) {
  act(() => root.render(<Host session={session} facts={facts} controls={controls} />));
}
beforeEach(() => {
  sessionStorage.clear();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("Weaver composer choices (prepared, not executed in M5c)", () => {
  it("leaves implicit recommendation/default selection and M3 options to the server", () => {
    render(null);
    expect(latest.chatProfileId).toBeNull();
    expect(models.options).toEqual({ temperature: 0.4, max_tokens: 300 });
  });
  it("retains an explicit recommendation pick as an explicit choice", () => {
    render(null);
    act(() => latest.setChatProfileId(modelChoiceKey(first)));
    expect(parseModelChoice(latest.chatProfileId!)).toEqual(first);
  });
  it("preserves the composite choice through draft binding and reload", () => {
    render(null);
    act(() => latest.setChatProfileId(modelChoiceKey(second)));
    act(() => latest.bindSession("conversation"));
    act(() => root.unmount());
    root = createRoot(container);
    render("conversation");
    expect(parseModelChoice(latest.chatProfileId!)).toEqual(second);
  });
  it("does not drop a revoked, withdrawn or temporarily missing choice", () => {
    render("conversation");
    act(() => latest.setChatProfileId(modelChoiceKey(second)));
    render("conversation", { ...models, offers: [] });
    expect(latest.chatProfileId).toBe(modelChoiceKey(second));
    render("conversation", undefined);
    expect(latest.chatProfileId).toBe(modelChoiceKey(second));
  });
  it("cannot select a source that preparation does not offer for selection", () => {
    render(null, { ...models, offers: models.offers.map((offer) => ({ ...offer, selectable: false })) });
    act(() => latest.setChatProfileId(modelChoiceKey(second)));
    expect(latest.chatProfileId).toBeNull();
  });
  it("does not let a late descriptor refresh replace an explicit setting", () => {
    render(null);
    act(() => latest.setReasoning(false));
    render(null, models, [{ capability_id: "platform", widget: "reasoning_toggle", params: { default: true } }]);
    expect(latest.reasoning).toBe(false);
  });
  it("never translates an old profile or malformed composite into a model", () => {
    expect(() => parseModelChoice("chat.small")).toThrow();
    expect(() => parseModelChoice('["source"]')).toThrow();
  });
});
