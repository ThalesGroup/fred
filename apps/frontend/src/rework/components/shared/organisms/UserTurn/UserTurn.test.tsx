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

// #2359: the user turn's copy affordance is the SAME one as the assistant
// turn's (#2336) — `ActionBar`, content_copy → check, 2s revert. These tests
// pin the parts that made the two diverge in the first place: the icon flip,
// the timing, and the silent-failure contract inherited from the deleted
// useCopyToClipboard hook.

import { act, useRef, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { assemblePromptTurn, selectedSkillText } from "@rework/utils/skillInvocation";
import { useAssistantCopyInterception } from "@hooks/useAssistantCopyInterception";
import { UserTurn } from "./UserTurn";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const writeText = vi.fn<(text: string) => Promise<void>>();

let container: HTMLDivElement;
let root: Root;

function CopyRegion({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null!);
  useAssistantCopyInterception(ref);
  return <div ref={ref}>{children}</div>;
}

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<CopyRegion>{ui}</CopyRegion>);
  });
}

/** The action's icon glyph, read the way ActionBar renders it. */
function iconOf(button: HTMLButtonElement): string {
  return button.querySelector(".material-symbols-outlined")?.textContent ?? "";
}

function buttons(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll("[role=toolbar] button"));
}

/** Copy is always the last action in the bar; edit, when present, precedes it. */
function copyButton(): HTMLButtonElement {
  const all = buttons();
  const button = all[all.length - 1];
  if (!button) throw new Error("no copy button rendered");
  return button;
}

async function click(button: HTMLButtonElement) {
  await act(async () => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  Object.defineProperty(globalThis.navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  vi.useRealTimers();
});

describe("UserTurn copy affordance (#2359)", () => {
  it.each(["summary", "mermaid"])(
    "restores mixed legacy /%s history without exposing the expanded prompt",
    async (command) => {
      const onOpenCommand = vi.fn();
      const onOpenSkill = vi.fn();
      const onEdit = vi.fn();
      const descriptor = {
        command,
        prompt_id: "legacy-prompt",
        appended_text: "Before /mermaid middle /verify-answer after",
      };
      const draft = `/${command} ${descriptor.appended_text}`;
      render(
        <UserTurn
          text="PRIVATE EXPANDED PROMPT Before /mermaid middle /verify-answer after"
          command={descriptor}
          skillNames={["mermaid", "verify-answer"]}
          onOpenCommand={onOpenCommand}
          onOpenSkill={onOpenSkill}
          onEdit={onEdit}
        />,
      );
      const body = container.querySelector("[data-skill-message]")!;
      expect(body.textContent).toBe(`edit_note/${command} Before mermaid middle verify-answer after`);
      expect(container.textContent).not.toContain("PRIVATE EXPANDED PROMPT");
      expect(body.querySelectorAll("[data-skill-name]")).toHaveLength(2);
      expect(
        Array.from(body.querySelectorAll<HTMLElement>("[data-surface=bubble]")).map((badge) => badge.dataset.kind),
      ).toEqual(["prompt", "skill", "skill"]);
      await click(body.querySelector("button[class*=command]") as HTMLButtonElement);
      expect(onOpenCommand).toHaveBeenCalledWith({
        text: "PRIVATE EXPANDED PROMPT Before /mermaid middle /verify-answer after",
        command: descriptor,
      });
      await click(body.querySelector("button[class*=badge]") as HTMLButtonElement);
      expect(onOpenSkill).toHaveBeenCalledWith("mermaid");
      const range = document.createRange();
      range.selectNodeContents(body);
      expect(selectedSkillText(range, container)).toBe(draft);
      await click(copyButton());
      expect(writeText).toHaveBeenCalledWith(draft);
      await click(buttons()[0]);
      expect(onEdit).toHaveBeenCalledWith(draft);
    },
  );
  it("renders a skill badge with the request and copies a reusable invocation", async () => {
    render(<UserTurn text={"Notes\nAction"} skillName="meeting-minutes" />);
    expect(container.querySelector('[role="group"]')?.textContent).toContain("meeting-minutes");
    expect(container.querySelector("[class*=skillTurn]")?.textContent).toBe("meeting-minutes Notes\nAction");
    expect(container.querySelector('[aria-label="chatbot.skills.remove"]')).toBeNull();
    await click(copyButton());
    expect(writeText).toHaveBeenCalledWith("/meeting-minutes Notes\nAction");
  });

  it("renders and copies a bare selected invocation without duplicate command text", async () => {
    render(<UserTurn text="/skill verify-answer" skillName="verify-answer" />);
    expect(container.querySelector('[role="group"]')?.textContent).toContain("verify-answer");
    expect(container.querySelector("p")).toBeNull();
    expect(container.textContent).not.toContain("/skill verify-answer");
    await click(copyButton());
    expect(writeText).toHaveBeenCalledWith("/verify-answer");
  });

  it("keeps an inline token at its stored position for selection-copy, full copy and editing", async () => {
    const onEdit = vi.fn();
    render(<UserTurn text={"Before /meeting-minutes after\nAction"} skillName="meeting-minutes" onEdit={onEdit} />);
    const body = container.querySelector("[class*=skillTurn]")!;
    expect(body.textContent).toBe("Before meeting-minutes after\nAction");
    expect(body.firstChild?.textContent).toBe("Before ");
    const selection = document.getSelection()!;
    const range = document.createRange();
    range.selectNodeContents(body.querySelector('[role="group"]')!);
    selection.removeAllRanges();
    selection.addRange(range);
    expect(selection.toString()).toBe("meeting-minutes");
    expect(selectedSkillText(range, container)).toBe("/meeting-minutes");
    const setData = vi.fn();
    const copy = new Event("copy", { bubbles: true, cancelable: true });
    Object.defineProperty(copy, "clipboardData", { value: { setData } });
    body.querySelector("[data-skill-name]")!.dispatchEvent(copy);
    expect(copy.defaultPrevented).toBe(true);
    expect(setData).toHaveBeenCalledWith("text/plain", "/meeting-minutes");
    range.selectNodeContents(body);
    expect(selectedSkillText(range, container)).toBe("Before /meeting-minutes after\nAction");
    // Copying the label alone restores the slash hidden from its display.
    range.selectNodeContents(body.querySelector("[data-skill-name]")!);
    expect(selectedSkillText(range, container)).toBe("/meeting-minutes");
    const labelText = body.querySelector("[data-skill-name]")!.firstChild!;
    range.setStart(labelText, 0);
    range.setEnd(body.lastChild!, 6);
    expect(selectedSkillText(range, container)).toBe("/meeting-minutes after");
    range.setEnd(labelText, labelText.textContent!.length);
    expect(selectedSkillText(range, container)).toBe("/meeting-minutes");
    range.setStart(labelText, 8);
    expect(selectedSkillText(range, container)).toBe("minutes");
    range.setEnd(body.lastChild!, 6);
    expect(selectedSkillText(range, container)).toBe("minutes after");
    range.selectNodeContents(body.firstChild!);
    expect(selectedSkillText(range, container)).toBeNull();
    // A selection extending into another message uses native serialization.
    range.selectNodeContents(container);
    expect(selectedSkillText(range, container)).toBeNull();
    selection.removeAllRanges();
    await click(copyButton());
    expect(writeText).toHaveBeenCalledWith("Before /meeting-minutes after\nAction");
    await click(buttons()[0]);
    expect(onEdit).toHaveBeenCalledWith("Before /meeting-minutes after\nAction");
  });

  it.each(["review", "review_long--", "_"])(
    "keeps the prompt %s in mixed history, copy, editing and preview",
    async (command) => {
      const draft = `Before /review middle /${command} after /mermaid Notes`;
      const onEdit = vi.fn();
      const onOpenSkill = vi.fn();
      const onOpenCommand = vi.fn();
      render(
        <UserTurn
          text="assembled prompt"
          skillNames={["review", "mermaid"]}
          command={{ command, prompt_id: "p-review", draft_text: draft, draft_command_offset: 22 }}
          onEdit={onEdit}
          onOpenSkill={onOpenSkill}
          onOpenCommand={onOpenCommand}
        />,
      );
      const body = container.querySelector("[data-skill-message]")!;
      expect(body.textContent).toBe(`Before review middle edit_note/${command} after mermaid Notes`);
      expect(body.querySelectorAll("[data-skill-name]")).toHaveLength(2);
      const prompt = body.querySelector("button[class*=command]") as HTMLButtonElement;
      await click(prompt);
      expect(onOpenCommand).toHaveBeenCalledOnce();
      await click(body.querySelector("button[class*=badge]") as HTMLButtonElement);
      expect(onOpenSkill).toHaveBeenCalledWith("review");
      const range = document.createRange();
      range.selectNodeContents(prompt);
      expect(selectedSkillText(range, container)).toBe(`/${command}`);
      range.setStartBefore(prompt);
      range.setEnd(body, body.childNodes.length);
      expect(selectedSkillText(range, container)).toBe(`/${command} after /mermaid Notes`);
      range.selectNodeContents(body);
      expect(selectedSkillText(range, container)).toBe(draft);
      await click(copyButton());
      expect(writeText).toHaveBeenCalledWith(draft);
      await click(buttons()[buttons().length - 2]!);
      expect(onEdit).toHaveBeenCalledWith(draft);
    },
  );

  describe("a turn listing several prompt commands", () => {
    const draft = "First /summary then /tone please /verify-answer";
    const sent = assemblePromptTurn(draft, [
      { command: "summary", promptId: "p-s", promptName: "Summary", from: 6, to: 14, text: "Summarise the document." },
      { command: "tone", promptId: "p-t", promptName: "Tone", from: 20, to: 25, text: "Use a formal tone." },
    ]);
    const promptBadges = () =>
      Array.from(container.querySelectorAll<HTMLButtonElement>("[data-skill-message] button[class*=command]"));

    it("shows one badge per prompt at its position, with the skill badge, and never the prompt text", () => {
      render(<UserTurn text={sent.text} command={sent.command} skillNames={["verify-answer"]} />);
      const body = container.querySelector("[data-skill-message]")!;
      expect(body.textContent).toBe("First edit_note/summary then edit_note/tone please verify-answer");
      expect(
        Array.from(body.querySelectorAll<HTMLElement>("[data-surface=bubble]")).map((badge) => badge.dataset.kind),
      ).toEqual(["prompt", "prompt", "skill"]);
      expect(promptBadges().map((badge) => badge.getAttribute("aria-label"))).toEqual([
        "chatbot.commandTurn.open",
        "chatbot.commandTurn.open",
      ]);
      expect(container.textContent).not.toContain("Summarise the document.");
      expect(container.textContent).not.toContain("Use a formal tone.");
    });

    it("opens each badge with its own place in the list", async () => {
      const onOpenCommand = vi.fn();
      render(<UserTurn text={sent.text} command={sent.command} onOpenCommand={onOpenCommand} />);
      await click(promptBadges()[1]);
      expect(onOpenCommand).toHaveBeenLastCalledWith({ text: sent.text, command: sent.command, promptIndex: 1 });
      await click(promptBadges()[0]);
      expect(onOpenCommand).toHaveBeenLastCalledWith({ text: sent.text, command: sent.command, promptIndex: 0 });
    });

    it("copies and edits the typed line", async () => {
      const onEdit = vi.fn();
      render(<UserTurn text={sent.text} command={sent.command} skillNames={["verify-answer"]} onEdit={onEdit} />);
      await click(copyButton());
      expect(writeText).toHaveBeenCalledWith(draft);
      await click(buttons()[0]);
      expect(onEdit).toHaveBeenCalledWith(draft);
      const range = document.createRange();
      range.selectNodeContents(container.querySelector("[data-skill-message]")!);
      expect(selectedSkillText(range, container)).toBe(draft);
    });

    it("shows the same command twice as two badges", () => {
      const line = "/summary of A, /summary of B";
      const twice = assemblePromptTurn(line, [
        { command: "summary", promptId: "p-s", promptName: "Summary", from: 0, to: 8, text: "Summarise." },
        { command: "summary", promptId: "p-s", promptName: "Summary", from: 15, to: 23, text: "Summarise." },
      ]);
      render(<UserTurn text={twice.text} command={twice.command} />);
      expect(container.querySelector("[data-skill-message]")!.textContent).toBe(
        "edit_note/summary of A, edit_note/summary of B",
      );
    });

    it("renders from the single fields when the list does not fit the stored text", async () => {
      const onOpenCommand = vi.fn();
      const command = {
        ...sent.command,
        prompts: sent.command.prompts!.map((entry) => ({ ...entry, text_offset: entry.text_offset + 500 })),
      };
      render(<UserTurn text={sent.text} command={command} onOpenCommand={onOpenCommand} />);
      expect(container.querySelector("[data-skill-message]")!.textContent).toBe(
        "First edit_note/summary then /tone please /verify-answer",
      );
      expect(promptBadges()).toHaveLength(1);
      await click(promptBadges()[0]);
      expect(onOpenCommand).toHaveBeenCalledWith({ text: sent.text, command });
      expect(onOpenCommand.mock.calls[0][0].promptIndex).toBeUndefined();
    });

    it("renders a turn stored with the single fields only as one badge", () => {
      const { prompts: _prompts, ...single } = sent.command;
      render(<UserTurn text={sent.text} command={single} />);
      expect(container.querySelector("[data-skill-message]")!.textContent).toBe(
        "First edit_note/summary then /tone please /verify-answer",
      );
    });
  });

  it("leaves an unattributed skill mention as ordinary text", () => {
    render(<UserTurn text="/skill verify-answer" />);
    expect(container.querySelector('[role="group"]')).toBeNull();
    expect(container.querySelector("p")?.textContent).toBe("/skill verify-answer");
  });

  it("opens the skill from a stored user message without copying or editing its request", async () => {
    const onOpenSkill = vi.fn();
    render(
      <UserTurn
        text="Notes"
        skillName="meeting-minutes"
        skillDescription="Prepare meeting minutes"
        onOpenSkill={onOpenSkill}
      />,
    );
    expect(container.querySelector<HTMLButtonElement>('[aria-label="chatbot.skills.open"]')!.title).toBe(
      "chatbot.skills.platformProvided\nPrepare meeting minutes",
    );
    await click(container.querySelector<HTMLButtonElement>('[aria-label="chatbot.skills.open"]')!);
    expect(onOpenSkill).toHaveBeenCalledOnce();
    expect(onOpenSkill).toHaveBeenCalledWith("meeting-minutes");
    expect(container.querySelector("[class*=skillTurn]")?.textContent).toBe("meeting-minutes Notes");
    expect(writeText).not.toHaveBeenCalled();
  });

  it("preserves the selection when a skill turn is edited", async () => {
    const onEdit = vi.fn();
    render(<UserTurn text="Notes" skillName="meeting-minutes" onEdit={onEdit} />);
    await click(buttons()[0]);
    expect(onEdit).toHaveBeenCalledWith("/meeting-minutes Notes");
  });

  it("renders only the copy action when no onEdit is supplied", () => {
    render(<UserTurn text="hello" />);
    expect(buttons()).toHaveLength(1);
    expect(iconOf(copyButton())).toBe("content_copy");
    expect(copyButton().getAttribute("aria-label")).toBe("chatbot.copyMessage.tooltip");
  });

  it("renders the edit action ahead of copy when onEdit is supplied", () => {
    const onEdit = vi.fn();
    render(<UserTurn text="hello" onEdit={onEdit} />);

    const [edit] = buttons();
    expect(buttons()).toHaveLength(2);
    expect(iconOf(edit)).toBe("edit");

    edit.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onEdit).toHaveBeenCalledWith("hello");
  });

  it("copies the message text and flips the button to a check for 2s", async () => {
    render(<UserTurn text="the question" />);

    await click(copyButton());
    expect(writeText).toHaveBeenCalledWith("the question");
    expect(iconOf(copyButton())).toBe("check");
    expect(copyButton().getAttribute("aria-label")).toBe("chatbot.copyMessage.copied");

    // Still confirming just before the 2s mark — same timing as AssistantTurn.
    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(iconOf(copyButton())).toBe("check");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(iconOf(copyButton())).toBe("content_copy");
  });

  it("restarts the full 2s window on a second click instead of letting the first timer cut it short", async () => {
    render(<UserTurn text="hello" />);

    await click(copyButton());
    act(() => {
      vi.advanceTimersByTime(1900);
    });

    // Second click 1.9s in: the first click's timer must not fire 100ms later.
    await click(copyButton());
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(iconOf(copyButton())).toBe("check");

    act(() => {
      vi.advanceTimersByTime(1900);
    });
    expect(iconOf(copyButton())).toBe("content_copy");
  });

  it("drops the pending revert on unmount rather than setting state on a dead turn", async () => {
    render(<UserTurn text="hello" />);
    await click(copyButton());

    act(() => {
      root.unmount();
    });
    // Assert BEFORE advancing: letting the timer fire would zero the count
    // either way and the test would pass without the cleanup effect.
    expect(vi.getTimerCount()).toBe(0);
    expect(() => vi.advanceTimersByTime(2000)).not.toThrow();

    // afterEach unmounts again; re-mount so it has a live root to tear down.
    render(<UserTurn text="hello" />);
  });

  it("stays silent when the clipboard write fails — the icon not flipping IS the feedback", async () => {
    writeText.mockRejectedValue(new Error("not allowed"));
    render(<UserTurn text="hello" />);

    await click(copyButton());
    expect(iconOf(copyButton())).toBe("content_copy");
  });

  // On a non-secure origin navigator.clipboard is undefined outright, so what
  // has to stay harmless is the property *access* — `.catch()` never sees a
  // synchronous TypeError. React swallows a throwing handler and reports it,
  // so neither the click nor a `.resolves.not.toThrow()` assertion observes
  // it; the reported error is what this pins.
  it("stays silent when navigator.clipboard is absent entirely", async () => {
    Object.defineProperty(globalThis.navigator, "clipboard", { value: undefined, configurable: true });
    const reported = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<UserTurn text="hello" />);

    await click(copyButton());

    expect(reported).not.toHaveBeenCalled();
    expect(iconOf(copyButton())).toBe("content_copy");
    reported.mockRestore();
  });
});
