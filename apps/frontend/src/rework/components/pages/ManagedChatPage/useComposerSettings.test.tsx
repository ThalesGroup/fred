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
  scope = "",
}: {
  session: string | null;
  facts?: PreparationModels;
  controls: ChatControlDescriptor[];
  scope?: string;
}) {
  latest = useComposerSettings(session, controls, facts, scope);
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

const combinedSelection = { folderIds: ["folder"], documentIds: ["root-document"] };
function reload(session: string | null, scope = "") {
  act(() => root.unmount());
  root = createRoot(container);
  act(() => root.render(<Host session={session} facts={models} controls={[]} scope={scope} />));
}

describe("document selection ownership", () => {
  it("preserves a draft through refresh, session binding and conversation reload", () => {
    render(null);
    act(() => latest.setDocumentSelection(combinedSelection));
    reload(null);
    expect(latest.documentSelection).toEqual(combinedSelection);
    act(() => latest.bindSession("created"));
    reload("created");
    expect(latest.documentSelection).toEqual(combinedSelection);
    reload(null);
    expect(latest.documentSelection).toBeNull();
  });
  it("binds a selection made immediately before session allocation", () => {
    render(null);
    act(() => {
      latest.setDocumentSelection(combinedSelection);
      latest.bindSession("created");
    });
    reload("created");
    expect(latest.documentSelection).toEqual(combinedSelection);
  });
  it("persists an empty selection and reset as distinct states", () => {
    render("conversation");
    act(() => latest.setDocumentSelection({ folderIds: [], documentIds: [] }));
    reload("conversation");
    expect(latest.documentSelection).toEqual({ folderIds: [], documentIds: [] });
    act(() => latest.setDocumentSelection(null));
    reload("conversation");
    expect(latest.documentSelection).toBeNull();
  });
  it("restores each conversation's selection without leaking into another", () => {
    render("one");
    act(() => latest.setDocumentSelection(combinedSelection));
    render("two");
    act(() => latest.reset("two", []));
    expect(latest.documentSelection).toBeNull();
    render("one");
    act(() => latest.reset("one", []));
    expect(latest.documentSelection).toEqual(combinedSelection);
  });
  it("isolates agent and space changes, including a draft with no session id", () => {
    reload(null, "space-a:agent-a");
    act(() => latest.setDocumentSelection(combinedSelection));
    reload(null, "space-a:agent-b");
    expect(latest.documentSelection).toBeNull();
    reload(null, "space-b:agent-a");
    expect(latest.documentSelection).toBeNull();
    reload(null, "space-a:agent-a");
    expect(latest.documentSelection).toEqual(combinedSelection);
  });
  it("starts an explicit new conversation without reviving a previous draft", () => {
    render(null);
    act(() => latest.setDocumentSelection(combinedSelection));
    reload("existing");
    act(() => {
      latest.discardDraft();
      latest.reset(null, []);
    });
    expect(latest.documentSelection).toBeNull();
    reload(null);
    expect(latest.documentSelection).toBeNull();
  });
  it("keeps a selection through a fresh preparation response", () => {
    render(null);
    act(() => latest.setDocumentSelection(combinedSelection));
    render(null, models, [{ capability_id: "document_access", widget: "document_scope", params: {} }]);
    expect(latest.documentSelection).toEqual(combinedSelection);
  });
});

it("pins draft choices across preparation refresh and browser reload", () => {
  render(null);
  act(() => latest.acceptPreparation(4, []));
  act(() => latest.setDocumentSelection({ folderIds: ["library"], documentIds: ["document"] }));
  act(() => latest.setReasoning(true));
  expect(() => latest.acceptPreparation(5, [])).toThrow();
  expect(latest.agentConfigurationRevision).toBe(4);
  act(() => root.unmount());
  root = createRoot(container);
  render(null);
  expect(latest.agentConfigurationRevision).toBe(4);
  expect(latest.documentSelection).toEqual({ folderIds: ["library"], documentIds: ["document"] });
  expect(() => latest.acceptPreparation(5, [])).toThrow();
  act(() => latest.bindSession("saved"));
  act(() => latest.reset("saved", []));
  expect(latest.agentConfigurationRevision).toBe(4);
});

it("starts a new draft from current defaults without restoring prior choices", () => {
  render(null);
  act(() => latest.acceptPreparation(4, []));
  act(() => latest.setDocumentSelection({ folderIds: ["library"], documentIds: [] }));
  act(() => latest.setReasoning(true));
  act(() => latest.setChatProfileId(modelChoiceKey(first)));
  act(() => latest.bindSession("old"));
  act(() => {
    latest.discardDraft();
    latest.reset(null, []);
  });
  act(() =>
    latest.acceptPreparation(5, [
      { capability_id: "search", widget: "search_policy", params: { default: "semantic" } },
    ]),
  );
  expect(latest.agentConfigurationRevision).toBe(5);
  expect(latest.documentSelection).toBeNull();
  expect(latest.chatProfileId).toBeNull();
  expect(latest.reasoning).toBe(false);
  expect(latest.searchPolicy).toBe("semantic");
  act(() => latest.reset("old", []));
  expect(latest.agentConfigurationRevision).toBe(4);
  expect(latest.documentSelection?.folderIds).toEqual(["library"]);
});
