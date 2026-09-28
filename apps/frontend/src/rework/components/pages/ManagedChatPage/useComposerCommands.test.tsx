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

// The whole trigger, driven the way a user drives it: the real composer, the
// real menu, and the hook between them. Mounted together because the keyboard
// model only exists as the three of them — the field consumes a key only when
// the hook claims it, and the hook claims it only when the menu is open.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandMenu } from "@shared/molecules/CommandMenu/CommandMenu";
import { RichInputField, type CommandTriggerBinding } from "@shared/molecules/RichInputField/RichInputField";
import { useComposerCommands, type ComposerCommandsMenu } from "./useComposerCommands";

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
let listResult: { data?: typeof PROMPTS } = { data: PROMPTS };

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery: () => listResult,
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [fetchPrompt],
}));

const onRunCommand = vi.fn();
const onSend = vi.fn();
const onResolveError = vi.fn();
let renders: { menu: ComposerCommandsMenu | null; submit: () => void; trigger: CommandTriggerBinding }[] = [];

function Host() {
  const [input, setInput] = useState("");
  const commands = useComposerCommands({
    teamId: "team-1",
    input,
    setInput,
    onRunCommand,
    onSend,
    onResolveError,
  });
  renders.push(commands);
  return (
    <RichInputField
      value={input}
      onChange={setInput}
      onSend={commands.submit}
      commandTrigger={commands.trigger}
      aboveFieldSlot={commands.menu ? <CommandMenu {...commands.menu} /> : undefined}
    />
  );
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  listResult = { data: PROMPTS };
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

function type(text: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(textarea(), text);
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
  return options().map((option) => option.querySelector("span > span")?.textContent ?? "");
}

function focusedLabel(): string | null {
  const active = textarea().getAttribute("aria-activedescendant");
  const option = options().find((candidate) => candidate.id === active);
  return option?.querySelector("span > span")?.textContent ?? null;
}

describe("the command menu", () => {
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
      command: { command: "summary", prompt_id: "p-summary", prompt_name: "Résumé" },
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
      command: {
        command: "summary",
        appended_text: "33 lignes",
        prompt_id: "p-summary",
        prompt_name: "Résumé",
      },
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
