// @vitest-environment jsdom
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

// The whole trigger, driven the way a user drives it: the real composer, the
// real menu, and the hook between them. Mounted together because the keyboard
// model only exists as the three of them — the field consumes a key only when
// the hook claims it, and the hook claims it only when the menu is open.

import { deleteCharBackward, undo, redo } from "@codemirror/commands";
import { EditorView } from "@codemirror/view";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandMenu } from "@shared/molecules/CommandMenu/CommandMenu";
import { RichInputField } from "@shared/molecules/RichInputField/RichInputField";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { useComposerCommands } from "./useComposerCommands";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

// The shape of `GET /teams/{id}/prompt-commands`: only invocable prompts, and
// already ordered by command. Excluding the ones without a command is the
// endpoint's job, proven by `test_prompt_commands_endpoint_lists_only_invocable_prompts`.
const PROMPTS = [
  { prompt_id: "p-search", name: "Recherche", command: "search", description: "Chercher", emoji: null },
  { prompt_id: "p-summary", name: "Résumé", command: "summary", description: "Résumer", emoji: null },
];

const PROMPT_TEXT: Record<string, string> = {
  "p-summary": "Résume le document en :",
  "p-search": "Cherche dans le corpus :",
};

const fetchPrompt = vi.fn();
let listResult: { data?: typeof PROMPTS; currentData?: typeof PROMPTS } = { data: PROMPTS };
let personalResult: typeof listResult = { data: [] };
const listCommands = vi.fn();

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetAgentInstanceSkillsQuery: () => ({ currentData: skillCatalog }),
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery: (
    args: { teamId: string },
    options: { skip: boolean },
  ) => {
    listCommands(args, options);
    const result = args.teamId === "personal-1" ? personalResult : listResult;
    return {
      data: result.data,
      currentData: options.skip ? undefined : "currentData" in result ? result.currentData : result.data,
    };
  },
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [fetchPrompt],
}));

let skillCatalog:
  | { supported: boolean; skills: { name: string; description: string; argument_hint?: string | null }[] }
  | undefined;
const onRunSkill = vi.fn();
const onSkillError = vi.fn();
const onRunCommand = vi.fn();
const onSend = vi.fn();
const onResolveError = vi.fn();
let renders: ReturnType<typeof useComposerCommands>[] = [];

function Host({
  inlineEditor = false,
  includePersonalCommands = false,
  teamId = "team-1",
  agentInstanceId = "instance-1",
  personalTeamId,
}: {
  inlineEditor?: boolean;
  includePersonalCommands?: boolean;
  teamId?: string;
  agentInstanceId?: string;
  personalTeamId?: string;
}) {
  const [input, setInput] = useState("");
  const commands = useComposerCommands({
    teamId,
    agentInstanceId,
    includePersonalCommands,
    personalTeamId,
    onRunSkill,
    onSkillError,
    input,
    setInput,
    onRunCommand,
    onSend,
    onResolveError,
  });
  renders.push(commands);
  return (
    <RichInputField
      value={commands.composerValue}
      onChange={commands.onComposerChange}
      onSend={commands.submit}
      commandTrigger={commands.trigger}
      aboveFieldSlot={commands.menu ? <CommandMenu {...commands.menu} /> : undefined}
      showSendButton
      inlineSkills={
        inlineEditor
          ? {
              promptToken: commands.selectedPrompt,
              tokens: commands.selectedSkills.map((token) => ({ ...token, onOpen: () => {} })),
            }
          : undefined
      }
    />
  );
}

// jsdom has no layout engine; interaction assertions do not use geometry.
beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
});
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  skillCatalog = undefined;
  listResult = { data: PROMPTS };
  personalResult = { data: [] };
  fetchPrompt.mockImplementation(({ promptId }: { promptId: string }) => ({
    unwrap: () => Promise.resolve({ id: promptId, text: PROMPT_TEXT[promptId] }),
  }));
  renders = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<Host />);
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  vi.clearAllMocks();
});

function textarea(): HTMLTextAreaElement {
  return container.querySelector("textarea") as HTMLTextAreaElement;
}

function type(text: string, caret = text.length) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(textarea(), text);
    textarea().setSelectionRange(caret, caret);
    textarea().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function press(key: string) {
  act(() => {
    textarea().dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

async function pressAsync(key: string) {
  await act(async () => {
    textarea().dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

function panel(): HTMLElement | null {
  return container.querySelector('[role="listbox"], [role="status"]');
}

function options(): HTMLElement[] {
  return Array.from(container.querySelectorAll('[role="option"]'));
}

function labels(): string[] {
  return options().map((option) => option.querySelector("[class*=rowHeading]")?.textContent ?? "");
}

function focusedLabel(): string | null {
  const active = textarea().getAttribute("aria-activedescendant");
  const option = options().find((candidate) => candidate.id === active);
  return option?.querySelector("[class*=rowHeading]")?.textContent ?? null;
}

describe("the command menu", () => {
  it("consumes Escape before an open skill preview, then lets the next Escape close that preview", () => {
    const onClose = vi.fn();
    act(() =>
      root.render(
        <>
          <Host />
          <InlineDrawer open layout="push" title="Skill preview" onClose={onClose} />
        </>,
      ),
    );
    type("/");
    expect(panel()).not.toBeNull();
    press("Escape");
    expect(panel()).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    press("Escape");
    expect(onClose).toHaveBeenCalledOnce();
  });
  it("keeps prompt arguments intact when the caret moves back to the command", async () => {
    type("/summary 33 lignes", 8);
    expect(panel()).toBeNull();
    press("Tab");
    expect(textarea().value).toBe("/summary 33 lignes");
    await pressAsync("Enter");
    expect(onRunCommand).toHaveBeenCalledWith({
      text: "Résume le document en :\n\n33 lignes",
      command: expect.objectContaining({
        command: "summary",
        appended_text: "33 lignes",
        prompt_id: "p-summary",
        prompt_name: "Résumé",
      }),
    });
  });
  it("opens on a slash under a titled section, with the best match focused", () => {
    type("/");

    expect(container.querySelector('[role="listbox"]')).not.toBeNull();
    expect(container.textContent).toContain("chatbot.commandMenu.promptsSection");
    expect(labels()).toEqual(["/search", "/summary"]);
    expect(focusedLabel()).toBe("/search");
  });

  it("offers every command the endpoint returns, in its order", () => {
    type("/");

    expect(options()).toHaveLength(2);
    expect(labels()).toEqual(["/search", "/summary"]);
  });

  it("filters on what is typed after the slash", () => {
    type("/");
    type("/su");

    expect(labels()).toEqual(["/summary"]);
    expect(focusedLabel()).toBe("/summary");
  });

  it("closes when the slash is deleted away", () => {
    type("/su");
    type("");

    expect(container.querySelector('[role="listbox"]')).toBeNull();
  });

  it("walks every entry with the arrows, wrapping at either end", () => {
    type("/");

    press("ArrowUp");
    expect(focusedLabel()).toBe("/summary");
    press("ArrowDown");
    expect(focusedLabel()).toBe("/search");
    press("ArrowDown");
    expect(focusedLabel()).toBe("/summary");
  });

  it("keeps the caret in the composer while the focus moves through the menu", () => {
    act(() => textarea().focus());
    type("/");
    press("ArrowDown");

    expect(document.activeElement).toBe(textarea());
    expect(textarea().getAttribute("aria-activedescendant")).toBe(options()[1].id);
    expect(options()[1].getAttribute("aria-selected")).toBe("true");
  });

  it("completes on Tab with a trailing space, closes, and sends nothing", () => {
    type("/su");
    press("Tab");

    expect(textarea().value).toBe("/summary ");
    expect(container.querySelector('[role="listbox"]')).toBeNull();
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("completes the same way on a pointer activation", () => {
    type("/");
    act(() => {
      options()[1].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
    });

    expect(textarea().value).toBe("/summary ");
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("closes when the composer loses focus, and comes back when it returns", () => {
    type("/su");
    expect(panel()).not.toBeNull();

    act(() => textarea().blur());
    expect(panel()).toBeNull();

    act(() => textarea().focus());
    expect(panel()).not.toBeNull();
    expect(labels()).toEqual(["/summary"]);
  });

  it("stays closed after Esc even when focus comes back", () => {
    type("/su");
    press("Escape");
    expect(panel()).toBeNull();

    act(() => textarea().blur());
    act(() => textarea().focus());
    expect(panel()).toBeNull();
  });

  it("closes on Esc, keeps what was typed, and gives Tab back", () => {
    type("/su");
    press("Escape");

    expect(container.querySelector('[role="listbox"]')).toBeNull();
    expect(textarea().value).toBe("/su");

    // The menu no longer claims Tab, so it does not complete the line.
    press("Tab");
    expect(textarea().value).toBe("/su");
  });

  // The list scrolls past 40vh and the caret never moves, so nothing brings the
  // focused row into view on its own — the arrows would walk over entries the
  // user cannot see.
  it("brings the focused entry into view as the focus moves", () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      value: scrollIntoView,
      configurable: true,
      writable: true,
    });

    type("/");
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });

    const callsAfterOpen = scrollIntoView.mock.calls.length;
    press("ArrowDown");
    expect(scrollIntoView.mock.calls.length).toBeGreaterThan(callsAfterOpen);
  });

  it("prefetches the focused entry once, and not again on the way back", () => {
    type("/");
    expect(fetchPrompt.mock.calls.map(([arg]) => arg.promptId)).toEqual(["p-search"]);

    press("ArrowDown");
    expect(fetchPrompt.mock.calls.map(([arg]) => arg.promptId)).toEqual(["p-search", "p-summary"]);

    press("ArrowUp");
    expect(fetchPrompt.mock.calls).toHaveLength(2);
  });
});

describe("with nothing to offer", () => {
  it("says the team holds no command rather than vanishing", () => {
    listResult = { data: [] };
    act(() => {
      root.render(<Host />);
    });

    type("/");
    expect(panel()?.getAttribute("role")).toBe("status");
    expect(container.textContent).toContain("chatbot.commandMenu.noneInTeam");
    expect(options()).toHaveLength(0);
  });

  it("distinguishes a query that matches none of the team's commands", () => {
    type("/zzz");

    expect(container.textContent).toContain("chatbot.commandMenu.noMatch");
    expect(container.textContent).not.toContain("chatbot.commandMenu.noneInTeam");
  });

  // The panel is shown but claims no key: the ordinary send has to still work.
  it("leaves Enter and Tab alone so an unmatched token is sent as typed", async () => {
    type("/zzz");
    press("Tab");
    expect(textarea().value).toBe("/zzz");

    await pressAsync("Enter");
    expect(onSend).toHaveBeenCalledOnce();
    expect(onRunCommand).not.toHaveBeenCalled();
  });

  it("still closes on Esc", () => {
    type("/zzz");
    expect(panel()).not.toBeNull();
    press("Escape");
    expect(panel()).toBeNull();
  });
});

describe("running a command", () => {
  it("sends the prompt behind the focused entry on Enter", async () => {
    type("/su");
    await pressAsync("Enter");

    expect(onRunCommand).toHaveBeenCalledWith({
      text: "Résume le document en :",
      command: expect.objectContaining({ command: "summary", prompt_id: "p-summary", prompt_name: "Résumé" }),
    });
    expect(onSend).not.toHaveBeenCalled();
    // The prompt's text never passed through the composer.
    expect(textarea().value).toBe("/su");
  });

  it("runs a completed command on submit with the menu closed", async () => {
    type("/su");
    press("Tab");
    expect(container.querySelector('[role="listbox"]')).toBeNull();
    await pressAsync("Enter");

    expect(onRunCommand).toHaveBeenCalledOnce();
    expect(onRunCommand.mock.calls[0][0].command.command).toBe("summary");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("appends trailing text and records it on the descriptor", async () => {
    type("/summary 33 lignes");
    await pressAsync("Enter");

    expect(onRunCommand).toHaveBeenCalledWith({
      text: "Résume le document en :\n\n33 lignes",
      command: expect.objectContaining({
        command: "summary",
        appended_text: "33 lignes",
        prompt_id: "p-summary",
        prompt_name: "Résumé",
      }),
    });
  });

  it("sends an unmatched token as ordinary text", async () => {
    type("/nosuchcommand");
    await pressAsync("Enter");

    expect(onSend).toHaveBeenCalledOnce();
    expect(onRunCommand).not.toHaveBeenCalled();
  });

  it("reports a prompt whose text cannot be read instead of sending a blank turn", async () => {
    fetchPrompt.mockImplementation(() => ({ unwrap: () => Promise.reject(new Error("boom")) }));
    type("/summary");
    await pressAsync("Enter");

    expect(onResolveError).toHaveBeenCalledOnce();
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("callback identity", () => {
  // Third time on this branch: a callback rebuilt per keystroke silently
  // defeats the memo of whatever it is handed to — here the menu, which
  // re-renders every row.
  it("holds across a keystroke render", () => {
    type("/");
    const first = renders[renders.length - 1];
    expect(first.menu).not.toBeNull();
    type("/s");
    const latest = renders[renders.length - 1];

    expect(latest.submit).toBe(first.submit);
    expect(latest.trigger.onQueryChange).toBe(first.trigger.onQueryChange);
    expect(latest.trigger.onKeyDown).toBe(first.trigger.onKeyDown);
    expect(latest.menu?.optionId).toBe(first.menu?.optionId);
    expect(latest.menu?.onActivate).toBe(first.menu?.onActivate);
    expect(latest.menu?.onFocusEntry).toBe(first.menu?.onFocusEntry);
  });
});

describe("platform skills", () => {
  function activateSkills(inlineEditor = false) {
    skillCatalog = {
      supported: true,
      skills: [
        { name: "compte-rendu", description: "Meeting minutes", argument_hint: "[meeting notes]" },
        { name: "review", description: "Review" },
      ],
    };
    act(() => root.render(<Host inlineEditor={inlineEditor} />));
    if (!inlineEditor) act(() => textarea().focus());
  }
  const selected = () =>
    renders[renders.length - 1].selectedSkills[0] ? { name: renders[renders.length - 1].selectedSkills[0].name } : null;

  it.each(["Tab", "Enter", "click"])("keeps both selected skills when adding the second with %s", async (method) => {
    activateSkills(true);
    cmType("Before /comp");
    cmPress("Tab");
    const prefix = cm().state.doc.toString() + "middle /rev";
    act(() =>
      cm().dispatch({
        changes: { from: cm().state.doc.length, insert: "middle /rev" },
        selection: { anchor: prefix.length },
      }),
    );
    expect(labels()).toEqual(["review"]);
    if (method === "click")
      act(() => options()[0].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true })));
    else cmPress(method);
    const draft = cm().state.doc.toString() + "After";
    act(() =>
      cm().dispatch({ changes: { from: cm().state.doc.length, insert: "After" }, selection: { anchor: draft.length } }),
    );
    expect(renders[renders.length - 1]!.selectedSkills.map((token) => token.name)).toEqual(["compte-rendu", "review"]);
    expect(container.querySelectorAll(".cm-content button")).toHaveLength(2);
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onRunSkill).toHaveBeenCalledWith({ text: draft, skills: [{ name: "compte-rendu" }, { name: "review" }] });
    expect(onRunCommand).not.toHaveBeenCalled();
  });
  it("deduplicates loads while displaying repeated invocations and keeps other tokens after deletion", () => {
    activateSkills(true);
    cmType("Before /review middle /compte-rendu after /review ");
    expect(container.querySelectorAll(".cm-content button")).toHaveLength(3);
    act(() => renders[renders.length - 1]!.submit());
    expect(onRunSkill).toHaveBeenLastCalledWith({
      text: "Before /review middle /compte-rendu after /review ",
      skills: [{ name: "review" }, { name: "compte-rendu" }],
    });
    act(() => cm().dispatch({ changes: { from: 7, to: 14 } }));
    expect(renders[renders.length - 1]!.selectedSkills.map((token) => token.name)).toEqual(["compte-rendu", "review"]);
    expect(cm().state.doc.toString()).toBe("Before  middle /compte-rendu after /review ");
  });
  it.each(["personal-1", "team-1"])(
    "assembles an inline prompt from %s with two skills and surrounding text",
    async (owner) => {
      activateSkills(true);
      personalResult = {
        data:
          owner === "personal-1"
            ? [{ prompt_id: "p-summary", command: "summary", name: "Résumé", description: "Résumer", emoji: null }]
            : [],
      };
      if (owner === "personal-1") listResult = { data: [] };
      act(() => root.render(<Host inlineEditor includePersonalCommands personalTeamId="personal-1" />));
      cmType("Before /review middle /su after /compte-rendu Notes");
      act(() => cm().dispatch({ selection: { anchor: 25 } }));
      cmPress("Tab");
      const draft = "Before /review middle /summary after /compte-rendu Notes";
      expect(cm().state.doc.toString()).toBe(draft);
      expect(container.querySelectorAll(".cm-content button")).toHaveLength(2);
      expect(container.querySelector(".cm-content [role=group]")).not.toBeNull();
      await act(async () => renders[renders.length - 1]!.submit());
      expect(fetchPrompt).toHaveBeenLastCalledWith({ teamId: owner, promptId: "p-summary" }, true);
      expect(onRunCommand).toHaveBeenCalledWith({
        text: "Before /review middle\n\nRésume le document en :\n\nafter /compte-rendu Notes",
        command: {
          command: "summary",
          prompt_id: "p-summary",
          prompt_name: "Résumé",
          appended_text: "Before /review middle\n\nafter /compte-rendu Notes",
          draft_text: draft,
          draft_command_offset: 22,
        },
        skills: [{ name: "review" }, { name: "compte-rendu" }],
      });
      expect(onSend).not.toHaveBeenCalled();
    },
  );
  it.each(["summary_long", "summary--long", "summary-", "--summary", "_"])(
    "invokes the valid prompt command %s inline with two skills",
    async (command) => {
      activateSkills(true);
      listResult = { data: [{ ...PROMPTS[1], command }] };
      act(() => root.render(<Host inlineEditor includePersonalCommands />));
      cmType(`Before /review middle /${command}`);
      expect(labels()).toEqual([`/${command}`]);
      cmPress("Tab");
      const suffix = "after /compte-rendu Notes";
      const draft = cm().state.doc.toString() + suffix;
      act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: suffix } }));
      expect(renders[renders.length - 1]!.selectedPrompt?.command).toBe(command);
      await act(async () => renders[renders.length - 1]!.submit());
      expect(onRunCommand).toHaveBeenCalledWith({
        text: "Before /review middle\n\nRésume le document en :\n\nafter /compte-rendu Notes",
        command: expect.objectContaining({ command, draft_text: draft, draft_command_offset: 22 }),
        skills: [{ name: "review" }, { name: "compte-rendu" }],
      });
    },
  );
  it("rejects the entire selection if a completed skill disappears during catalog refresh", () => {
    activateSkills(true);
    cmType("/rev");
    cmPress("Tab");
    act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: "/comp" }, selection: { anchor: 13 } }));
    cmPress("Tab");
    skillCatalog = { supported: true, skills: [{ name: "compte-rendu", description: "Meeting minutes" }] };
    act(() => root.render(<Host inlineEditor />));
    act(() => renders[renders.length - 1]!.submit());
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
    expect(onSkillError).toHaveBeenCalledWith("unavailable");
  });
  it("resolves available inline prompt commands outside ReAct with surrounding text", async () => {
    activateSkills(true);
    cmType("Explain how /summary works");
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onRunCommand).toHaveBeenCalledWith({
      text: "Explain how\n\nRésume le document en :\n\nworks",
      command: expect.objectContaining({
        command: "summary",
        draft_text: "Explain how /summary works",
        draft_command_offset: 12,
      }),
    });
    expect(onSend).not.toHaveBeenCalled();
  });
  it("retains typed selections immediately when the last delimiter is added before catalog refresh", () => {
    activateSkills(true);
    cmType("/review /compte-rendu");
    act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: " " } }));
    skillCatalog = { supported: true, skills: [{ name: "review", description: "Review" }] };
    act(() => root.render(<Host inlineEditor />));
    act(() => renders[renders.length - 1]!.submit());
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSkillError).toHaveBeenCalledWith("unavailable");
  });
  it.each([1, 2])("restores an explicit prompt homonym through grouped undo/redo (%s deletions)", async (deletions) => {
    listResult = {
      data: [{ prompt_id: "p-review", command: "review", name: "Prompt review", description: "Prompt", emoji: null }],
    };
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Prompt instructions" }) }));
    activateSkills(true);
    cmType("/rev");
    cmPress("Tab");
    act(() => cm().dispatch({ selection: { anchor: 7 } }));
    for (let index = 0; index < deletions; index++)
      act(() => {
        deleteCharBackward(cm());
      });
    expect(selected()).toBeNull();
    act(() => {
      undo(cm());
    });
    expect(cm().state.doc.toString()).toBe("/review ");
    expect(selected()).toBeNull();
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("p-review");
    expect(onRunSkill).not.toHaveBeenCalled();
    act(() => {
      redo(cm());
    });
    expect(cm().state.doc.toString()).toBe(deletions === 1 ? "/revie " : "/revi ");
    act(() => {
      undo(cm());
    });
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onRunCommand.mock.calls[1][0].command.prompt_id).toBe("p-review");
  });
  it("restores the personal prompt owner after invocation deletion and undo", async () => {
    activateSkills(true);
    personalResult = {
      data: [
        {
          prompt_id: "personal-summary",
          command: "summary",
          name: "Personal summary",
          description: "Private",
          emoji: null,
        },
      ],
    };
    fetchPrompt.mockImplementation(({ teamId }: { teamId: string }) => ({
      unwrap: async () => ({ text: teamId === "personal-1" ? "Personal instructions" : "Team instructions" }),
    }));
    act(() => root.render(<Host inlineEditor includePersonalCommands personalTeamId="personal-1" />));
    cmType("/su");
    cmPress("ArrowDown");
    cmPress("Tab");
    act(() => cm().dispatch({ selection: { anchor: 8 } }));
    act(() => {
      deleteCharBackward(cm());
    });
    act(() => {
      undo(cm());
    });
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("personal-summary");
    expect(fetchPrompt).toHaveBeenLastCalledWith({ teamId: "personal-1", promptId: "personal-summary" }, true);
  });
  it("preserves whitespace before a leading prompt outside ReAct", async () => {
    activateSkills();
    type("  /summary notes");
    await pressAsync("Enter");
    expect(onRunCommand).toHaveBeenCalledWith(expect.objectContaining({ text: "Résume le document en :\n\nnotes" }));
  });
  it("lists all runtime skills with descriptions, hints and platform identity", () => {
    activateSkills();
    type("/");
    expect(labels()).toEqual(["/search", "/summary", "compte-rendu [meeting notes]", "review"]);
    expect(options()[2].title).toBe("chatbot.skills.platformProvided");
    expect(options()[2].querySelector("[class*=customIcon]")).not.toBeNull();
    expect(options()[2].querySelector("em")?.textContent).toContain("Meeting minutes");
  });
  it.each(["Enter", "Tab"])("completes a direct skill query with %s without sending", (key) => {
    activateSkills();
    type("/comp");
    press(key);
    expect(textarea().value).toBe("/compte-rendu ");
    expect(selected()).toEqual({ name: "compte-rendu" });
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/compte-rendu ", skills: [{ name: "compte-rendu" }] });
  });
  it.each([
    { input: "/comp**Meeting**\nNotes", caret: 5, expected: "/compte-rendu **Meeting**\nNotes" },
    { input: "Meeting /comp", caret: 13, expected: "Meeting /compte-rendu " },
    { input: "Before /comp after\nNotes", caret: 12, expected: "Before /compte-rendu after\nNotes" },
  ])("preserves the invocation's position and surrounding text: $input", ({ input, caret, expected }) => {
    activateSkills();
    type(input, caret);
    act(() => options()[0].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true })));
    expect(textarea().value).toBe(expected);
    expect(textarea().selectionStart).toBe(expected.indexOf("/compte-rendu") + 14);
    expect(onRunSkill).not.toHaveBeenCalled();
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: expected, skills: [{ name: "compte-rendu" }] });
  });
  it.each(["/compte-rendu ", "Before /compte-rendu after", "Notes\n/compte-rendu "])(
    "recognizes a complete delimited invocation typed or pasted: %s",
    (text) => {
      activateSkills();
      type(text);
      expect(selected()).toEqual({ name: "compte-rendu" });
      expect(panel()).toBeNull();
      expect(onRunSkill).not.toHaveBeenCalled();
      act(() => renders[renders.length - 1].submit());
      expect(onRunSkill).toHaveBeenCalledWith({ text, skills: [{ name: "compte-rendu" }] });
    },
  );
  it("keeps a name editable until its delimiter and accepts a bare invocation on submit", () => {
    activateSkills();
    type("/compte-rendu");
    expect(selected()).toBeNull();
    act(() => renders[renders.length - 1].submit());
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/compte-rendu", skills: [{ name: "compte-rendu" }] });
    type("/compte-rendu ");
    expect(selected()).toEqual({ name: "compte-rendu" });
  });
  it("removes the import after any character of its name is deleted, preserving the request", () => {
    activateSkills();
    type("Before /compte-rendu after");
    type("Before /compte-rend after");
    expect(selected()).toBeNull();
    type("Before compte-rendu after");
    expect(selected()).toBeNull();
    press("Enter");
    expect(onSend).toHaveBeenCalledOnce();
    expect(onRunSkill).not.toHaveBeenCalled();
  });
  it("replaces the whole draft and its selection on full paste", () => {
    activateSkills();
    type("/compte-rendu Notes");
    type("/review Other notes");
    expect(selected()).toEqual({ name: "review" });
    type("Plain replacement");
    expect(selected()).toBeNull();
  });
  it("retains the import while editing just the surrounding request", () => {
    activateSkills();
    type("Before /compte-rendu First");
    type("New /compte-rendu Second\nAction");
    expect(selected()).toEqual({ name: "compte-rendu" });
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({
      text: "New /compte-rendu Second\nAction",
      skills: [{ name: "compte-rendu" }],
    });
  });
  it("does not recognize URLs, paths, partial names or unknown names as imports", () => {
    activateSkills();
    for (const text of ["https://host/compte-rendu ", "folder/compte-rendu ", "/compte-rendu-long ", "/missing "]) {
      type(text);
      expect(selected()).toBeNull();
    }
  });
  it("keeps prompt and skill homonyms independently selectable", async () => {
    listResult = {
      data: [
        ...PROMPTS,
        { prompt_id: "p-review", name: "Prompt review", command: "review", description: "Prompt", emoji: null },
      ],
    };
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Prompt instructions" }) }));
    activateSkills();
    type("/rev");
    press("Tab");
    expect(selected()).toBeNull();
    await pressAsync("Enter");
    expect(onRunCommand).toHaveBeenCalledOnce();
    expect(onRunSkill).not.toHaveBeenCalled();
    type("/rev");
    expect(labels()).toEqual(["/review", "review"]);
    press("ArrowDown");
    press("Tab");
    expect(selected()).toEqual({ name: "review" });
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/review ", skills: [{ name: "review" }] });
  });
  it.each([true, false])("preserves prompts that prefix skill (enabled: %s)", async (enabled) => {
    listResult = {
      data: [{ prompt_id: "p-ski", command: "ski", name: "Ski", description: "Plan a trip", emoji: null }],
    };
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Plan a ski trip" }) }));
    if (enabled) activateSkills();
    else act(() => root.render(<Host />));
    type("/ski");
    expect(labels()).toEqual(["/ski"]);
    await pressAsync("Enter");
    expect(onRunCommand).toHaveBeenCalledOnce();
    expect(onRunSkill).not.toHaveBeenCalled();
  });
  it("preserves skill names that prefix the old dispatcher", () => {
    activateSkills();
    skillCatalog = { supported: true, skills: [...skillCatalog!.skills, { name: "skillet", description: "Cooking" }] };
    act(() => root.render(<Host />));
    type("/ski");
    expect(labels()).toEqual(["skillet"]);
    press("Tab");
    expect(selected()).toEqual({ name: "skillet" });
  });
  it("does not use stale or unsupported catalogs", () => {
    activateSkills();
    type("/compte-rendu Notes");
    skillCatalog = undefined;
    act(() => root.render(<Host />));
    expect(selected()).toBeNull();
    expect(textarea().value).toBe("/compte-rendu Notes");
    press("Enter");
    expect(onRunSkill).not.toHaveBeenCalled();
    skillCatalog = { supported: false, skills: [{ name: "review", description: "Review" }] };
    act(() => root.render(<Host />));
    type("/");
    expect(labels()).toEqual(["/search", "/summary"]);
  });
  it("can still submit historical legacy copy payloads using canonical syntax", () => {
    activateSkills();
    type("/skill compte-rendu Notes");
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/compte-rendu Notes", skills: [{ name: "compte-rendu" }] });
  });
  it("keeps named legacy completion available without a dispatcher row", () => {
    activateSkills();
    type("/skill");
    expect(labels()).toEqual(["compte-rendu [meeting notes]", "review"]);
    press("Tab");
    expect(textarea().value).toBe("/compte-rendu ");
    expect(selected()).toEqual({ name: "compte-rendu" });
  });
  it("reports unavailable legacy names and a bare dispatcher", () => {
    activateSkills();
    type("/skill missing notes");
    press("Enter");
    expect(onSkillError).toHaveBeenLastCalledWith("unavailable");
    type("/skill");
    press("Escape");
    press("Enter");
    expect(onSkillError).toHaveBeenLastCalledWith("usage");
  });
  function cm() {
    return EditorView.findFromDOM(container.querySelector(".cm-content")!)!;
  }
  function cmType(text: string) {
    act(() => {
      cm().dispatch({ selection: { anchor: 0, head: cm().state.doc.length } });
      cm().contentDOM.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertFromPaste" }));
      cm().dispatch({
        changes: { from: 0, to: cm().state.doc.length, insert: text },
        selection: { anchor: text.length },
      });
    });
  }
  function cmPress(key: string) {
    act(() => cm().contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })));
  }

  it.each(["typed", "completed"])(
    "decorates a non-ReAct leading prompt with multiple skills when %s",
    async (method) => {
      activateSkills(true);
      act(() => cm().contentDOM.focus());
      const prefix = method === "typed" ? "  " : "";
      cmType(method === "typed" ? `${prefix}/summary ` : "/su");
      if (method === "completed") {
        expect(labels()).toEqual(["/summary"]);
        cmPress("Tab");
      }
      expect(cm().state.doc.toString()).toBe(`${prefix}/summary `);
      const append = "Before /compte-rendu middle /review after";
      act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: append } }));
      const prompt = container.querySelector<HTMLElement>("[class*=promptToken]");
      expect(prompt?.textContent).toBe("edit_notesummary");
      expect(prompt?.title).toContain("Résumé");
      expect(container.querySelectorAll('[aria-label="chatbot.skills.open"]')).toHaveLength(2);
      const draft = cm().state.doc.toString();
      await act(async () => renders[renders.length - 1].submit());
      expect(onRunCommand).toHaveBeenCalledWith({
        text: `Résume le document en :\n\n${append}`,
        command: expect.objectContaining({
          command: "summary",
          draft_text: draft,
          draft_command_offset: prefix.length,
        }),
        skills: [{ name: "compte-rendu" }, { name: "review" }],
      });
      cmType("Before /summary after");
      expect(container.querySelector("[class*=promptToken]")).not.toBeNull();
    },
  );

  it.each([false, true])(
    "keeps both completion orders with ReAct libraries enabled=%s",
    async (includePersonalCommands) => {
      activateSkills(true);
      act(() => root.render(<Host inlineEditor includePersonalCommands={includePersonalCommands} />));
      act(() => cm().contentDOM.focus());
      for (const promptFirst of [false, true]) {
        const before = promptFirst ? "Before" : "Before /review middle";
        cmType(`${before} /su`);
        expect(labels()).toEqual(["/summary"]);
        cmPress("Tab");
        expect(container.querySelector("[class*=promptToken]")?.textContent).toBe("edit_notesummary");
        for (const insert of promptFirst ? ["middle /rev", "after /comp"] : ["after /comp"]) {
          act(() => {
            const end = cm().state.doc.length;
            cm().dispatch({ changes: { from: end, insert }, selection: { anchor: end + insert.length } });
          });
          cmPress("Tab");
        }
        expect(container.querySelectorAll('[aria-label="chatbot.skills.open"]')).toHaveLength(2);
        expect(container.querySelector("[class*=promptToken]")).not.toBeNull();
        const draft = cm().state.doc.toString();
        const after = promptFirst ? "middle /review after /compte-rendu" : "after /compte-rendu";
        await act(async () => renders[renders.length - 1].submit());
        expect(onRunCommand).toHaveBeenLastCalledWith({
          text: `${before}\n\nRésume le document en :\n\n${after}`,
          command: expect.objectContaining({
            command: "summary",
            draft_text: draft,
            draft_command_offset: draft.indexOf("/summary"),
          }),
          skills: [{ name: "review" }, { name: "compte-rendu" }],
        });
      }
    },
  );

  it("places the caret after a completed prompt in the actual editor", () => {
    activateSkills(true);
    cmType("/su");
    cmPress("Tab");
    expect(cm().state.doc.toString()).toBe("/summary ");
    expect(cm().state.selection.main.head).toBe(9);
    act(() => cm().dispatch({ changes: { from: 9, insert: "Notes" }, selection: { anchor: 14 } }));
    expect(cm().state.doc.toString()).toBe("/summary Notes");
  });
  it("does not dispatch a homonymous prompt when Enter selects the exact skill row", () => {
    listResult = {
      data: [
        ...PROMPTS,
        { prompt_id: "p-review", name: "Prompt review", command: "review", description: "Prompt", emoji: null },
      ],
    };
    activateSkills(true);
    cmType("/review");
    cmPress("ArrowDown");
    cmPress("Enter");
    expect(selected()).toEqual({ name: "review" });
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onRunSkill).not.toHaveBeenCalled();
    cmPress("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/review ", skills: [{ name: "review" }] });
  });
  it("gives canonical pasted/typed homonyms skill identity unless the prompt was explicitly chosen", () => {
    listResult = {
      data: [
        ...PROMPTS,
        { prompt_id: "p-review", name: "Prompt review", command: "review", description: "Prompt", emoji: null },
      ],
    };
    activateSkills(true);
    cmType("/review Notes");
    expect(selected()).toEqual({ name: "review" });
    cmType("/review");
    cmPress("Tab");
    expect(selected()).toBeNull();
    // Native whole-draft replacement invalidates the explicit prompt identity.
    act(() => {
      cm().dispatch({ selection: { anchor: 0, head: cm().state.doc.length } });
      cm().contentDOM.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertFromPaste" }));
    });
    cmType("/review New notes");
    expect(selected()).toEqual({ name: "review" });
    cmPress("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/review New notes", skills: [{ name: "review" }] });
  });
  it("replacing a skill with its prompt homonym clears the earlier choice", async () => {
    listResult = {
      data: [
        ...PROMPTS,
        { prompt_id: "p-review", name: "Prompt review", command: "review", description: "Prompt", emoji: null },
      ],
    };
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Prompt instructions" }) }));
    activateSkills(true);
    cmType("/rev");
    cmPress("ArrowDown");
    cmPress("Tab");
    expect(selected()).toEqual({ name: "review" });
    cmType("/review");
    cmPress("Tab");
    expect(selected()).toBeNull();
    await act(async () => renders[renders.length - 1].submit());
    expect(onRunCommand).toHaveBeenCalledOnce();
    expect(onRunSkill).not.toHaveBeenCalled();
  });
  it("keeps a selected skill when only the surrounding request is deleted", () => {
    activateSkills(true);
    cmType("/rev");
    cmPress("Tab");
    act(() => cm().dispatch({ changes: { from: 8, insert: "Notes" } }));
    act(() => cm().dispatch({ changes: { from: 7, to: 13 } }));
    expect(cm().state.doc.toString()).toBe("/review");
    expect(selected()).toEqual({ name: "review" });
  });
  it("keeps a typed skill's identity over its prompt homonym when the request is deleted", async () => {
    listResult = {
      data: [
        ...PROMPTS,
        { prompt_id: "p-review", name: "Prompt review", command: "review", description: "Prompt", emoji: null },
      ],
    };
    activateSkills(true);
    cmType("/review Notes");
    act(() => cm().dispatch({ changes: { from: 7, to: 13 }, selection: { anchor: 7 } }));
    expect(selected()).toEqual({ name: "review" });
    await act(async () => renders[renders.length - 1].submit());
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/review", skills: [{ name: "review" }] });
    expect(onRunCommand).not.toHaveBeenCalled();
    // An invocation edit clears the prior identity and restores completion.
    act(() => cm().dispatch({ changes: { from: 6, to: 7 }, selection: { anchor: 6 } }));
    expect(selected()).toBeNull();
  });
  it("completes a prompt before existing request text without losing that text", () => {
    activateSkills(true);
    cmType("/s existing notes");
    act(() => cm().dispatch({ selection: { anchor: 2 } }));
    expect(labels()).toEqual(["/search", "/summary"]);
    cmPress("Tab");
    expect(cm().state.doc.toString()).toBe("/search existing notes");
    expect(cm().state.selection.main.head).toBe(8);
    expect(onRunCommand).not.toHaveBeenCalled();
  });
});

describe("ReAct personal and team prompt commands", () => {
  const personalPrompt = {
    prompt_id: "personal-summary",
    command: "summary",
    name: "Personal summary",
    description: "Private instructions",
    emoji: null,
  };
  const mountReact = () => {
    personalResult = { data: [personalPrompt] };
    act(() => root.render(<Host includePersonalCommands personalTeamId="personal-1" />));
  };
  it.each(["personal", "skill-homonym"])(
    "preserves the chosen %s prompt after a legacy skill prefix",
    async (variant) => {
      skillCatalog = {
        supported: true,
        skills: [
          { name: "review", description: "Review" },
          ...(variant === "skill-homonym" ? [{ name: "summary", description: "Summarize" }] : []),
        ],
      };
      personalResult = { data: [personalPrompt] };
      fetchPrompt.mockImplementation(({ teamId }: { teamId: string }) => ({
        unwrap: async () => ({ text: teamId === "personal-1" ? "Personal instructions" : "Team instructions" }),
      }));
      const react = variant === "personal";
      act(() => root.render(<Host inlineEditor includePersonalCommands={react} personalTeamId="personal-1" />));
      const view = EditorView.findFromDOM(container.querySelector(".cm-content")!)!;
      const draft = "  /skill review   /su";
      act(() => {
        view.contentDOM.focus();
        view.dispatch({ changes: { from: 0, insert: draft }, selection: { anchor: draft.length } });
      });
      if (react)
        act(() => view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
      act(() =>
        view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true })),
      );
      expect(renders[renders.length - 1].selectedPrompt?.promptId).toBe(react ? "personal-summary" : "p-summary");
      act(() => view.dispatch({ changes: { from: view.state.doc.length, insert: "Notes" } }));
      await act(async () => renders[renders.length - 1].submit());
      expect(onRunCommand).toHaveBeenCalledWith({
        text: `/review\n\n${react ? "Personal" : "Team"} instructions\n\nNotes`,
        command: expect.objectContaining({
          prompt_id: react ? "personal-summary" : "p-summary",
          draft_text: "/review /summary Notes",
          draft_command_offset: 8,
        }),
        skills: [{ name: "review" }],
      });
      expect(onRunSkill).not.toHaveBeenCalled();
    },
  );
  it.each(["team", "personal"])("decorates the completed %s prompt and sends that same selection", async (source) => {
    personalResult = { data: [personalPrompt] };
    fetchPrompt.mockImplementation(({ teamId }: { teamId: string }) => ({
      unwrap: async () => ({ text: teamId === "personal-1" ? "Personal instructions" : "Team instructions" }),
    }));
    act(() => root.render(<Host inlineEditor includePersonalCommands personalTeamId="personal-1" />));
    const view = EditorView.findFromDOM(container.querySelector(".cm-content")!)!;
    act(() => view.contentDOM.focus());
    act(() => view.dispatch({ changes: { from: 0, insert: "/su" }, selection: { anchor: 3 } }));
    expect(container.querySelector("[class*=promptToken]")).toBeNull();
    if (source === "personal")
      act(() => view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
    act(() =>
      view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true })),
    );
    const token = container.querySelector<HTMLElement>("[class*=promptToken]")!;
    expect(token).not.toBeNull();
    expect(token.textContent).toBe("edit_notesummary");
    expect(token.title).toContain(`chatbot.commandMenu.sources.${source}`);
    expect(token.querySelector('[aria-hidden="true"]')?.textContent).toBe("edit_note");
    expect(view.state.doc.toString()).toBe("/summary ");
    expect(onRunCommand).not.toHaveBeenCalled();
    act(() => view.dispatch({ changes: { from: 9, insert: "Notes" }, selection: { anchor: 14 } }));
    await act(async () =>
      view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })),
    );
    expect(onRunCommand.mock.calls[0][0].command).toMatchObject({
      prompt_id: source === "personal" ? "personal-summary" : "p-summary",
      appended_text: "Notes",
    });
    expect(onRunSkill).not.toHaveBeenCalled();
  });
  it("offers scoped prompts beside platform skills with visible source labels", () => {
    skillCatalog = { supported: true, skills: [{ name: "review", description: "Review" }] };
    mountReact();
    type("/");
    expect(labels()).toEqual(["/search", "/summary", "/summary", "review"]);
    expect(options()[0].querySelector("[class*=promptIcon]")?.textContent).toBe("edit_note");
    expect(options()[0].querySelector("em")?.textContent).toBe("Chercher");
    expect(options()[3].querySelector("[class*=promptIcon]")).toBeNull();
    expect(options()[3].querySelector("em")?.textContent).toBe("Review");
    expect(options().map((option) => option.querySelector("[class*=sourceLabel]")?.textContent)).toEqual([
      "chatbot.commandMenu.sources.team",
      "chatbot.commandMenu.sources.team",
      "chatbot.commandMenu.sources.personal",
      "chatbot.commandMenu.sources.platform",
    ]);
    press("ArrowUp");
    expect(focusedLabel()).toBe("review");
    press("ArrowDown");
    expect(focusedLabel()).toBe("/search");
  });
  it.each(["Tab", "pointer", "Enter"])(
    "runs the selected personal homonym through %s using its owning library",
    async (selection) => {
      fetchPrompt.mockImplementation(({ teamId }: { teamId: string }) => ({
        unwrap: async () => ({ text: teamId === "personal-1" ? "Personal instructions" : "Team instructions" }),
      }));
      mountReact();
      type("/su");
      press("ArrowDown");
      expect(fetchPrompt).toHaveBeenCalledWith({ teamId: "personal-1", promptId: "personal-summary" }, true);
      if (selection === "Enter") await pressAsync("Enter");
      else {
        if (selection === "Tab") press("Tab");
        else act(() => options()[1].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true })));
        expect(onRunCommand).not.toHaveBeenCalled();
        type("/summary additional notes");
        await pressAsync("Enter");
      }
      expect(onRunCommand).toHaveBeenCalledWith({
        text: selection === "Enter" ? "Personal instructions" : "Personal instructions\n\nadditional notes",
        command: expect.objectContaining({
          command: "summary",
          prompt_id: "personal-summary",
          prompt_name: "Personal summary",
          ...(selection === "Enter" ? {} : { appended_text: "additional notes" }),
        }),
      });
      expect(onRunSkill).not.toHaveBeenCalled();
    },
  );
  it("preserves team precedence for a typed command and uses a unique personal command", async () => {
    fetchPrompt.mockImplementation(({ teamId }: { teamId: string }) => ({
      unwrap: async () => ({ text: teamId === "personal-1" ? "Personal instructions" : "Team instructions" }),
    }));
    mountReact();
    type("/summary notes");
    await pressAsync("Enter");
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("p-summary");
    personalResult = { data: [{ ...personalPrompt, command: "private-summary" }] };
    act(() => root.render(<Host includePersonalCommands personalTeamId="personal-1" />));
    type("/private-summary notes");
    await pressAsync("Enter");
    expect(onRunCommand.mock.calls[1][0]).toMatchObject({
      text: "Personal instructions\n\nnotes",
      command: expect.objectContaining({ prompt_id: "personal-summary" }),
    });
  });
  it("keeps an explicit personal prompt homonym separate from its platform skill", async () => {
    skillCatalog = { supported: true, skills: [{ name: "summary", description: "Summarize" }] };
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Personal instructions" }) }));
    mountReact();
    type("/su");
    press("ArrowDown");
    press("Tab");
    expect(
      renders[renders.length - 1]?.selectedSkills[0]
        ? { name: renders[renders.length - 1].selectedSkills[0].name }
        : null,
    ).toBeNull();
    await pressAsync("Enter");
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("personal-summary");
    expect(onRunSkill).not.toHaveBeenCalled();
    type("plain text");
    type("/summary notes");
    expect(
      renders[renders.length - 1]?.selectedSkills[0]
        ? { name: renders[renders.length - 1].selectedSkills[0].name }
        : null,
    ).toEqual({ name: "summary" });
    expect(renders[renders.length - 1]?.selectedPrompt).toBeNull();
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/summary notes", skills: [{ name: "summary" }] });
  });
  it("does not replace a removed selected personal prompt with a team homonym", async () => {
    mountReact();
    type("/su");
    press("ArrowDown");
    press("Tab");
    personalResult = { data: [] };
    act(() => root.render(<Host includePersonalCommands personalTeamId="personal-1" />));
    await pressAsync("Enter");
    expect(renders[renders.length - 1]?.selectedPrompt).toBeNull();
    expect(onResolveError).toHaveBeenCalledOnce();
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });
  it("reports a failed personal read without sending the team homonym", async () => {
    mountReact();
    type("/su");
    press("ArrowDown");
    press("Tab");
    fetchPrompt.mockImplementation(() => ({
      unwrap: async () => {
        throw new Error("forbidden");
      },
    }));
    await pressAsync("Enter");
    expect(onResolveError).toHaveBeenCalledOnce();
    expect(onRunCommand).not.toHaveBeenCalled();
  });
  it("queries a personal chat once and labels its prompts as personal", () => {
    personalResult = { data: [personalPrompt] };
    act(() => root.render(<Host includePersonalCommands teamId="personal-1" personalTeamId="personal-1" />));
    type("/");
    expect(labels()).toEqual(["/summary"]);
    expect(options()[0].textContent).toContain("chatbot.commandMenu.sources.personal");
    const calls = listCommands.mock.calls.slice(-2);
    expect(calls).toEqual([
      [{ teamId: "personal-1" }, { skip: false }],
      [{ teamId: "personal-1" }, { skip: true }],
    ]);
  });
  it.each([false, true])("skips the personal source when unavailable (ReAct: %s)", (enabled) => {
    personalResult = { data: [personalPrompt] };
    act(() =>
      root.render(<Host includePersonalCommands={enabled} personalTeamId={enabled ? undefined : "personal-1"} />),
    );
    type("/");
    expect(labels()).toEqual(["/search", "/summary"]);
    expect(listCommands.mock.calls[listCommands.mock.calls.length - 1]?.[1]).toEqual({ skip: true });
  });
  it("ignores stale query data after changing prompt scope", () => {
    mountReact();
    listResult = { data: PROMPTS, currentData: undefined };
    personalResult = { data: [personalPrompt], currentData: undefined };
    act(() => root.render(<Host includePersonalCommands teamId="team-2" personalTeamId="personal-1" />));
    type("/");
    expect(labels()).toEqual([]);
  });
  it.each(["team", "agent", "category", "personal"])(
    "requires reselection after a completed personal command's scope changes: %s",
    async (variant) => {
      mountReact();
      type("/su");
      press("ArrowDown");
      press("Tab");
      act(() =>
        root.render(
          <Host
            includePersonalCommands={variant !== "category"}
            teamId={variant === "team" ? "team-2" : "team-1"}
            agentInstanceId={variant === "agent" ? "instance-2" : "instance-1"}
            personalTeamId={variant === "personal" ? undefined : "personal-1"}
          />,
        ),
      );
      await pressAsync("Enter");
      expect(onResolveError).toHaveBeenCalledOnce();
      expect(onRunCommand).not.toHaveBeenCalled();
      expect(onRunSkill).not.toHaveBeenCalled();
      expect(onSend).not.toHaveBeenCalled();
      // Editing and selecting a current prompt intentionally replaces the choice.
      type("/su");
      press("Tab");
      await pressAsync("Enter");
      expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("p-summary");
    },
  );
  it("waits for the team's catalog before resolving a typed personal fallback", async () => {
    mountReact();
    listResult = { data: PROMPTS, currentData: undefined };
    act(() => root.render(<Host includePersonalCommands personalTeamId="personal-1" />));
    type("/summary notes");
    await pressAsync("Enter");
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onResolveError).toHaveBeenCalledOnce();
    // Once resolved, the same typed command takes the team's match.
    listResult = { currentData: PROMPTS };
    act(() => root.render(<Host includePersonalCommands personalTeamId="personal-1" />));
    await pressAsync("Enter");
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("p-summary");
  });
  it("allows an explicit personal selection while the team catalog is pending", async () => {
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Personal instructions" }) }));
    mountReact();
    listResult = { currentData: undefined };
    act(() => root.render(<Host includePersonalCommands personalTeamId="personal-1" />));
    type("/su");
    press("Tab");
    await pressAsync("Enter");
    expect(onResolveError).not.toHaveBeenCalled();
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("personal-summary");
  });
  it.each(["team", "agent", "category", "personal"])(
    "discards a pending personal command after a scope change: %s",
    async (variant) => {
      mountReact();
      type("/su");
      press("ArrowDown");
      press("Tab");
      let resolve!: (detail: { text: string }) => void;
      fetchPrompt.mockImplementation(() => ({
        unwrap: () =>
          new Promise((done) => {
            resolve = done;
          }),
      }));
      press("Enter");
      act(() =>
        root.render(
          <Host
            includePersonalCommands={variant !== "category"}
            teamId={variant === "team" ? "team-2" : "team-1"}
            agentInstanceId={variant === "agent" ? "instance-2" : "instance-1"}
            personalTeamId={variant === "personal" ? undefined : "personal-1"}
          />,
        ),
      );
      // Returning to the original scope cannot resurrect its earlier request.
      act(() => root.render(<Host includePersonalCommands personalTeamId="personal-1" />));
      await act(async () => resolve({ text: "Late personal instructions" }));
      expect(onRunCommand).not.toHaveBeenCalled();
      expect(onResolveError).not.toHaveBeenCalled();
    },
  );
});
