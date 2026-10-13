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
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal";
import type { CapabilityCatalogEntry } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { CreationAssistantDialog } from "./CreationAssistantDialog";
import promptEditorStyles from "@shared/molecules/PromptEditor/PromptEditor.module.css";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn(), showInfo: vi.fn() }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => (key.startsWith("capability.") ? `T:${key}` : key),
    i18n: { language: "fr-FR" },
  }),
}));

const generate = vi.fn();
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useDraftAgentMutation: () => [generate],
}));

const KEY = "rework.teams.formAgent.creationAssistant";
const REASONING = "rework.teams.formAgent.capabilities.packs.reasoning.title";
const CAPABILITIES = [
  { id: "team_wiki", name: "capability.team_wiki.name", description: "capability.team_wiki.description" },
  { id: "html_artifact", name: "capability.html_artifact.name", description: "capability.html_artifact.description" },
] as CapabilityCatalogEntry[];

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  generate.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.getElementById("modal-portal")?.remove();
});

function answer(result: Promise<unknown>) {
  generate.mockReturnValue({ unwrap: () => result, abort: vi.fn() });
}

const EMPTY = {
  systemPrompt: "",
  name: "",
  role: "",
  description: "",
  capabilityIds: [],
  capabilityConfigValues: {},
};

function renderDialog(props: Partial<Parameters<typeof CreationAssistantDialog>[0]> = {}) {
  const onApply = vi.fn();
  const onClose = vi.fn();
  act(() => {
    root.render(
      <CreationAssistantDialog
        open
        teamId="team-1"
        templateId="runtime:agent"
        capabilities={CAPABILITIES}
        hasPromptField
        offersReasoning={false}
        current={{ ...EMPTY, name: "RH" }}
        onApply={onApply}
        onClose={onClose}
        {...props}
      />,
    );
  });
  return { onApply, onClose };
}

const textarea = () => document.querySelector("textarea") as HTMLTextAreaElement;
const button = (label: string) =>
  [...document.querySelectorAll("button")].find((node) => node.textContent?.includes(label)) as HTMLButtonElement;

function type(value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(textarea(), value);
    textarea().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function click(label: string) {
  await act(async () => {
    button(label).click();
  });
}

const DRAFT = {
  name: "Assistant RH",
  role: "Répond aux questions RH",
  description: "Aide les salariés sur les congés.",
  system_prompt: "You answer HR questions.",
  capability_ids: ["team_wiki", "ghost"],
};

const tiles = () => [...document.querySelectorAll<HTMLButtonElement>('[role="checkbox"]')];
const tileFor = (text: string) => tiles().find((tile) => tile.textContent?.includes(text)) as HTMLButtonElement;
const stateOf = (text: string) => tileFor(text).getAttribute("aria-checked");

async function draftWith(result: unknown, props: Partial<Parameters<typeof CreationAssistantDialog>[0]> = {}) {
  answer(Promise.resolve(result));
  const handles = renderDialog(props);
  type("Answers HR questions");
  await click(`${KEY}.generate`);
  return handles;
}

describe("CreationAssistantDialog", () => {
  it("drafts from the description and applies every proposal by default", async () => {
    answer(Promise.resolve(DRAFT));
    // A name equal to the draft's replaces nothing, so no confirmation.
    const { onApply } = renderDialog({ current: { ...EMPTY, name: "Assistant RH" } });

    expect(button(`${KEY}.generate`).disabled).toBe(true);
    type("Answers HR questions");
    await click(`${KEY}.generate`);

    expect(generate).toHaveBeenCalledWith({
      teamId: "team-1",
      templateId: "runtime%3Aagent",
      agentDraftRequest: expect.objectContaining({
        description: "Answers HR questions",
        language: "fr",
        agent_name: "Assistant RH",
        capabilities: expect.arrayContaining([
          expect.objectContaining({ id: "team_wiki", name: "T:capability.team_wiki.name" }),
        ]),
      }),
    });
    const text = document.body.textContent ?? "";
    expect(text).toContain("You answer HR questions.");
    expect(text).toContain("Assistant RH");
    expect(text).toContain("T:capability.team_wiki.name");
    expect(text).not.toContain("ghost");
    expect(text).not.toContain("The wiki holds the HR policies.");
    // identity header, name, role, description, prompt header, capabilities header, team_wiki
    expect(tiles().map((tile) => tile.getAttribute("aria-checked"))).toEqual(Array(7).fill("true"));
    expect(document.querySelector('input[type="checkbox"]')).toBeNull();

    await click(`${KEY}.apply`);
    expect(onApply).toHaveBeenCalledWith({
      systemPrompt: "You answer HR questions.",
      name: "Assistant RH",
      role: "Répond aux questions RH",
      description: "Aide les salariés sur les congés.",
      capabilityIds: ["team_wiki"],
    });
  });

  it("applies only the ticked proposals", async () => {
    const { onApply } = await draftWith({ ...DRAFT, capability_ids: ["team_wiki", "html_artifact"] });

    await act(async () => tileFor(`${KEY}.fields.name`).click());
    await act(async () => tileFor("T:capability.team_wiki.name").click());
    expect(stateOf(`${KEY}.fields.name`)).toBe("false");
    expect(stateOf(`${KEY}.identityHeading`)).toBe("mixed");
    expect(stateOf(`${KEY}.capabilitiesHeading`)).toBe("mixed");

    // Retick then untick again: the tile toggles both ways.
    await act(async () => tileFor(`${KEY}.fields.role`).click());
    expect(stateOf(`${KEY}.fields.role`)).toBe("false");
    await act(async () => tileFor(`${KEY}.fields.role`).click());
    expect(stateOf(`${KEY}.fields.role`)).toBe("true");

    await click(`${KEY}.apply`);
    expect(onApply).toHaveBeenCalledWith({
      systemPrompt: "You answer HR questions.",
      role: "Répond aux questions RH",
      description: "Aide les salariés sur les congés.",
      capabilityIds: ["html_artifact"],
    });
  });

  it("disables Apply when nothing is ticked, the group box included", async () => {
    await draftWith({ ...DRAFT, name: null, role: null, description: null });

    await act(async () => tileFor(`${KEY}.promptHeading`).click());
    await act(async () => tileFor(`${KEY}.capabilitiesHeading`).click());

    expect(stateOf("T:capability.team_wiki.name")).toBe("false");
    expect(stateOf(`${KEY}.capabilitiesHeading`)).toBe("false");
    expect(button(`${KEY}.apply`).disabled).toBe(true);

    // The group tile ticks every recommendation back.
    await act(async () => tileFor(`${KEY}.capabilitiesHeading`).click());
    expect(stateOf("T:capability.team_wiki.name")).toBe("true");
    expect(button(`${KEY}.apply`).disabled).toBe(false);
  });

  it("selects or clears a whole section from its header", async () => {
    const { onApply } = await draftWith({ ...DRAFT, capability_ids: ["team_wiki", "html_artifact"] });

    // A partial identity header ticks every field back, then clears them all.
    await act(async () => tileFor(`${KEY}.fields.role`).click());
    await act(async () => tileFor(`${KEY}.identityHeading`).click());
    expect(stateOf(`${KEY}.identityHeading`)).toBe("true");
    expect(stateOf(`${KEY}.fields.role`)).toBe("true");
    await act(async () => tileFor(`${KEY}.identityHeading`).click());
    expect(stateOf(`${KEY}.identityHeading`)).toBe("false");
    expect(["name", "role", "description"].map((field) => stateOf(`${KEY}.fields.${field}`))).toEqual(
      Array(3).fill("false"),
    );

    // The prompt editor border follows its section's tick.
    const promptHighlighted = () =>
      document
        .querySelector(".cm-editor")!
        .closest(`.${promptEditorStyles.editor}`)!
        .classList.contains(promptEditorStyles.highlighted);
    expect(promptHighlighted()).toBe(true);
    await act(async () => tileFor(`${KEY}.promptHeading`).click());
    expect(stateOf(`${KEY}.promptHeading`)).toBe("false");
    expect(promptHighlighted()).toBe(false);
    await act(async () => tileFor(`${KEY}.promptHeading`).click());
    expect(stateOf(`${KEY}.promptHeading`)).toBe("true");

    await act(async () => tileFor(`${KEY}.capabilitiesHeading`).click());
    expect(stateOf("T:capability.html_artifact.name")).toBe("false");
    await act(async () => tileFor("T:capability.html_artifact.name").click());
    expect(stateOf(`${KEY}.capabilitiesHeading`)).toBe("mixed");

    await click(`${KEY}.apply`);
    expect(onApply).toHaveBeenCalledWith({
      systemPrompt: "You answer HR questions.",
      capabilityIds: ["html_artifact"],
    });
  });

  it("offers no prompt when the template has no prompt field", async () => {
    await draftWith(DRAFT, { hasPromptField: false });
    expect(document.body.textContent).not.toContain("You answer HR questions.");
  });

  it("asks before replacing values the user wrote, and cancelling keeps the review", async () => {
    const { onApply } = await draftWith(DRAFT, {
      current: { ...EMPTY, name: "Mine", systemPrompt: "Old prompt", capabilityIds: ["html_artifact"] },
    });

    await click(`${KEY}.apply`);
    expect(onApply).not.toHaveBeenCalled();
    const dialog = document.querySelector('[role="alertdialog"]') as HTMLElement;
    expect(dialog.textContent).toContain(`${KEY}.overwrite.items.name`);
    expect(dialog.textContent).toContain(`${KEY}.overwrite.items.systemPrompt`);
    expect(dialog.textContent).toContain(`${KEY}.overwrite.items.capabilities`);
    expect(dialog.textContent).not.toContain(`${KEY}.overwrite.items.role`);

    const cancel = [...dialog.querySelectorAll("button")].find((node) => node.textContent === "rework.cancel")!;
    await act(async () => cancel.click());
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    expect(onApply).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("You answer HR questions.");

    await click(`${KEY}.apply`);
    await click(`${KEY}.overwrite.confirm`);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it("closes only the confirmation on Escape", async () => {
    const { onApply, onClose } = await draftWith(DRAFT, { current: { ...EMPTY, name: "Mine" } });
    await click(`${KEY}.apply`);

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });

    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    expect(onApply).not.toHaveBeenCalled();
  });

  it("hands the keyboard to the overwrite confirmation", async () => {
    const { onApply, onClose } = await draftWith(DRAFT, { current: { ...EMPTY, name: "Mine" } });
    await click(`${KEY}.apply`);
    const dialog = document.querySelector('[role="alertdialog"]') as HTMLElement;
    const inDialog = (label: string) => [...dialog.querySelectorAll("button")].find((b) => b.textContent === label)!;
    expect(document.activeElement).toBe(inDialog("rework.cancel"));

    const shiftTab = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
    act(() => {
      document.activeElement!.dispatchEvent(shiftTab);
    });
    const replace = inDialog(`${KEY}.overwrite.confirm`);
    expect(document.activeElement).toBe(replace);
    // Enter on a focused button: the assistant's own Enter handler stays out, the browser clicks.
    act(() => {
      replace.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
    await act(async () => replace.click());
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("says when no capability is recommended", async () => {
    await draftWith({ ...DRAFT, capability_ids: [] });
    expect(document.body.textContent).toContain(`${KEY}.noCapabilities`);
    // The header stays a plain title: there is nothing to select.
    expect(document.body.textContent).toContain(`${KEY}.capabilitiesHeading`);
    expect(tileFor(`${KEY}.capabilitiesHeading`)).toBeUndefined();
  });

  it("proposes reasoning first in the capabilities column, ticked, and applies it", async () => {
    const { onApply } = await draftWith(
      { ...DRAFT, name: null, role: null, description: null },
      { offersReasoning: true },
    );
    const column = [...document.querySelectorAll("section")].find((node) =>
      node.textContent?.includes(`${KEY}.capabilitiesHeading`),
    )!;
    const columnTiles = [...column.querySelectorAll("li [role='checkbox'] > span:first-child")].map(
      (tile) => tile.textContent,
    );
    expect(columnTiles).toEqual([REASONING, "T:capability.team_wiki.name"]);
    expect(stateOf(REASONING)).toBe("true");

    await click(`${KEY}.apply`);
    expect(onApply).toHaveBeenCalledWith({
      systemPrompt: "You answer HR questions.",
      capabilityIds: ["team_wiki"],
      reasoning: true,
    });
  });

  it("leaves reasoning out once unticked, and counts it in the column header", async () => {
    const { onApply } = await draftWith(DRAFT, { offersReasoning: true, current: EMPTY });

    await act(async () => tileFor(REASONING).click());
    expect(stateOf(`${KEY}.capabilitiesHeading`)).toBe("mixed");
    await act(async () => tileFor(`${KEY}.capabilitiesHeading`).click());
    expect(stateOf(REASONING)).toBe("true");
    await act(async () => tileFor(`${KEY}.capabilitiesHeading`).click());
    expect(stateOf(REASONING)).toBe("false");
    expect(stateOf("T:capability.team_wiki.name")).toBe("false");

    await click(`${KEY}.apply`);
    expect(onApply).toHaveBeenCalledWith(expect.not.objectContaining({ reasoning: true }));
  });

  it("tells the user what to do in the review header only", async () => {
    renderDialog();
    expect(document.body.textContent).not.toContain(`${KEY}.selectHint`);
    await draftWith(DRAFT);
    expect(document.body.textContent).toContain(`${KEY}.selectHint`);
  });

  it("does not propose reasoning when the form does not offer it", async () => {
    await draftWith(DRAFT);
    expect(tileFor(REASONING)).toBeUndefined();
  });

  it("keeps a selectable reasoning column, without the empty hint, when no capability is recommended or available", async () => {
    await draftWith({ ...DRAFT, capability_ids: [] }, { offersReasoning: true });
    expect(document.body.textContent).not.toContain(`${KEY}.noCapabilities`);
    expect(stateOf(`${KEY}.capabilitiesHeading`)).toBe("true");

    act(() => root.unmount());
    root = createRoot(container);
    await draftWith(DRAFT, { offersReasoning: true, capabilities: [] });
    expect(document.body.textContent).not.toContain(`${KEY}.noCapabilities`);
    expect(stateOf(REASONING)).toBe("true");
    expect(stateOf(`${KEY}.capabilitiesHeading`)).toBe("true");
  });

  it("shows a friendly error and keeps the description for a retry", async () => {
    answer(Promise.reject({ status: 504, data: { detail: "timeout" } }));
    renderDialog();
    type("Answers HR questions");
    await click(`${KEY}.generate`);

    expect(document.body.textContent).toContain(`${KEY}.errors.timeout`);
    expect(textarea().value).toBe("Answers HR questions");
    expect(button(`${KEY}.generate`).disabled).toBe(false);
  });

  it("says the assistant is unavailable for a template the team can no longer enroll", async () => {
    answer(Promise.reject({ status: 404, data: { detail: "Template not found" } }));
    renderDialog();
    type("Answers HR questions");
    await click(`${KEY}.generate`);
    expect(document.body.textContent).toContain(`${KEY}.errors.unsupported`);
  });

  it("closes alone on Escape, leaving the agent form open", () => {
    const formClose = vi.fn();
    const dialogClose = vi.fn();
    act(() => {
      root.render(
        <FullPageModal isOpen onClose={formClose} id="agent-form">
          <CreationAssistantDialog
            open
            teamId="team-1"
            templateId="runtime:agent"
            capabilities={[]}
            hasPromptField
            offersReasoning
            current={EMPTY}
            onApply={vi.fn()}
            onClose={dialogClose}
          />
        </FullPageModal>,
      );
    });
    act(() => {
      textarea().dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(dialogClose).toHaveBeenCalledTimes(1);
    expect(formClose).not.toHaveBeenCalled();
  });
});
