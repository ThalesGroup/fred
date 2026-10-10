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

import { act, useCallback, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandMenu } from "@shared/molecules/CommandMenu/CommandMenu";
import { RichInputField } from "@shared/molecules/RichInputField/RichInputField";
import type { ThreadMessage } from "@rework/types/thread";
import type { CommandDescriptor } from "../../../../slices/runtime/runtimeOpenApi";
import { useComposerCommands } from "./useComposerCommands";
import { recallLinesOf, useComposerRecall } from "./useComposerRecall";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

const PROMPTS = [
  { prompt_id: "p-search", name: "Recherche", command: "search", description: "Chercher", emoji: null },
  { prompt_id: "p-summary", name: "Résumé", command: "summary", description: "Résumer", emoji: null },
];

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery: () => ({ data: PROMPTS }),
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [vi.fn()],
}));

let counter = 0;
function turn(role: ThreadMessage["role"], text: string, command?: CommandDescriptor): ThreadMessage {
  counter += 1;
  return {
    id: `m-${counter}`,
    role,
    text,
    isStreaming: false,
    traceMessages: [],
    sources: [],
    uiParts: [],
    command: command ?? null,
  };
}

function summaryCommand(appended?: string): CommandDescriptor {
  return {
    command: "summary",
    prompt_id: "p-summary",
    prompt_name: "Résumé",
    ...(appended ? { appended_text: appended } : {}),
  } as CommandDescriptor;
}

let messages: ThreadMessage[] = [];
let disabled = false;

// Wired the way ManagedChatPage wires it: the menu first, then the recall.
function Host() {
  const [input, setInput] = useState("");
  const [focusEndRequestId, setFocusEndRequestId] = useState(0);
  const commands = useComposerCommands({
    teamId: "team-1",
    input,
    setInput,
    onRunCommand: vi.fn(),
    onSend: vi.fn(),
    onResolveError: vi.fn(),
  });
  const { dismiss } = commands;
  const onRecall = useCallback(
    (line: string) => {
      dismiss(line);
      setInput(line);
      setFocusEndRequestId((n) => n + 1);
    },
    [dismiss],
  );
  const recallKeyDown = useComposerRecall({
    messages,
    input,
    menuOpen: commands.trigger.open,
    disabled,
    onRecall,
  });
  return (
    <RichInputField
      value={input}
      onChange={setInput}
      onSend={commands.submit}
      commandTrigger={commands.trigger}
      onRecallKeyDown={recallKeyDown}
      aboveFieldSlot={commands.menu ? <CommandMenu {...commands.menu} /> : undefined}
      focusEndRequestId={focusEndRequestId}
      disabled={disabled}
    />
  );
}

let container: HTMLDivElement;
let root: Root;

function mount() {
  act(() => {
    root.render(<Host />);
  });
}

beforeEach(() => {
  messages = [
    turn("user", "Summarize the report"),
    turn("assistant", "Here is the summary."),
    turn("user", "Translate it to French"),
    turn("assistant", "Voici la traduction."),
  ];
  disabled = false;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  mount();
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
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

function press(key: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  act(() => {
    textarea().dispatchEvent(event);
  });
  return event;
}

function menuOpen(): boolean {
  return container.querySelector('[role="listbox"]') !== null;
}

describe("recallLinesOf", () => {
  it("lists user turns newest first, skipping answers, empty turns and consecutive repeats", () => {
    const lines = recallLinesOf([
      turn("user", "a"),
      turn("assistant", "answer"),
      turn("user", "b"),
      turn("user", "b"),
      turn("user", "  "),
      turn("hitl_response", "Yes"),
      turn("user", "a"),
    ]);

    expect(lines).toEqual(["a", "b", "a"]);
  });

  it("rebuilds a command turn as the line that was typed", () => {
    const lines = recallLinesOf([
      turn("user", "Résume le document en :", summaryCommand()),
      turn("user", "Résume le document en :\n\nfocus on risks", summaryCommand("focus on risks")),
    ]);

    expect(lines).toEqual(["/summary focus on risks", "/summary"]);
  });
});

describe("recalling sent messages in the composer", () => {
  it("recalls the last message with the caret at the end", () => {
    const event = press("ArrowUp");

    expect(event.defaultPrevented).toBe(true);
    expect(textarea().value).toBe("Translate it to French");
    expect(textarea().selectionStart).toBe("Translate it to French".length);
  });

  it("goes back and forth, and empties the composer past the newest", () => {
    press("ArrowUp");
    press("ArrowUp");
    expect(textarea().value).toBe("Summarize the report");
    press("ArrowDown");
    expect(textarea().value).toBe("Translate it to French");
    press("ArrowDown");
    expect(textarea().value).toBe("");
  });

  it("stays on the oldest message", () => {
    press("ArrowUp");
    press("ArrowUp");
    const event = press("ArrowUp");

    expect(event.defaultPrevented).toBe(true);
    expect(textarea().value).toBe("Summarize the report");
  });

  it("does nothing with no sent message, or ArrowDown in an empty composer", () => {
    expect(press("ArrowDown").defaultPrevented).toBe(false);

    messages = [];
    mount();
    expect(press("ArrowUp").defaultPrevented).toBe(false);
    expect(textarea().value).toBe("");
  });

  it("hands the arrows back to the caret once the recalled text is edited", () => {
    press("ArrowUp");
    type("Translate it to French please");

    expect(press("ArrowUp").defaultPrevented).toBe(false);
    expect(textarea().value).toBe("Translate it to French please");
  });

  it("leaves a typed draft alone", () => {
    type("A new question");

    expect(press("ArrowUp").defaultPrevented).toBe(false);
    expect(textarea().value).toBe("A new question");
  });

  it("ignores the arrows with a modifier held", () => {
    for (const modifier of ["shiftKey", "ctrlKey", "altKey", "metaKey"] as const) {
      expect(press("ArrowUp", { [modifier]: true }).defaultPrevented).toBe(false);
    }
    expect(textarea().value).toBe("");
  });

  it("recalls nothing from a disabled composer", () => {
    disabled = true;
    mount();

    press("ArrowUp");
    expect(textarea().value).toBe("");
  });

  it("leaves the arrows to an open command menu", () => {
    type("/");
    press("ArrowUp");

    expect(menuOpen()).toBe(true);
    expect(textarea().value).toBe("/");
  });
});

describe("recalling a command message", () => {
  beforeEach(() => {
    messages = [
      turn("user", "Summarize the report"),
      turn("user", "Résume le document en :\n\nfocus on risks", summaryCommand("focus on risks")),
      turn("user", "Résume le document en :", summaryCommand()),
    ];
    mount();
  });

  it("recalls the typed line, not the expanded prompt", () => {
    press("ArrowUp");
    expect(textarea().value).toBe("/summary");
    press("ArrowUp");
    expect(textarea().value).toBe("/summary focus on risks");
  });

  it("keeps the menu shut on a recalled command and goes on browsing", () => {
    press("ArrowUp");
    expect(menuOpen()).toBe(false);

    press("ArrowUp");
    press("ArrowUp");
    expect(textarea().value).toBe("Summarize the report");
  });

  it("never renders the menu while browsing past a command, even for a frame", () => {
    // Mutation records, not a DOM read: a flashed menu is gone again by the end.
    const observer = new MutationObserver(() => undefined);
    observer.observe(container, { childList: true, subtree: true });

    press("ArrowUp");
    press("ArrowUp");
    press("ArrowUp");
    press("ArrowDown");
    const added = observer.takeRecords().flatMap((record) => Array.from(record.addedNodes));
    observer.disconnect();
    const flashed = added.some((node) => {
      const el = node as Element;
      return !!el.matches?.('[role="listbox"]') || !!el.querySelector?.('[role="listbox"]');
    });

    expect(textarea().value).toBe("/summary focus on risks");
    expect(flashed).toBe(false);
  });

  it("opens the menu once the recalled command is edited", () => {
    press("ArrowUp");
    type("/summar");

    expect(menuOpen()).toBe(true);
    type("/summary");
    expect(menuOpen()).toBe(true);
  });
});
