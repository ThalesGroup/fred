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

// End to end through the real modal, form body and assistant dialog: what the
// user sees in the form fields after applying a draft. Only network hooks are mocked.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentTemplateSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const draftAgent = vi.fn();

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
    i18n: { language: "en" },
  }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn() }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn() }),
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "agent" }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useDraftAgentMutation: () => [draftAgent],
  useUsersByIdsQuery: () => ({ data: [] }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useDraftAgentMutation: () => [draftAgent],
  useUsersByIdsQuery: () => ({ data: [] }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi.ts", () => ({
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery: () => ({ data: [] }),
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery: () => ({ data: [] }),
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [vi.fn(), { isLoading: false }],
  usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation: () => [vi.fn()],
}));
// CodeMirror does not run under happy-dom; a textarea shows the same value.
vi.mock("@shared/molecules/PromptEditor/PromptEditor", () => ({
  PROMPT_EDITOR_ROWS: 15,
  PromptEditor: ({ value, onChange }: { value: string; onChange: (next: string) => void }) => (
    <textarea data-testid="prompt-editor" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock("@shared/molecules/PromptEditor/PromptEditor.tsx", () => ({
  PROMPT_EDITOR_ROWS: 15,
  PromptEditor: ({ value, onChange }: { value: string; onChange: (next: string) => void }) => (
    <textarea data-testid="prompt-editor" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

import AgentFormModal from "./AgentFormModal";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const KEY = "rework.teams.formAgent.creationAssistant";

const TEMPLATE = {
  template_id: "runtime:agent",
  display_name: "Template name",
  description: "Template description",
  reasoning_enabled: false,
  reasoning_default_on: false,
  default_capability_ids: [],
  available_capabilities: [
    { id: "team_wiki", name: "Wiki", description: "", route_base_url: "" },
    { id: "html_artifact", name: "HTML", description: "", route_base_url: "" },
  ],
  default_tuning_fields: [
    { key: "prompts.system", type: "prompt", title: "Prompt", default: "", ui: { group: "Prompts" } },
  ],
} as unknown as AgentTemplateSummary;

const DRAFT = {
  name: "Assistant RH",
  role: "Répond aux questions RH",
  description: "Aide les salariés sur les congés.",
  system_prompt: "You answer HR questions.",
  capability_ids: ["team_wiki"],
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  draftAgent.mockReset();
  draftAgent.mockReturnValue({ unwrap: () => Promise.resolve(DRAFT), abort: vi.fn() });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.getElementById("modal-portal")?.remove();
});

const buttonWith = (text: string) =>
  [...document.querySelectorAll("button")].find((node) => node.textContent?.includes(text)) as HTMLButtonElement;

async function click(text: string) {
  await act(async () => {
    buttonWith(text).click();
  });
}

function typeInto(node: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(node, value);
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

const inputLabelled = (label: string) => {
  const node = [...document.querySelectorAll("label")].find((l) => l.textContent?.startsWith(label));
  return document.getElementById(node!.htmlFor) as HTMLInputElement | HTMLTextAreaElement;
};

function renderModal() {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  act(() => {
    root.render(
      <AgentFormModal
        isOpen
        isSubmitting={false}
        mode="create"
        teamId="team-1"
        templates={[TEMPLATE]}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
  });
  return onSubmit;
}

async function applyDraftThroughDialog() {
  await click(`${KEY}.open`);
  const dialogs = document.querySelectorAll('[role="dialog"]');
  typeInto(dialogs[dialogs.length - 1].querySelector("textarea") as HTMLTextAreaElement, "An HR helper");
  await click(`${KEY}.generate`);
  await click(`${KEY}.apply`);
}

describe("AgentFormModal + creation assistant (real body and dialog)", () => {
  it("shows the applied draft in the visible form fields", async () => {
    renderModal();
    await click("Template name");
    expect(inputLabelled("rework.teams.formAgent.fields.name.label").value).toBe("Template name");

    await applyDraftThroughDialog();
    // Seeded values are not the user's: no overwrite confirmation, the dialog just closes.
    expect(document.body.textContent).not.toContain(`${KEY}.overwrite.title`);
    expect(buttonWith(`${KEY}.apply`)).toBeUndefined();

    expect(inputLabelled("rework.teams.formAgent.fields.name.label").value).toBe(DRAFT.name);
    expect(inputLabelled("rework.teams.formAgent.fields.role.label").value).toBe(DRAFT.role);
    expect(inputLabelled("rework.teams.formAgent.fields.description.label").value).toBe(DRAFT.description);

    await click("rework.teams.formAgent.sections.prompts");
    expect((document.querySelector('[data-testid="prompt-editor"]') as HTMLTextAreaElement).value).toBe(
      DRAFT.system_prompt,
    );
  });

  it("keeps reasoning on when capabilities are applied with it", async () => {
    const onSubmit = renderModal();
    await click("Template name");
    await applyDraftThroughDialog();

    await click("rework.teams.formAgent.sections.commitments");
    typeInto(
      inputLabelled("rework.teams.formAgent.fields.usageStatement.label") as HTMLTextAreaElement,
      "Internal use only.",
    );
    await click("rework.create");

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      displayName: DRAFT.name,
      reasoningEnabled: true,
      reasoningDefaultOn: true,
      selectedCapabilityIds: ["team_wiki"],
    });
  });
});
