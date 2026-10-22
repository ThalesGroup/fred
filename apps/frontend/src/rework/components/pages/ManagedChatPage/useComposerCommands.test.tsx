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

import { cursorCharLeft, cursorCharRight, deleteCharBackward, undo, redo } from "@codemirror/commands";
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
let commandsFetching = false;
let commandsFailed = false;
const listCommands = vi.fn();
// What a catalog answers when the hook asks it again; nothing by default.
const refetchCommands = vi.fn<(teamId: string) => Promise<{ data?: typeof PROMPTS }>>();
const refetchSkills = vi.fn<() => Promise<{ data?: typeof skillCatalog }>>();
const NO_SKILLS = { supported: false, skills: [] };
let skillsPending = false;
let skillsFailed = false;

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetAgentInstanceSkillsQuery: () => ({
    currentData: skillsPending ? undefined : (skillCatalog ?? NO_SKILLS),
    isError: skillsFailed,
    refetch: refetchSkills,
  }),
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery: (
    args: { teamId: string },
    options: { skip: boolean },
  ) => {
    listCommands(args, options);
    const result = args.teamId === "personal-1" ? personalResult : listResult;
    return {
      data: result.data,
      currentData: options.skip ? undefined : "currentData" in result ? result.currentData : result.data,
      isFetching: !options.skip && commandsFetching,
      isError: !options.skip && commandsFailed,
      refetch: () => refetchCommands(args.teamId),
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
let setHostInput: (value: string) => void;

function Host({
  inlineEditor = false,
  teamId = "team-1",
  agentInstanceId = "instance-1",
  personalTeamId,
}: {
  inlineEditor?: boolean;
  teamId?: string;
  agentInstanceId?: string;
  personalTeamId?: string;
}) {
  const [input, setInput] = useState("");
  setHostInput = setInput;
  const commands = useComposerCommands({
    teamId,
    agentInstanceId,
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
              promptTokens: commands.selectedPrompts,
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
  commandsFetching = false;
  commandsFailed = false;
  skillsPending = false;
  skillsFailed = false;
  refetchCommands.mockImplementation(async () => ({}));
  refetchSkills.mockImplementation(async () => ({}));
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
  return options().map((option) => option.querySelector("[class*=rowLabel]")?.textContent ?? "");
}

/** Each displayed section as its heading and the labels of its rows. */
function sections(): [string, string[]][] {
  return Array.from(container.querySelectorAll<HTMLElement>('[role="group"]')).map((group) => [
    document.getElementById(group.getAttribute("aria-labelledby") ?? "")?.textContent ?? "",
    Array.from(group.querySelectorAll('[role="option"]')).map(
      (option) => option.querySelector("[class*=rowLabel]")?.textContent ?? "",
    ),
  ]);
}

function focusedLabel(): string | null {
  const active = textarea().getAttribute("aria-activedescendant");
  const option = options().find((candidate) => candidate.id === active);
  return option?.querySelector("[class*=rowLabel]")?.textContent ?? null;
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
  it("opens on a slash under a titled section, with the first row focused", () => {
    type("/");

    expect(container.querySelector('[role="listbox"]')).not.toBeNull();
    expect(sections()).toEqual([["chatbot.commandMenu.sections.teamFallback", ["/search", "/summary"]]]);
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

  it("keeps the same menu mounted while the command is typed", () => {
    type("/");
    const list = container.querySelector('[role="listbox"]');
    type("/s");
    type("/su");

    expect(list).not.toBeNull();
    expect(container.querySelector('[role="listbox"]')).toBe(list);
    expect(labels()).toEqual(["/summary"]);
  });

  it("matches anywhere inside a command name, whatever the case, and nowhere else", () => {
    type("/MAR");
    expect(labels()).toEqual(["/summary"]);
    type("see /Ear");
    expect(labels()).toEqual(["/search"]);
    // "Recherche" and "Chercher" are the prompt's name and description.
    type("/cher");
    expect(labels()).toEqual([]);
    expect(container.textContent).toContain("chatbot.commandMenu.noMatch");
  });

  it("lists names starting with the typed text first in each section and focuses the first row", () => {
    listResult = {
      data: [
        { prompt_id: "t-1", name: "A", command: "pre-sum", description: null, emoji: null },
        { prompt_id: "t-2", name: "B", command: "big-sum", description: null, emoji: null },
      ] as unknown as typeof PROMPTS,
    };
    personalResult = {
      data: [
        { prompt_id: "p-1", name: "C", command: "my-sum", description: null, emoji: null },
        { prompt_id: "p-2", name: "D", command: "sum-up", description: null, emoji: null },
        { prompt_id: "p-3", name: "E", command: "sum", description: null, emoji: null },
      ] as unknown as typeof PROMPTS,
    };
    skillCatalog = {
      supported: true,
      skills: [
        { name: "resume", description: "Resume" },
        { name: "summarize", description: "Summarize" },
      ],
    };
    act(() => root.render(<Host personalTeamId="personal-1" />));
    type("/sum");

    expect(sections()).toEqual([
      ["chatbot.commandMenu.sections.teamFallback", ["/pre-sum", "/big-sum"]],
      ["chatbot.commandMenu.sections.personal", ["/sum-up", "/sum", "/my-sum"]],
      ["chatbot.commandMenu.sections.platform", ["/summarize", "/resume"]],
    ]);
    // The first row keeps the focus even though a later section starts with the text.
    expect(focusedLabel()).toBe("/pre-sum");
  });

  it("closes when the slash is deleted away", () => {
    type("/su");
    type("");

    expect(container.querySelector('[role="listbox"]')).toBeNull();
  });

  it("walks every entry with the arrows and stops at either end", () => {
    type("/");

    press("ArrowUp");
    expect(focusedLabel()).toBe("/search");
    press("ArrowDown");
    expect(focusedLabel()).toBe("/summary");
    press("ArrowDown");
    expect(focusedLabel()).toBe("/summary");
    press("ArrowUp");
    expect(focusedLabel()).toBe("/search");
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

  it("replaces the whole name under the caret, whatever its case", () => {
    type("hello /MAR", 9);
    expect(labels()).toEqual(["/summary"]);
    press("Tab");
    expect(textarea().value).toBe("hello /summary ");
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

  it("reopens after Esc once the query is edited, even back to the same text", () => {
    type("/su");
    press("Escape");
    type("/s");
    expect(panel()).not.toBeNull();

    type("/su");
    expect(panel()).not.toBeNull();
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

  it("shows the section heading with the first entry, back at the top of the list", () => {
    const scrolled: Element[] = [];
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      value(this: Element) {
        scrolled.push(this);
      },
      configurable: true,
      writable: true,
    });
    type("/");
    const list = container.querySelector<HTMLElement>('[role="listbox"]')!;
    press("ArrowDown");
    list.scrollTop = 40;
    scrolled.length = 0;

    press("ArrowUp");

    expect(scrolled.map((element) => element.getAttribute("role"))).toEqual([null, "option"]);
    expect(list.scrollTop).toBe(0);
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
  it("says there is no command yet rather than vanishing", () => {
    listResult = { data: [] };
    act(() => {
      root.render(<Host />);
    });

    type("/");
    expect(panel()?.getAttribute("role")).toBe("status");
    expect(container.textContent).toContain("chatbot.commandMenu.none");
    expect(options()).toHaveLength(0);
  });

  it("says the commands are loading instead of claiming there is none", () => {
    listResult = { currentData: undefined };
    commandsFetching = true;
    act(() => root.render(<Host personalTeamId="personal-1" />));

    type("/");
    expect(panel()?.getAttribute("role")).toBe("status");
    expect(container.textContent).toContain("chatbot.commandMenu.loading");
    expect(container.textContent).not.toContain("chatbot.commandMenu.none");
    type("/zzz");
    expect(container.textContent).toContain("chatbot.commandMenu.loading");
    expect(container.textContent).not.toContain("chatbot.commandMenu.noMatch");

    // What has already answered is offered while the rest loads.
    personalResult = { data: [PROMPTS[1]] };
    act(() => root.render(<Host personalTeamId="personal-1" />));
    type("/");
    expect(labels()).toEqual(["/summary"]);

    listResult = { data: [] };
    personalResult = { data: [] };
    commandsFetching = false;
    act(() => root.render(<Host personalTeamId="personal-1" />));
    expect(container.textContent).toContain("chatbot.commandMenu.none");
  });

  it("distinguishes a query that matches none of the team's commands", () => {
    type("/zzz");

    expect(panel()?.textContent).toBe("chatbot.commandMenu.noMatch");
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
  it("inserts the focused prompt on Enter like Tab, and sends it on the second Enter", async () => {
    type("/su");
    await pressAsync("Enter");

    expect(textarea().value).toBe("/summary ");
    expect(container.querySelector('[role="listbox"]')).toBeNull();
    expect(fetchPrompt).toHaveBeenCalledTimes(1);
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();

    await pressAsync("Enter");
    expect(onRunCommand).toHaveBeenCalledWith({
      text: "Résume le document en :",
      command: {
        command: "summary",
        prompt_id: "p-summary",
        prompt_name: "Résumé",
        draft_text: "/summary ",
        draft_command_offset: 0,
        prompts: [
          {
            command: "summary",
            prompt_id: "p-summary",
            prompt_name: "Résumé",
            draft_offset: 0,
            text_offset: 0,
            text_length: 23,
          },
        ],
      },
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends the same turn whether the row was picked with Enter or with Tab", async () => {
    type("Avant /su");
    await pressAsync("Enter");
    await pressAsync("Enter");
    type("");
    type("Avant /su");
    press("Tab");
    await pressAsync("Enter");

    expect(onRunCommand).toHaveBeenCalledTimes(2);
    expect(onRunCommand.mock.calls[1]).toEqual(onRunCommand.mock.calls[0]);
    expect(onRunCommand.mock.calls[0][0]).toMatchObject({
      text: "Avant\n\nRésume le document en :",
      command: { prompt_id: "p-summary", appended_text: "Avant", draft_command_offset: 6 },
    });
  });

  it("leaves Shift+Enter to the composer while the menu is open", () => {
    type("/su");
    act(() => {
      textarea().dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true, cancelable: true }),
      );
    });

    expect(textarea().value).toBe("/su");
    expect(onRunCommand).not.toHaveBeenCalled();
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
    expect(onResolveError).not.toHaveBeenCalled();
    await pressAsync("Enter");

    expect(onResolveError.mock.calls).toEqual([["unreadable", "summary"]]);
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it.each([403, 404])("says the command must be chosen again when its prompt answers %s", async (status) => {
    type("/su");
    press("Tab");
    fetchPrompt.mockImplementation(() => ({ unwrap: () => Promise.reject({ status, data: {} }) }));
    await pressAsync("Enter");

    expect(onResolveError.mock.calls).toEqual([["stale", "summary"]]);
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
        { name: "meeting-minutes", description: "Meeting minutes", argument_hint: "[meeting notes]" },
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
    cmType("Before /meet");
    cmPress("Tab");
    const prefix = cm().state.doc.toString() + "middle /rev";
    act(() =>
      cm().dispatch({
        changes: { from: cm().state.doc.length, insert: "middle /rev" },
        selection: { anchor: prefix.length },
      }),
    );
    expect(labels()).toEqual(["/review"]);
    if (method === "click")
      act(() => options()[0].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true })));
    else cmPress(method);
    const draft = cm().state.doc.toString() + "After";
    act(() =>
      cm().dispatch({ changes: { from: cm().state.doc.length, insert: "After" }, selection: { anchor: draft.length } }),
    );
    expect(renders[renders.length - 1]!.selectedSkills.map((token) => token.name)).toEqual([
      "meeting-minutes",
      "review",
    ]);
    expect(container.querySelectorAll(".cm-content button")).toHaveLength(2);
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onRunSkill).toHaveBeenCalledWith({ text: draft, skills: [{ name: "meeting-minutes" }, { name: "review" }] });
    expect(onRunCommand).not.toHaveBeenCalled();
  });
  it("deduplicates loads while displaying repeated invocations and keeps other tokens after deletion", () => {
    activateSkills(true);
    cmType("Before /review middle /meeting-minutes after /review ");
    expect(container.querySelectorAll(".cm-content button")).toHaveLength(3);
    act(() => renders[renders.length - 1]!.submit());
    expect(onRunSkill).toHaveBeenLastCalledWith({
      text: "Before /review middle /meeting-minutes after /review ",
      skills: [{ name: "review" }, { name: "meeting-minutes" }],
    });
    act(() => cm().dispatch({ changes: { from: 7, to: 14 } }));
    expect(renders[renders.length - 1]!.selectedSkills.map((token) => token.name)).toEqual([
      "meeting-minutes",
      "review",
    ]);
    expect(cm().state.doc.toString()).toBe("Before  middle /meeting-minutes after /review ");
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
      act(() => root.render(<Host inlineEditor personalTeamId="personal-1" />));
      cmType("Before /review middle /su after /meeting-minutes Notes");
      act(() => cm().dispatch({ selection: { anchor: 25 } }));
      cmPress("Tab");
      const draft = "Before /review middle /summary after /meeting-minutes Notes";
      expect(cm().state.doc.toString()).toBe(draft);
      expect(container.querySelectorAll(".cm-content button")).toHaveLength(2);
      expect(container.querySelector(".cm-content [role=group]")).not.toBeNull();
      await act(async () => renders[renders.length - 1]!.submit());
      expect(fetchPrompt).toHaveBeenLastCalledWith({ teamId: owner, promptId: "p-summary" }, false);
      expect(onRunCommand).toHaveBeenCalledWith({
        text: "Before /review middle\n\nRésume le document en :\n\nafter /meeting-minutes Notes",
        command: {
          command: "summary",
          prompt_id: "p-summary",
          prompt_name: "Résumé",
          appended_text: "Before /review middle\n\nafter /meeting-minutes Notes",
          draft_text: draft,
          draft_command_offset: 22,
          prompts: [
            {
              command: "summary",
              prompt_id: "p-summary",
              prompt_name: "Résumé",
              draft_offset: 22,
              text_offset: 23,
              text_length: 23,
            },
          ],
        },
        skills: [{ name: "review" }, { name: "meeting-minutes" }],
      });
      expect(onSend).not.toHaveBeenCalled();
    },
  );
  it.each(["summary_long", "summary--long", "summary-", "--summary", "_"])(
    "invokes the valid prompt command %s inline with two skills",
    async (command) => {
      activateSkills(true);
      listResult = { data: [{ ...PROMPTS[1], command }] };
      act(() => root.render(<Host inlineEditor />));
      cmType(`Before /review middle /${command}`);
      expect(labels()).toEqual([`/${command}`]);
      cmPress("Tab");
      const suffix = "after /meeting-minutes Notes";
      const draft = cm().state.doc.toString() + suffix;
      act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: suffix } }));
      expect(renders[renders.length - 1]!.selectedPrompts[0]?.command).toBe(command);
      await act(async () => renders[renders.length - 1]!.submit());
      expect(onRunCommand).toHaveBeenCalledWith({
        text: "Before /review middle\n\nRésume le document en :\n\nafter /meeting-minutes Notes",
        command: expect.objectContaining({ command, draft_text: draft, draft_command_offset: 22 }),
        skills: [{ name: "review" }, { name: "meeting-minutes" }],
      });
    },
  );
  it("rejects the entire selection if a completed skill disappears during catalog refresh", () => {
    activateSkills(true);
    cmType("/rev");
    cmPress("Tab");
    act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: "/meet" }, selection: { anchor: 13 } }));
    cmPress("Tab");
    skillCatalog = { supported: true, skills: [{ name: "meeting-minutes", description: "Meeting minutes" }] };
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
    cmType("/review /meeting-minutes");
    act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: " " } }));
    skillCatalog = { supported: true, skills: [{ name: "review", description: "Review" }] };
    act(() => root.render(<Host inlineEditor />));
    act(() => renders[renders.length - 1]!.submit());
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSkillError).toHaveBeenCalledWith("unavailable");
  });
  it("restores an explicit prompt homonym through undo/redo of its whole deletion", async () => {
    listResult = {
      data: [{ prompt_id: "p-review", command: "review", name: "Prompt review", description: "Prompt", emoji: null }],
    };
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Prompt instructions" }) }));
    activateSkills(true);
    cmType("/rev");
    cmPress("Tab");
    act(() => cm().dispatch({ selection: { anchor: 7 } }));
    cmPress("Backspace");
    expect(cm().state.doc.toString()).toBe("");
    expect(renders[renders.length - 1].menu).toBeNull();
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
    expect(cm().state.doc.toString()).toBe("");
    act(() => {
      undo(cm());
    });
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onRunCommand.mock.calls[1][0].command.prompt_id).toBe("p-review");
  });
  // One transaction per character, as the keyboard does, never a menu pick.
  function cmTypeByHand(text: string) {
    for (const character of text)
      act(() => {
        const head = cm().state.selection.main.head;
        cm().dispatch({
          changes: { from: head, insert: character },
          selection: { anchor: head + 1 },
          userEvent: "input.type",
        });
      });
  }
  const promptShown = () => container.querySelector("[data-kind=prompt]") !== null;
  const skillShown = () => container.querySelector("[data-kind=skill]") !== null;
  it.each([
    { kind: "skill", name: "review", shown: skillShown },
    { kind: "prompt", name: "summary", shown: promptShown },
  ])("removes a hand-typed $kind token as one block", ({ name, shown }) => {
    activateSkills(true);
    act(() => cm().contentDOM.focus());
    const token = `/${name}`;
    for (const [before, after] of [
      ["", ""],
      ["", "notes"],
      ["Before ", ""],
      ["Before ", "after"],
    ]) {
      cmTypeByHand(before + token);
      // Still a name being typed: no token, and Backspace edits one character.
      expect(shown()).toBe(false);
      cmPress("Backspace");
      expect(cm().state.doc.toString()).toBe(before + token.slice(0, -1));
      cmTypeByHand(token.slice(-1) + " " + after);
      expect(shown()).toBe(true);
      const to = (before + token).length;

      // Backspace from the end: the text after, the space, then the whole token.
      for (let index = 0; index < after.length + 1; index++) cmPress("Backspace");
      expect(cm().state.doc.toString()).toBe(before + token);
      expect(shown()).toBe(true);
      act(() => {
        cursorCharLeft(cm());
      });
      expect(cm().state.selection.main.head).toBe(before.length);
      act(() => {
        cursorCharRight(cm());
      });
      expect(cm().state.selection.main.head).toBe(to);
      cmPress("Backspace");
      expect(cm().state.doc.toString()).toBe(before);
      expect(shown()).toBe(false);
      expect(renders[renders.length - 1].menu).toBeNull();

      // Delete from just before it, with the same draft typed again.
      cmTypeByHand(token + " " + after);
      act(() => cm().dispatch({ selection: { anchor: before.length } }));
      cmPress("Delete");
      expect(cm().state.doc.toString()).toBe(before + after);
      expect(shown()).toBe(false);
      act(() => cm().dispatch({ changes: { from: 0, to: cm().state.doc.length }, selection: { anchor: 0 } }));
    }
  });
  it.each(["picked", "typed"])("keeps the menu closed on a %s prompt token left at the end of the draft", (origin) => {
    activateSkills(true);
    act(() => cm().contentDOM.focus());
    if (origin === "picked") {
      cmTypeByHand("/su");
      cmPress("Tab");
    } else cmTypeByHand("/summary ");
    expect(cm().state.doc.toString()).toBe("/summary ");
    const menu = () => renders[renders.length - 1].menu;

    cmPress("Backspace");
    expect(cm().state.doc.toString()).toBe("/summary");
    expect(promptShown()).toBe(true);
    expect(menu()).toBeNull();

    cmTypeByHand(" ");
    expect(menu()).toBeNull();
    cmTypeByHand("notes");
    expect(promptShown()).toBe(true);
    expect(menu()).toBeNull();

    // A new slash further on is a new command: the menu is for it alone.
    cmTypeByHand(" /re");
    expect(labels()).toEqual(["/review"]);
    expect(promptShown()).toBe(true);
  });
  it("deletes one of two adjacent tokens without touching the other", () => {
    activateSkills(true);
    cmType("/review /meeting-minutes notes");
    const names = () => renders[renders.length - 1].selectedSkills.map((token) => token.name);
    expect(names()).toEqual(["review", "meeting-minutes"]);
    act(() => cm().dispatch({ selection: { anchor: "/review ".length } }));
    cmPress("Delete");
    expect(cm().state.doc.toString()).toBe("/review notes");
    expect(names()).toEqual(["review"]);
    expect(renders[renders.length - 1].menu).toBeNull();
    act(() => cm().dispatch({ selection: { anchor: "/review".length } }));
    cmPress("Backspace");
    expect(cm().state.doc.toString()).toBe("notes");
    expect(names()).toEqual([]);
    expect(renders[renders.length - 1].menu).toBeNull();
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
    act(() => root.render(<Host inlineEditor personalTeamId="personal-1" />));
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
    expect(fetchPrompt).toHaveBeenLastCalledWith({ teamId: "personal-1", promptId: "personal-summary" }, false);
  });
  it("preserves whitespace before a leading prompt outside ReAct", async () => {
    activateSkills();
    type("  /summary notes");
    await pressAsync("Enter");
    expect(onRunCommand).toHaveBeenCalledWith(expect.objectContaining({ text: "Résume le document en :\n\nnotes" }));
  });
  it("lists all runtime skills with descriptions and platform identity, without their argument hint", () => {
    activateSkills();
    type("/");
    expect(labels()).toEqual(["/search", "/summary", "/meeting-minutes", "/review"]);
    // The native tooltip gives the full description, which the row may cut.
    expect(options()[2].title).toBe("Meeting minutes");
    expect(options()[2].querySelector("[class*=customIcon]")).not.toBeNull();
    expect(options()[2].querySelector("em")?.textContent).toContain("Meeting minutes");
  });
  it.each(["Enter", "Tab"])("completes a direct skill query with %s without sending", (key) => {
    activateSkills();
    type("/meet");
    press(key);
    expect(textarea().value).toBe("/meeting-minutes ");
    expect(selected()).toEqual({ name: "meeting-minutes" });
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/meeting-minutes ", skills: [{ name: "meeting-minutes" }] });
  });
  it.each([
    { input: "/meet**Meeting**\nNotes", caret: 5, expected: "/meeting-minutes **Meeting**\nNotes" },
    { input: "Meeting /meet", caret: 13, expected: "Meeting /meeting-minutes " },
    { input: "Before /meet after\nNotes", caret: 12, expected: "Before /meeting-minutes after\nNotes" },
  ])("preserves the invocation's position and surrounding text: $input", ({ input, caret, expected }) => {
    activateSkills();
    type(input, caret);
    act(() => options()[0].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true })));
    expect(textarea().value).toBe(expected);
    expect(textarea().selectionStart).toBe(expected.indexOf("/meeting-minutes") + "/meeting-minutes ".length);
    expect(onRunSkill).not.toHaveBeenCalled();
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: expected, skills: [{ name: "meeting-minutes" }] });
  });
  it.each(["/meeting-minutes ", "Before /meeting-minutes after", "Notes\n/meeting-minutes "])(
    "recognizes a complete delimited invocation typed or pasted: %s",
    (text) => {
      activateSkills();
      type(text);
      expect(selected()).toEqual({ name: "meeting-minutes" });
      expect(panel()).toBeNull();
      expect(onRunSkill).not.toHaveBeenCalled();
      act(() => renders[renders.length - 1].submit());
      expect(onRunSkill).toHaveBeenCalledWith({ text, skills: [{ name: "meeting-minutes" }] });
    },
  );
  it("keeps a name editable until its delimiter and accepts a bare invocation on submit", () => {
    activateSkills();
    type("/meeting-minutes");
    expect(selected()).toBeNull();
    act(() => renders[renders.length - 1].submit());
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/meeting-minutes", skills: [{ name: "meeting-minutes" }] });
    type("/meeting-minutes ");
    expect(selected()).toEqual({ name: "meeting-minutes" });
  });
  it("removes the import after any character of its name is deleted, preserving the request", () => {
    activateSkills();
    type("Before /meeting-minutes after");
    type("Before /meeting-minute after");
    expect(selected()).toBeNull();
    type("Before meeting-minutes after");
    expect(selected()).toBeNull();
    press("Enter");
    expect(onSend).toHaveBeenCalledOnce();
    expect(onRunSkill).not.toHaveBeenCalled();
  });
  it("replaces the whole draft and its selection on full paste", () => {
    activateSkills();
    type("/meeting-minutes Notes");
    type("/review Other notes");
    expect(selected()).toEqual({ name: "review" });
    type("Plain replacement");
    expect(selected()).toBeNull();
  });
  it("retains the import while editing just the surrounding request", () => {
    activateSkills();
    type("Before /meeting-minutes First");
    type("New /meeting-minutes Second\nAction");
    expect(selected()).toEqual({ name: "meeting-minutes" });
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({
      text: "New /meeting-minutes Second\nAction",
      skills: [{ name: "meeting-minutes" }],
    });
  });
  it("does not recognize URLs, paths, partial names or unknown names as imports", () => {
    activateSkills();
    for (const text of [
      "https://host/meeting-minutes ",
      "folder/meeting-minutes ",
      "/meeting-minutes-long ",
      "/missing ",
    ]) {
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
    expect(labels()).toEqual(["/review", "/review"]);
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
    expect(onRunCommand).not.toHaveBeenCalled();
    await pressAsync("Enter");
    expect(onRunCommand).toHaveBeenCalledOnce();
    expect(onRunSkill).not.toHaveBeenCalled();
  });
  it("preserves skill names that prefix the old dispatcher", () => {
    activateSkills();
    skillCatalog = { supported: true, skills: [...skillCatalog!.skills, { name: "skillet", description: "Cooking" }] };
    act(() => root.render(<Host />));
    type("/ski");
    expect(labels()).toEqual(["/skillet"]);
    press("Tab");
    expect(selected()).toEqual({ name: "skillet" });
  });
  it("does not use stale or unsupported catalogs", () => {
    activateSkills();
    type("/meeting-minutes Notes");
    skillCatalog = undefined;
    act(() => root.render(<Host />));
    expect(selected()).toBeNull();
    expect(textarea().value).toBe("/meeting-minutes Notes");
    press("Enter");
    expect(onRunSkill).not.toHaveBeenCalled();
    skillCatalog = { supported: false, skills: [{ name: "review", description: "Review" }] };
    act(() => root.render(<Host />));
    type("/");
    expect(labels()).toEqual(["/search", "/summary"]);
  });
  it("can still submit historical legacy copy payloads using canonical syntax", () => {
    activateSkills();
    type("/skill meeting-minutes Notes");
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/meeting-minutes Notes", skills: [{ name: "meeting-minutes" }] });
  });
  it("keeps named legacy completion available without a dispatcher row", () => {
    activateSkills();
    type("/skill");
    expect(labels()).toEqual(["/meeting-minutes", "/review"]);
    press("Tab");
    expect(textarea().value).toBe("/meeting-minutes ");
    expect(selected()).toEqual({ name: "meeting-minutes" });
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
      const append = "Before /meeting-minutes middle /review after";
      act(() => cm().dispatch({ changes: { from: cm().state.doc.length, insert: append } }));
      const prompt = container.querySelector<HTMLElement>("[data-kind=prompt]");
      expect(prompt?.textContent).toBe("edit_note/summary");
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
        skills: [{ name: "meeting-minutes" }, { name: "review" }],
      });
      cmType("Before /summary after");
      expect(container.querySelector("[data-kind=prompt]")).not.toBeNull();
    },
  );

  it.each([undefined, "personal-1"])(
    "keeps both completion orders with the personal space %s",
    async (personalTeamId) => {
      activateSkills(true);
      act(() => root.render(<Host inlineEditor personalTeamId={personalTeamId} />));
      act(() => cm().contentDOM.focus());
      for (const promptFirst of [false, true]) {
        const before = promptFirst ? "Before" : "Before /review middle";
        cmType(`${before} /su`);
        expect(labels()).toEqual(["/summary"]);
        cmPress("Tab");
        expect(container.querySelector("[data-kind=prompt]")?.textContent).toBe("edit_note/summary");
        for (const insert of promptFirst ? ["middle /rev", "after /meet"] : ["after /meet"]) {
          act(() => {
            const end = cm().state.doc.length;
            cm().dispatch({ changes: { from: end, insert }, selection: { anchor: end + insert.length } });
          });
          cmPress("Tab");
        }
        expect(container.querySelectorAll('[aria-label="chatbot.skills.open"]')).toHaveLength(2);
        expect(container.querySelector("[data-kind=prompt]")).not.toBeNull();
        const draft = cm().state.doc.toString();
        const after = promptFirst ? "middle /review after /meeting-minutes" : "after /meeting-minutes";
        await act(async () => renders[renders.length - 1].submit());
        expect(onRunCommand).toHaveBeenLastCalledWith({
          text: `${before}\n\nRésume le document en :\n\n${after}`,
          command: expect.objectContaining({
            command: "summary",
            draft_text: draft,
            draft_command_offset: draft.indexOf("/summary"),
          }),
          skills: [{ name: "review" }, { name: "meeting-minutes" }],
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
    expect(labels()).toEqual(["/search", "/summary", "/meeting-minutes"]);
    cmPress("Tab");
    expect(cm().state.doc.toString()).toBe("/search existing notes");
    expect(cm().state.selection.main.head).toBe(8);
    expect(onRunCommand).not.toHaveBeenCalled();
  });
});

describe("personal and team prompt commands", () => {
  const personalPrompt = {
    prompt_id: "personal-summary",
    command: "summary",
    name: "Personal summary",
    description: "Private instructions",
    emoji: null,
  };
  const mountReact = () => {
    personalResult = { data: [personalPrompt] };
    act(() => root.render(<Host personalTeamId="personal-1" />));
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
      act(() => root.render(<Host inlineEditor personalTeamId={react ? "personal-1" : undefined} />));
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
      expect(renders[renders.length - 1].selectedPrompts[0]?.promptId).toBe(react ? "personal-summary" : "p-summary");
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
    act(() => root.render(<Host inlineEditor personalTeamId="personal-1" />));
    const view = EditorView.findFromDOM(container.querySelector(".cm-content")!)!;
    act(() => view.contentDOM.focus());
    act(() => view.dispatch({ changes: { from: 0, insert: "/su" }, selection: { anchor: 3 } }));
    expect(container.querySelector("[data-kind=prompt]")).toBeNull();
    if (source === "personal")
      act(() => view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
    act(() =>
      view.contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true })),
    );
    const token = container.querySelector<HTMLElement>("[data-kind=prompt]")!;
    expect(token).not.toBeNull();
    expect(token.textContent).toBe("edit_note/summary");
    expect(token.title.split("\n")[1]).toBe(
      `chatbot.commandMenu.sections.${source === "team" ? "teamFallback" : "personal"}`,
    );
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
  it("lists team prompts, personal prompts and platform skills under their own section", () => {
    skillCatalog = { supported: true, skills: [{ name: "review", description: "Review" }] };
    mountReact();
    type("/");
    expect(labels()).toEqual(["/search", "/summary", "/summary", "/review"]);
    expect(options()[0].querySelector("[class*=rowIcon]")?.textContent).toBe("edit_note");
    expect(options()[0].querySelector("em")?.textContent).toBe("Chercher");
    expect(options()[3].querySelector("[class*=rowIcon]")?.textContent).not.toBe("edit_note");
    expect(options()[3].querySelector("em")?.textContent).toBe("Review");
    expect(sections()).toEqual([
      ["chatbot.commandMenu.sections.teamFallback", ["/search", "/summary"]],
      ["chatbot.commandMenu.sections.personal", ["/summary"]],
      ["chatbot.commandMenu.sections.platform", ["/review"]],
    ]);
    expect(container.textContent).not.toContain("chatbot.commandMenu.sources.");
    type("/sea");
    expect(sections()).toEqual([["chatbot.commandMenu.sections.teamFallback", ["/search"]]]);
    // The arrows cross section boundaries and stop on the last row.
    type("/");
    for (let step = 0; step < 4; step += 1) press("ArrowDown");
    expect(focusedLabel()).toBe("/review");
    press("ArrowUp");
    expect(options()[2].getAttribute("aria-selected")).toBe("true");
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
      if (selection === "pointer")
        act(() => options()[1].dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true })));
      else await pressAsync(selection);
      expect(onRunCommand).not.toHaveBeenCalled();
      type("/summary additional notes");
      await pressAsync("Enter");
      expect(onRunCommand).toHaveBeenCalledWith({
        text: "Personal instructions\n\nadditional notes",
        command: expect.objectContaining({
          command: "summary",
          prompt_id: "personal-summary",
          prompt_name: "Personal summary",
          appended_text: "additional notes",
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
    act(() => root.render(<Host personalTeamId="personal-1" />));
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
    expect(renders[renders.length - 1]?.selectedPrompts).toEqual([]);
    press("Enter");
    expect(onRunSkill).toHaveBeenCalledWith({ text: "/summary notes", skills: [{ name: "summary" }] });
  });
  it("does not replace a removed selected personal prompt with a team homonym", async () => {
    mountReact();
    type("/su");
    press("ArrowDown");
    press("Tab");
    personalResult = { data: [] };
    act(() => root.render(<Host personalTeamId="personal-1" />));
    await pressAsync("Enter");
    expect(renders[renders.length - 1]?.selectedPrompts).toEqual([]);
    expect(onResolveError.mock.calls).toEqual([["stale", "summary"]]);
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
    expect(onResolveError.mock.calls).toEqual([["unreadable", "summary"]]);
    expect(onRunCommand).not.toHaveBeenCalled();
  });
  it("queries a personal chat once and lists its prompts in the personal section only", () => {
    personalResult = { data: [personalPrompt] };
    act(() => root.render(<Host teamId="personal-1" personalTeamId="personal-1" />));
    type("/");
    expect(labels()).toEqual(["/summary"]);
    expect(sections()).toEqual([["chatbot.commandMenu.sections.personal", ["/summary"]]]);
    const calls = listCommands.mock.calls.slice(-2);
    expect(calls).toEqual([
      [{ teamId: "personal-1" }, { skip: false }],
      [{ teamId: "personal-1" }, { skip: true }],
    ]);
  });
  it("skips the personal source while the personal space is unknown", () => {
    personalResult = { data: [personalPrompt] };
    act(() => root.render(<Host />));
    type("/");
    expect(labels()).toEqual(["/search", "/summary"]);
    expect(listCommands.mock.calls[listCommands.mock.calls.length - 1]?.[1]).toEqual({ skip: true });
  });
  it("ignores stale query data after changing prompt scope", () => {
    mountReact();
    listResult = { data: PROMPTS, currentData: undefined };
    personalResult = { data: [personalPrompt], currentData: undefined };
    act(() => root.render(<Host teamId="team-2" personalTeamId="personal-1" />));
    type("/");
    expect(labels()).toEqual([]);
  });
  it.each(["team", "agent", "personal"])(
    "requires reselection after a completed personal command's scope changes: %s",
    async (variant) => {
      mountReact();
      type("/su");
      press("ArrowDown");
      press("Tab");
      act(() =>
        root.render(
          <Host
            teamId={variant === "team" ? "team-2" : "team-1"}
            agentInstanceId={variant === "agent" ? "instance-2" : "instance-1"}
            personalTeamId={variant === "personal" ? undefined : "personal-1"}
          />,
        ),
      );
      await pressAsync("Enter");
      expect(onResolveError.mock.calls).toEqual([["stale", "summary"]]);
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
    refetchCommands.mockImplementation(async () => ({ data: PROMPTS }));
    act(() => root.render(<Host personalTeamId="personal-1" />));
    type("/summary notes");
    await pressAsync("Enter");
    // The typed command takes the team's match, not the personal one already there.
    expect(refetchCommands.mock.calls).toEqual([["team-1"]]);
    expect(onResolveError).not.toHaveBeenCalled();
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("p-summary");
  });
  it("allows an explicit personal selection while the team catalog is pending", async () => {
    fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Personal instructions" }) }));
    mountReact();
    listResult = { currentData: undefined };
    act(() => root.render(<Host personalTeamId="personal-1" />));
    type("/su");
    press("Tab");
    await pressAsync("Enter");
    expect(onResolveError).not.toHaveBeenCalled();
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("personal-summary");
  });
  it.each(["team", "agent", "personal"])(
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
            teamId={variant === "team" ? "team-2" : "team-1"}
            agentInstanceId={variant === "agent" ? "instance-2" : "instance-1"}
            personalTeamId={variant === "personal" ? undefined : "personal-1"}
          />,
        ),
      );
      // Returning to the original scope cannot resurrect its earlier request.
      act(() => root.render(<Host personalTeamId="personal-1" />));
      await act(async () => resolve({ text: "Late personal instructions" }));
      expect(onRunCommand).not.toHaveBeenCalled();
      expect(onResolveError).not.toHaveBeenCalled();
    },
  );
});

describe("sending while a catalog has not answered", () => {
  const TONE = { prompt_id: "p-tone", command: "tone", name: "Ton", description: "Ton formel", emoji: null };
  /** A catalog asked again, answering when the test says so. */
  function pending<T>() {
    let answer!: (result: { data?: T }) => void;
    const promise = new Promise<{ data?: T }>((done) => {
      answer = done;
    });
    return { promise, answer: (data?: T) => act(async () => answer({ data })) };
  }
  const nothingSent = () => {
    expect(onSend).not.toHaveBeenCalled();
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onResolveError).not.toHaveBeenCalled();
  };

  it("waits for the personal catalog, then expands a command only it holds", async () => {
    personalResult = { currentData: undefined };
    const personal = pending<typeof PROMPTS>();
    refetchCommands.mockImplementation(() => personal.promise);
    fetchPrompt.mockImplementation(({ promptId }: { promptId: string }) => ({
      unwrap: async () => ({ text: `Text of ${promptId}` }),
    }));
    act(() => root.render(<Host personalTeamId="personal-1" />));
    type("/summary and /tone now");
    await pressAsync("Enter");
    expect(refetchCommands.mock.calls).toEqual([["personal-1"]]);
    nothingSent();

    await personal.answer([TONE]);
    expect(
      onRunCommand.mock.calls[0][0].command.prompts.map((entry: { prompt_id: string }) => entry.prompt_id),
    ).toEqual(["p-summary", "p-tone"]);
    expect(onSend).not.toHaveBeenCalled();
  });

  it("waits for both prompt catalogs right after the page loads", async () => {
    listResult = { currentData: undefined };
    personalResult = { currentData: undefined };
    commandsFetching = true;
    const team = pending<typeof PROMPTS>();
    const personal = pending<typeof PROMPTS>();
    refetchCommands.mockImplementation((teamId) => (teamId === "team-1" ? team.promise : personal.promise));
    act(() => root.render(<Host personalTeamId="personal-1" />));
    type("/summary report");
    await pressAsync("Enter");
    // A second Enter while waiting sends nothing more.
    await pressAsync("Enter");
    await personal.answer([]);
    nothingSent();

    await team.answer(PROMPTS);
    expect(onRunCommand).toHaveBeenCalledOnce();
    expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("p-summary");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("waits for the skill catalog, then runs the typed skill", async () => {
    skillsPending = true;
    const skills = pending<typeof skillCatalog>();
    refetchSkills.mockImplementation(() => skills.promise);
    act(() => root.render(<Host />));
    type("/review notes");
    await pressAsync("Enter");
    nothingSent();

    await skills.answer({ supported: true, skills: [{ name: "review", description: "Review" }] });
    expect(onRunSkill).toHaveBeenCalledExactlyOnceWith({ text: "/review notes", skills: [{ name: "review" }] });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends a word no catalog knows as plain text once they have answered, with no error", async () => {
    listResult = { currentData: undefined };
    refetchCommands.mockImplementation(async () => ({ data: PROMPTS }));
    act(() => root.render(<Host />));
    type("see /etc and /nosuch please");
    await pressAsync("Enter");
    expect(onSend).toHaveBeenCalledOnce();
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onResolveError).not.toHaveBeenCalled();
  });

  it("does not wait for a draft with no command-shaped word", async () => {
    listResult = { currentData: undefined };
    skillsPending = true;
    act(() => root.render(<Host />));
    type("see /etc/hosts and a/b");
    press("Enter");
    expect(onSend).toHaveBeenCalledOnce();
    expect(refetchCommands).not.toHaveBeenCalled();
    expect(refetchSkills).not.toHaveBeenCalled();
  });

  it("sends nothing when the conversation changes while waiting", async () => {
    listResult = { currentData: undefined };
    const team = pending<typeof PROMPTS>();
    refetchCommands.mockImplementation(() => team.promise);
    act(() => root.render(<Host />));
    type("/summary report");
    await pressAsync("Enter");
    act(() => root.render(<Host teamId="team-2" />));
    await team.answer(PROMPTS);
    nothingSent();
  });

  describe("after a catalog failed", () => {
    beforeEach(() => {
      listResult = { currentData: undefined };
      commandsFailed = true;
      act(() => root.render(<Host />));
    });

    it("asks it once more on submit and sends when it answers", async () => {
      refetchCommands.mockImplementation(async () => ({ data: PROMPTS }));
      type("/summary report");
      press("Escape");
      refetchCommands.mockClear();
      await pressAsync("Enter");
      expect(refetchCommands.mock.calls).toEqual([["team-1"]]);
      expect(onResolveError).not.toHaveBeenCalled();
      expect(onRunCommand.mock.calls[0][0].command.prompt_id).toBe("p-summary");
    });

    it("holds the message back when it fails again, and names the typed command", async () => {
      type("hello /summary report");
      await pressAsync("Enter");
      expect(onResolveError.mock.calls).toEqual([["unreadable", "summary"]]);
      expect(onSend).not.toHaveBeenCalled();
      expect(onRunCommand).not.toHaveBeenCalled();
    });

    it("still sends ordinary text at once", () => {
      type("hello there");
      press("Enter");
      expect(onSend).toHaveBeenCalledOnce();
      expect(onResolveError).not.toHaveBeenCalled();
    });

    it("says so in the menu instead of claiming there is no command, and asks again for each new command", () => {
      type("/");
      expect(panel()?.getAttribute("role")).toBe("status");
      expect(container.textContent).toContain("chatbot.commandMenu.error");
      expect(container.textContent).not.toContain("chatbot.commandMenu.none");
      expect(refetchCommands.mock.calls).toEqual([["team-1"]]);
      type("/zzz");
      expect(container.textContent).toContain("chatbot.commandMenu.error");
      expect(container.textContent).not.toContain("chatbot.commandMenu.noMatch");
      expect(refetchCommands).toHaveBeenCalledOnce();

      type("");
      type("/");
      expect(refetchCommands).toHaveBeenCalledTimes(2);
    });

    it("still lists the commands of the catalogs that answered", () => {
      skillCatalog = { supported: true, skills: [{ name: "review", description: "Review" }] };
      act(() => root.render(<Host />));
      type("/");
      expect(labels()).toEqual(["/review"]);
      expect(container.textContent).not.toContain("chatbot.commandMenu.error");
    });
  });
});

describe("restoring recalled invocations", () => {
  it.each(
    ["skill", "personal", "missing", "loading"].flatMap((variant) => [
      { variant, padding: "" },
      { variant, padding: "  " },
    ]),
  )(
    "preserves the selected prompt identity with $variant homonym/catalog and padding '$padding'",
    async ({ variant, padding }) => {
      const selectedId = variant === "personal" ? "private-review" : "p-review";
      listResult = { data: [{ ...PROMPTS[0], command: "review", prompt_id: "p-review" }] };
      personalResult = { data: [{ ...PROMPTS[0], command: "review", prompt_id: "private-review" }] };
      skillCatalog = { supported: true, skills: [{ name: "review", description: "Review" }] };
      fetchPrompt.mockImplementation(() => ({ unwrap: async () => ({ text: "Selected instructions" }) }));
      act(() => root.render(<Host personalTeamId="personal-1" />));
      const command = {
        command: "review",
        prompt_id: selectedId,
        draft_text: `${padding}Before /review Notes${padding}`,
        draft_command_offset: 7 + padding.length,
      };
      const message = {
        id: "recalled",
        role: "user" as const,
        text: "Expanded instructions",
        isStreaming: false,
        traceMessages: [],
        command,
        sources: [],
        uiParts: [],
      };
      if (variant === "missing" || variant === "loading") {
        listResult = { currentData: variant === "missing" ? [] : undefined };
        act(() => root.render(<Host personalTeamId="personal-1" />));
      }
      act(() => {
        renders[renders.length - 1]!.dismiss(command.draft_text, message);
        setHostInput(command.draft_text);
      });
      if (variant === "loading") {
        listResult = { data: [{ ...PROMPTS[0], command: "review", prompt_id: "p-review" }] };
        act(() => root.render(<Host personalTeamId="personal-1" />));
      }
      await act(async () => renders[renders.length - 1]!.submit());
      if (variant === "missing") {
        expect(onResolveError.mock.calls).toEqual([["stale", "review"]]);
        expect(onRunCommand).not.toHaveBeenCalled();
      } else {
        expect(onRunCommand).toHaveBeenCalledOnce();
        expect(onRunCommand.mock.calls[0][0].command).toMatchObject({
          prompt_id: selectedId,
          draft_command_offset: 7 + padding.length,
        });
        expect(fetchPrompt).toHaveBeenCalledWith(
          {
            teamId: variant === "personal" ? "personal-1" : "team-1",
            promptId: selectedId,
          },
          false,
        );
      }
      expect(onRunSkill).not.toHaveBeenCalled();
      expect(onSend).not.toHaveBeenCalled();
    },
  );
  it("rejects a recalled skill missing from the current catalog", async () => {
    const message = {
      id: "recalled",
      role: "user" as const,
      text: "/removed Notes",
      isStreaming: false,
      traceMessages: [],
      skillNames: ["removed"],
      sources: [],
      uiParts: [],
    };
    act(() => {
      renders[renders.length - 1]!.dismiss(message.text, message);
      setHostInput(message.text);
    });
    await act(async () => renders[renders.length - 1]!.submit());
    expect(onSkillError).toHaveBeenCalledWith("unavailable");
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("several prompt commands in one message", () => {
  const TONE = { prompt_id: "p-tone", command: "tone", name: "Ton", description: "Ton formel", emoji: null };
  const TEXTS: Record<string, string> = {
    "p-summary": "Summarise the document.",
    "p-search": "Search the corpus.",
    "p-tone": "Use a formal tone.",
    "personal-summary": "My own summary.",
    "p-style": "Write plainly.",
    "p-review": "Review it.",
  };
  const latest = () => renders[renders.length - 1]!;
  const cm = () => EditorView.findFromDOM(container.querySelector(".cm-content")!)!;
  const cmPress = (key: string) =>
    act(() => cm().contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })));
  /** Types at the end of the line, one user edit. */
  const cmAppend = (text: string) =>
    act(() => {
      const end = cm().state.doc.length;
      cm().dispatch({ changes: { from: end, insert: text }, selection: { anchor: end + text.length } });
    });
  const tokens = () => latest().selectedPrompts.map((prompt) => [prompt.command, prompt.promptTeamId, prompt.from]);
  const submit = () => act(async () => latest().submit());

  function mount(personal: unknown[] = [TONE], skills: string[] = []) {
    personalResult = { data: personal as typeof PROMPTS };
    skillCatalog = { supported: true, skills: skills.map((name) => ({ name, description: name })) };
    fetchPrompt.mockImplementation(({ promptId }: { promptId: string }) => ({
      unwrap: async () => ({ text: TEXTS[promptId] }),
    }));
    act(() => root.render(<Host inlineEditor personalTeamId="personal-1" />));
    act(() => cm().contentDOM.focus());
  }

  it("still offers the prompts of both libraries once the message holds a prompt", () => {
    mount([TONE], ["verify-answer"]);
    cmAppend("/su");
    cmPress("Tab");
    expect(cm().state.doc.toString()).toBe("/summary ");
    expect(latest().menu).toBeNull();

    cmAppend("/");
    // The token in the editor is a group of its own, with no heading.
    expect(sections().filter(([heading]) => heading)).toEqual([
      ["chatbot.commandMenu.sections.teamFallback", ["/search", "/summary"]],
      ["chatbot.commandMenu.sections.personal", ["/tone"]],
      ["chatbot.commandMenu.sections.platform", ["/verify-answer"]],
    ]);
  });

  it("holds two tokens picked from two libraries and keeps one when the other is removed", () => {
    mount([TONE, { ...TONE, prompt_id: "personal-summary", command: "summary", name: "Mine" }]);
    cmAppend("/to");
    cmPress("Tab");
    cmAppend("then /summ");
    // The team's `/summary` is the first row, the personal one the second.
    cmPress("ArrowDown");
    cmPress("Tab");
    expect(cm().state.doc.toString()).toBe("/tone then /summary ");
    expect(tokens()).toEqual([
      ["tone", "personal-1", 0],
      ["summary", "personal-1", 11],
    ]);
    expect(latest().selectedPrompts[1].promptId).toBe("personal-summary");
    expect(container.querySelectorAll(".cm-content [data-kind=prompt]")).toHaveLength(2);
    expect(latest().menu).toBeNull();

    // One Backspace takes the first token as a block; the second keeps its library.
    act(() => cm().dispatch({ selection: { anchor: 5 } }));
    cmPress("Backspace");
    expect(cm().state.doc.toString()).toBe("then /summary ");
    expect(latest().selectedPrompts.map((prompt) => [prompt.promptId, prompt.from])).toEqual([["personal-summary", 5]]);
  });

  it("expands every prompt in place, in order, and lists each one on the descriptor", async () => {
    mount();
    cmAppend("First /summary then /tone please");
    fetchPrompt.mockClear();
    await submit();

    expect(fetchPrompt.mock.calls).toEqual([
      [{ teamId: "team-1", promptId: "p-summary" }, false],
      [{ teamId: "personal-1", promptId: "p-tone" }, false],
    ]);
    expect(onRunCommand).toHaveBeenCalledExactlyOnceWith({
      text: "First\n\nSummarise the document.\n\nthen\n\nUse a formal tone.\n\nplease",
      command: {
        command: "summary",
        appended_text: "First\n\nthen\n\nplease",
        prompt_id: "p-summary",
        prompt_name: "Résumé",
        draft_text: "First /summary then /tone please",
        draft_command_offset: 6,
        prompts: [
          {
            command: "summary",
            prompt_id: "p-summary",
            prompt_name: "Résumé",
            draft_offset: 6,
            text_offset: 7,
            text_length: 23,
          },
          {
            command: "tone",
            prompt_id: "p-tone",
            prompt_name: "Ton",
            draft_offset: 20,
            text_offset: 38,
            text_length: 18,
          },
        ],
      },
    });
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends the prompt as its library holds it now, not the copy read for the menu", async () => {
    mount();
    fetchPrompt.mockImplementation((_arg: unknown, preferCache: boolean) => ({
      unwrap: async () => ({ text: preferCache ? "Text read when the row was focused." : "Text edited since." }),
    }));
    cmAppend("/summ");
    expect(fetchPrompt).toHaveBeenLastCalledWith({ teamId: "team-1", promptId: "p-summary" }, true);
    cmPress("Tab");
    await submit();
    expect(fetchPrompt).toHaveBeenLastCalledWith({ teamId: "team-1", promptId: "p-summary" }, false);
    expect(onRunCommand.mock.calls[0][0].text).toBe("Text edited since.");
  });

  it("starts every read before waiting for any of them", async () => {
    mount();
    cmAppend("/summary and /tone now");
    const pending: (() => void)[] = [];
    fetchPrompt.mockReset();
    fetchPrompt.mockImplementation(({ promptId }: { promptId: string }) => ({
      unwrap: () => new Promise((resolve) => pending.push(() => resolve({ text: TEXTS[promptId] }))),
    }));
    act(() => latest().submit());

    expect(fetchPrompt).toHaveBeenCalledTimes(2);
    expect(onRunCommand).not.toHaveBeenCalled();
    // Answers arriving out of order do not change the order of the text.
    await act(async () => pending.reverse().forEach((resolve) => resolve()));
    expect(onRunCommand.mock.calls[0][0].text).toBe("Summarise the document.\n\nand\n\nUse a formal tone.\n\nnow");
  });

  it("sends the selected skills with the prompts", async () => {
    mount([TONE], ["verify-answer"]);
    cmAppend("/summary /verify-answer and /tone now");
    await submit();

    expect(onRunCommand).toHaveBeenCalledOnce();
    expect(onRunCommand.mock.calls[0][0]).toMatchObject({
      text: "Summarise the document.\n\n/verify-answer and\n\nUse a formal tone.\n\nnow",
      skills: [{ name: "verify-answer" }],
    });
    expect(onRunCommand.mock.calls[0][0].command.prompts.map((entry: { command: string }) => entry.command)).toEqual([
      "summary",
      "tone",
    ]);
    expect(onRunSkill).not.toHaveBeenCalled();
  });

  it.each([
    { status: 404, reason: "stale" },
    { status: 500, reason: "unreadable" },
  ])("holds the whole message back and names the command when one read answers $status", async ({ status, reason }) => {
    mount([TONE], ["verify-answer"]);
    cmAppend("/summary /verify-answer and /tone now");
    fetchPrompt.mockImplementation(({ promptId }: { promptId: string }) => ({
      unwrap: () =>
        promptId === "p-tone" ? Promise.reject({ status, data: {} }) : Promise.resolve({ text: TEXTS[promptId] }),
    }));
    await submit();

    expect(onResolveError.mock.calls).toEqual([[reason, "tone"]]);
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onRunSkill).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
    expect(cm().state.doc.toString()).toBe("/summary /verify-answer and /tone now");
  });

  it("holds the message back when a prompt is empty", async () => {
    mount();
    cmAppend("/summary and /tone now");
    fetchPrompt.mockImplementation(({ promptId }: { promptId: string }) => ({
      unwrap: async () => ({ text: promptId === "p-tone" ? "  " : TEXTS[promptId] }),
    }));
    await submit();

    expect(onResolveError.mock.calls).toEqual([["unreadable", "tone"]]);
    expect(onRunCommand).not.toHaveBeenCalled();
  });

  it("reports the first failing command of the line, not the first failure in time", async () => {
    mount();
    cmAppend("/summary and /tone now");
    const reject: Record<string, () => void> = {};
    fetchPrompt.mockReset();
    fetchPrompt.mockImplementation(({ promptId }: { promptId: string }) => ({
      unwrap: () =>
        new Promise((_resolve, fail) => {
          reject[promptId] = () => fail({ status: promptId === "p-tone" ? 500 : 404, data: {} });
        }),
    }));
    act(() => latest().submit());
    await act(async () => reject["p-tone"]());
    expect(onResolveError).not.toHaveBeenCalled();
    await act(async () => reject["p-summary"]());

    expect(onResolveError.mock.calls).toEqual([["stale", "summary"]]);
    expect(onRunCommand).not.toHaveBeenCalled();
  });

  it("expands the same command at each occurrence and reads its prompt once", async () => {
    mount();
    cmAppend("/summary of A, /summary of B");
    expect(tokens()).toEqual([
      ["summary", "team-1", 0],
      ["summary", "team-1", 15],
    ]);
    fetchPrompt.mockClear();
    await submit();

    expect(fetchPrompt).toHaveBeenCalledOnce();
    const run = onRunCommand.mock.calls[0][0];
    expect(run.text).toBe("Summarise the document.\n\nof A,\n\nSummarise the document.\n\nof B");
    expect(run.command.prompts.map((entry: { draft_offset: number }) => entry.draft_offset)).toEqual([0, 15]);
  });

  it("refuses a message holding more prompt commands than the limit, and sends one at the limit", async () => {
    mount();
    cmAppend(Array.from({ length: 17 }, () => "/summary").join(" ") + " end");
    fetchPrompt.mockClear();
    await submit();

    expect(onResolveError.mock.calls).toEqual([["tooMany", "summary"]]);
    expect(fetchPrompt).not.toHaveBeenCalled();
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();

    act(() => cm().dispatch({ changes: { from: 0, to: "/summary ".length } }));
    await submit();
    expect(onRunCommand.mock.calls[0][0].command.prompts).toHaveLength(16);
  });

  it("resolves hand-typed names one by one, the team's command before the personal one", async () => {
    mount([TONE, { ...TONE, prompt_id: "personal-summary", command: "summary", name: "Mine" }]);
    cmAppend("/summary and /tone then /summary now");
    expect(tokens()).toEqual([
      ["summary", "team-1", 0],
      ["tone", "personal-1", 13],
      ["summary", "team-1", 24],
    ]);
    fetchPrompt.mockClear();
    await submit();

    expect(fetchPrompt.mock.calls.map(([arg]) => arg)).toEqual([
      { teamId: "team-1", promptId: "p-summary" },
      { teamId: "personal-1", promptId: "p-tone" },
    ]);
    expect(
      onRunCommand.mock.calls[0][0].command.prompts.map((entry: { prompt_id: string }) => entry.prompt_id),
    ).toEqual(["p-summary", "p-tone", "p-summary"]);
  });

  it("mixes a picked personal homonym with the same name typed by hand", async () => {
    mount([{ ...TONE, prompt_id: "personal-summary", command: "summary", name: "Mine" }]);
    cmAppend("/summ");
    cmPress("ArrowDown");
    cmPress("Tab");
    cmAppend("then /summary now");
    await submit();

    expect(
      onRunCommand.mock.calls[0][0].command.prompts.map((entry: { prompt_id: string }) => entry.prompt_id),
    ).toEqual(["personal-summary", "p-summary"]);
    expect(onRunCommand.mock.calls[0][0].text).toBe("My own summary.\n\nthen\n\nSummarise the document.\n\nnow");
  });

  it("waits for the team's catalog for a typed name next to a picked personal prompt", async () => {
    mount([TONE, { ...TONE, prompt_id: "p-style", command: "style", name: "Style" }]);
    listResult = { data: PROMPTS, currentData: undefined };
    act(() => root.render(<Host inlineEditor personalTeamId="personal-1" />));
    cmAppend("/sty");
    cmPress("Tab");
    cmAppend("then /tone now");
    refetchCommands.mockImplementation(async () => ({ data: PROMPTS }));
    await submit();

    // The team answered that it has no `/tone`: the personal one runs.
    expect(onResolveError).not.toHaveBeenCalled();
    expect(
      onRunCommand.mock.calls[0][0].command.prompts.map((entry: { prompt_id: string }) => entry.prompt_id),
    ).toEqual(["p-style", "p-tone"]);
  });

  it("keeps a typed skill homonym a skill next to a prompt, unless its prompt row was picked", async () => {
    mount([{ ...TONE, prompt_id: "p-review", command: "review", name: "Relecture" }], ["review"]);
    cmAppend("/summary then /review the text");
    expect(latest().selectedPrompts.map((prompt) => prompt.command)).toEqual(["summary"]);
    expect(latest().selectedSkills.map((skill) => skill.name)).toEqual(["review"]);
    await submit();
    expect(onRunCommand.mock.calls[0][0]).toMatchObject({
      text: "Summarise the document.\n\nthen /review the text",
      skills: [{ name: "review" }],
    });
    expect(onRunCommand.mock.calls[0][0].command.prompts).toHaveLength(1);

    // Picked from the personal section, the same name is a prompt and no longer a skill.
    onRunCommand.mockClear();
    act(() => cm().dispatch({ changes: { from: 0, to: cm().state.doc.length, insert: "/summary then " } }));
    act(() => cm().dispatch({ selection: { anchor: cm().state.doc.length } }));
    cmAppend("/rev");
    expect(latest().menu?.entries.map((entry) => entry.kind)).toEqual(["prompt", "skill"]);
    cmPress("Tab");
    expect(latest().selectedPrompts.map((prompt) => prompt.command)).toEqual(["summary", "review"]);
    expect(latest().selectedSkills).toEqual([]);
    await submit();
    expect(onRunCommand.mock.calls[0][0].text).toBe("Summarise the document.\n\nthen\n\nReview it.");
    expect(onRunCommand.mock.calls[0][0]).not.toHaveProperty("skills");
  });

  it("keeps hand-typed tokens while the text around them is edited", () => {
    mount();
    cmAppend("/summary and /tone now");
    expect(tokens().map(([command]) => command)).toEqual(["summary", "tone"]);

    // Deleting what follows the last token leaves it at the very end of the line.
    act(() => cm().dispatch({ changes: { from: "/summary and /tone".length, to: cm().state.doc.length } }));
    expect(cm().state.doc.toString()).toBe("/summary and /tone");
    expect(tokens().map(([command]) => command)).toEqual(["summary", "tone"]);
    expect(latest().menu).toBeNull();

    // An edit before it moves it; it is still the same token.
    act(() => cm().dispatch({ changes: { from: 9, insert: "first " } }));
    expect(cm().state.doc.toString()).toBe("/summary first and /tone");
    expect(tokens()).toEqual([
      ["summary", "team-1", 0],
      ["tone", "personal-1", 19],
    ]);
  });

  describe("a character glued to a token", () => {
    const SUM = { ...TONE, prompt_id: "p-sum", command: "sum", name: "Somme" };
    const cmInsert = (at: number, text: string) =>
      act(() => cm().dispatch({ changes: { from: at, insert: text }, selection: { anchor: at + text.length } }));
    const pickSum = () => {
      listResult = { data: [SUM, ...PROMPTS] };
      mount([]);
      cmAppend("/sum");
      expect(labels()).toEqual(["/sum", "/summary"]);
      cmPress("Tab");
      expect(cm().state.doc.toString()).toBe("/sum ");
      expect(latest().selectedPrompts.map((prompt) => prompt.promptId)).toEqual(["p-sum"]);
    };

    it("turns a picked prompt back into text when letters are typed right after it", async () => {
      pickSum();
      cmPress("Backspace");
      expect(cm().state.doc.toString()).toBe("/sum");
      expect(latest().selectedPrompts.map((prompt) => prompt.promptId)).toEqual(["p-sum"]);
      cmAppend("mary x");

      // The line now reads as the other command, typed by hand.
      expect(latest().trigger.choices).toEqual([]);
      expect(latest().selectedPrompts.map((prompt) => prompt.promptId)).toEqual(["p-summary"]);
      await submit();
      expect(onRunCommand.mock.calls[0][0].command).toMatchObject({
        draft_text: "/summary x",
        prompts: [expect.objectContaining({ command: "summary", prompt_id: "p-summary" })],
      });
    });

    it("does not pin the prompt again when the glued letter is removed", () => {
      pickSum();
      cmPress("Backspace");
      cmAppend("x");
      expect(latest().selectedPrompts).toEqual([]);
      cmPress("Backspace");
      expect(cm().state.doc.toString()).toBe("/sum");
      expect(latest().trigger.choices).toEqual([]);
      expect(container.querySelector(".cm-content [data-kind=prompt]")).toBeNull();
    });

    it("turns a picked prompt back into text when a character is typed right before it", async () => {
      pickSum();
      cmInsert(0, "x");
      expect(cm().state.doc.toString()).toBe("x/sum ");
      expect(latest().trigger.choices).toEqual([]);
      expect(latest().selectedPrompts).toEqual([]);
      expect(container.querySelector(".cm-content [data-kind=prompt]")).toBeNull();
      await submit();
      expect(onSend).toHaveBeenCalledOnce();
      expect(onRunCommand).not.toHaveBeenCalled();
    });

    it.each(["after", "before"])(
      "turns a picked skill back into text when a character is typed right %s it",
      (side) => {
        mount([], ["review"]);
        cmAppend("/rev");
        cmPress("Tab");
        cmPress("Backspace");
        expect(cm().state.doc.toString()).toBe("/review");
        expect(latest().selectedSkills.map((skill) => skill.name)).toEqual(["review"]);

        cmInsert(side === "after" ? 7 : 0, "s");
        expect(latest().trigger.choices).toEqual([]);
        expect(latest().selectedSkills).toEqual([]);
        expect(container.querySelector(".cm-content [data-kind=skill]")).toBeNull();

        // Back to the bare name: a name being typed, like any other.
        act(() => cm().dispatch({ changes: side === "after" ? { from: 7, to: 8 } : { from: 0, to: 1 } }));
        expect(cm().state.doc.toString()).toBe("/review");
        expect(latest().selectedSkills).toEqual([]);
      },
    );
  });

  describe("deleting one of two tokens with the same name", () => {
    const MINE = { ...TONE, prompt_id: "personal-summary", command: "summary", name: "Mine" };
    const pickBoth = (before: string) => {
      mount([MINE]);
      cmAppend(`${before}/summ`);
      cmPress("Tab");
      cmAppend("/summ");
      cmPress("ArrowDown");
      cmPress("Tab");
      cmAppend("x");
      expect(cm().state.doc.toString()).toBe(`${before}/summary /summary x`);
      expect(latest().selectedPrompts.map((prompt) => prompt.promptId)).toEqual(["p-summary", "personal-summary"]);
    };

    it.each(["", "a "])("keeps the second token's own prompt when the first is removed after %j", async (before) => {
      pickBoth(before);
      act(() => cm().dispatch({ selection: { anchor: before.length + "/summary".length } }));
      cmPress("Backspace");
      expect(cm().state.doc.toString()).toBe(`${before}/summary x`);
      expect(latest().selectedPrompts.map((prompt) => [prompt.promptId, prompt.from])).toEqual([
        ["personal-summary", before.length],
      ]);
      await submit();
      expect(onRunCommand.mock.calls[0][0].command.prompts).toEqual([
        expect.objectContaining({ prompt_id: "personal-summary", draft_offset: before.length }),
      ]);
    });

    it("keeps the first token's own prompt when the second is removed", () => {
      pickBoth("");
      act(() => cm().dispatch({ selection: { anchor: "/summary ".length } }));
      cmPress("Delete");
      expect(cm().state.doc.toString()).toBe("/summary x");
      expect(latest().selectedPrompts.map((prompt) => prompt.promptId)).toEqual(["p-summary"]);
    });

    it("gives both tokens their prompt back on undo, and removes the same one on redo", () => {
      pickBoth("");
      act(() => cm().dispatch({ selection: { anchor: "/summary".length } }));
      cmPress("Backspace");
      act(() => {
        undo(cm());
      });
      expect(cm().state.doc.toString()).toBe("/summary /summary x");
      expect(latest().selectedPrompts.map((prompt) => prompt.promptId)).toEqual(["p-summary", "personal-summary"]);
      act(() => {
        redo(cm());
      });
      expect(cm().state.doc.toString()).toBe("/summary x");
      expect(latest().selectedPrompts.map((prompt) => prompt.promptId)).toEqual(["personal-summary"]);
    });

    it("leaves the skill when the prompt of the same name before it is removed", async () => {
      listResult = { data: [{ ...TONE, prompt_id: "p-review", command: "review", name: "Review" }] };
      mount([], ["review"]);
      cmAppend("/rev");
      cmPress("Tab");
      cmAppend("/rev");
      cmPress("ArrowDown");
      cmPress("Tab");
      cmAppend("x");
      expect(cm().state.doc.toString()).toBe("/review /review x");
      expect(latest().selectedPrompts.map((prompt) => prompt.from)).toEqual([0]);
      expect(latest().selectedSkills.map((skill) => skill.from)).toEqual([8]);

      act(() => cm().dispatch({ selection: { anchor: "/review".length } }));
      cmPress("Backspace");
      expect(cm().state.doc.toString()).toBe("/review x");
      expect(latest().selectedPrompts).toEqual([]);
      expect(latest().selectedSkills.map((skill) => skill.from)).toEqual([0]);
      await submit();
      expect(onRunSkill).toHaveBeenCalledWith({ text: "/review x", skills: [{ name: "review" }] });
      expect(onRunCommand).not.toHaveBeenCalled();
    });
  });

  describe("recalled", () => {
    const personalSummary2 = { ...TONE, prompt_id: "personal-summary", command: "summary-2", name: "Mine" };
    const line = "/summary then /summary-2 now";
    const message = {
      id: "recalled",
      role: "user" as const,
      text: "Summarise the document.\n\nthen\n\nMy own summary.\n\nnow",
      isStreaming: false,
      traceMessages: [],
      sources: [],
      uiParts: [],
      command: {
        command: "summary",
        prompt_id: "p-summary",
        draft_text: line,
        draft_command_offset: 0,
        prompts: [
          { command: "summary", prompt_id: "p-summary", draft_offset: 0, text_offset: 0, text_length: 23 },
          { command: "summary-2", prompt_id: "personal-summary", draft_offset: 14, text_offset: 31, text_length: 15 },
        ],
      },
    };
    const recall = () =>
      act(() => {
        latest().dismiss(line, message);
        setHostInput(line);
      });

    it("restores every prompt with its identity and reads each from its own library", async () => {
      mount([personalSummary2]);
      recall();
      expect(latest().trigger.choices).toEqual([
        expect.objectContaining({ kind: "prompt", promptId: "p-summary", promptTeamId: "team-1", from: 0 }),
        expect.objectContaining({ kind: "prompt", promptId: "personal-summary", promptTeamId: "personal-1", from: 14 }),
      ]);
      expect(latest().menu).toBeNull();
      fetchPrompt.mockClear();
      await submit();

      expect(fetchPrompt.mock.calls.map(([arg]) => arg)).toEqual([
        { teamId: "team-1", promptId: "p-summary" },
        { teamId: "personal-1", promptId: "personal-summary" },
      ]);
      expect(onRunCommand.mock.calls[0][0].command.prompts).toEqual([
        expect.objectContaining({ prompt_id: "p-summary", draft_offset: 0 }),
        expect.objectContaining({ prompt_id: "personal-summary", draft_offset: 14 }),
      ]);
    });

    it("holds the message back and names the prompt that is gone, with no homonym fallback", async () => {
      // The personal prompt was deleted and another one took its command.
      mount([{ ...personalSummary2, prompt_id: "another" }]);
      recall();
      fetchPrompt.mockClear();
      await submit();

      expect(onResolveError.mock.calls).toEqual([["stale", "summary-2"]]);
      expect(fetchPrompt).not.toHaveBeenCalled();
      expect(onRunCommand).not.toHaveBeenCalled();
    });

    it("restores the single prompt of a turn whose list does not fit its text", () => {
      mount([personalSummary2]);
      act(() => {
        latest().dismiss(line, { ...message, text: "short" });
        setHostInput(line);
      });
      expect(latest().trigger.choices).toEqual([
        expect.objectContaining({ kind: "prompt", promptId: "p-summary", from: 0 }),
      ]);
    });
  });
});
