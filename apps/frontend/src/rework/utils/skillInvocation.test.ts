// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import { describe, expect, it } from "vitest";
import type { CommandDescriptor } from "../../slices/runtime/runtimeOpenApi";
import {
  assemblePromptTurn,
  findCommandWords,
  isCommandTokenAt,
  MAX_TURN_PROMPTS,
  usablePromptList,
  type ResolvedPromptCommand,
} from "./skillInvocation";

const prompt = (
  draft: string,
  command: string,
  text: string,
  occurrence = 0,
  id = `id-${command}`,
): ResolvedPromptCommand => {
  let from = -1;
  for (let i = 0; i <= occurrence; i++) from = draft.indexOf(`/${command}`, from + 1);
  return { command, promptId: id, promptName: `Name of ${command}`, from, to: from + command.length + 1, text };
};

/** What the single-prompt composer sent before the list existed. */
function legacyTurn(draft: string, resolved: ResolvedPromptCommand) {
  const before = draft.slice(0, resolved.from).trim();
  const after = draft.slice(resolved.to).trim();
  const appended = [before, after].filter(Boolean).join("\n\n");
  return {
    text: [before, resolved.text.trim(), after].filter(Boolean).join("\n\n"),
    command: {
      command: resolved.command,
      ...(appended ? { appended_text: appended } : {}),
      prompt_id: resolved.promptId,
      prompt_name: resolved.promptName,
      draft_text: draft,
      draft_command_offset: resolved.from,
    },
  };
}

describe("assemblePromptTurn", () => {
  it.each([
    ["/summary", "Summarise the document."],
    ["/summary the report", "  Summarise the document.\n"],
    ["First /summary", "Summarise."],
    ["  Before\n/summary   after it  ", "Line one.\n\nLine two."],
  ])("sends for one prompt exactly the text and single fields of a single-prompt turn: %j", (draft, text) => {
    const resolved = prompt(draft, "summary", text);
    const { text: sent, command } = assemblePromptTurn(draft, [resolved]);
    const legacy = legacyTurn(draft, resolved);
    const { prompts, ...single } = command;

    expect(sent).toBe(legacy.text);
    expect(single).toEqual(legacy.command);
    expect(prompts).toHaveLength(1);
    expect(sent.slice(prompts![0].text_offset, prompts![0].text_offset + prompts![0].text_length)).toBe(text.trim());
  });

  it("expands two prompts in place, in the order of the line", () => {
    const draft = "First /summary then /tone please";
    const { text, command } = assemblePromptTurn(draft, [
      prompt(draft, "tone", "Use a formal tone."),
      prompt(draft, "summary", "Summarise the document."),
    ]);

    expect(text).toBe("First\n\nSummarise the document.\n\nthen\n\nUse a formal tone.\n\nplease");
    expect(command).toEqual({
      command: "summary",
      appended_text: "First\n\nthen\n\nplease",
      prompt_id: "id-summary",
      prompt_name: "Name of summary",
      draft_text: draft,
      draft_command_offset: 6,
      prompts: [
        {
          command: "summary",
          prompt_id: "id-summary",
          prompt_name: "Name of summary",
          draft_offset: 6,
          text_offset: 7,
          text_length: 23,
        },
        {
          command: "tone",
          prompt_id: "id-tone",
          prompt_name: "Name of tone",
          draft_offset: 20,
          text_offset: 38,
          text_length: 18,
        },
      ],
    });
    expect(usablePromptList(command, text)).toBe(command.prompts);
  });

  it("expands a repeated command at each occurrence", () => {
    const draft = "/summary of A, /summary of B";
    const { text, command } = assemblePromptTurn(draft, [
      prompt(draft, "summary", "Summarise the document."),
      prompt(draft, "summary", "Summarise the document.", 1),
    ]);

    expect(text).toBe("Summarise the document.\n\nof A,\n\nSummarise the document.\n\nof B");
    expect(command.appended_text).toBe("of A,\n\nof B");
    expect(
      command.prompts?.map((entry) => text.slice(entry.text_offset, entry.text_offset + entry.text_length)),
    ).toEqual(["Summarise the document.", "Summarise the document."]);
    expect(command.prompts?.map((entry) => entry.draft_offset)).toEqual([0, 15]);
  });

  it("leaves no appended text when the line holds only commands", () => {
    const draft = "/summary /tone";
    const { text, command } = assemblePromptTurn(draft, [prompt(draft, "summary", "A."), prompt(draft, "tone", "B.")]);

    expect(text).toBe("A.\n\nB.");
    expect(command).not.toHaveProperty("appended_text");
  });

  it("counts positions as string indices when a prompt holds an emoji", () => {
    const draft = "Bonjour 👋 /summary puis /tone merci";
    const { text, command } = assemblePromptTurn(draft, [
      prompt(draft, "summary", "Résume 📄 le document."),
      prompt(draft, "tone", "Ton formel 🎩."),
    ]);

    const [summary, tone] = command.prompts!;
    expect(draft.slice(summary.draft_offset, summary.draft_offset + 8)).toBe("/summary");
    expect(draft.slice(tone.draft_offset, tone.draft_offset + 5)).toBe("/tone");
    expect(text.slice(summary.text_offset, summary.text_offset + summary.text_length)).toBe("Résume 📄 le document.");
    expect(text.slice(tone.text_offset, tone.text_offset + tone.text_length)).toBe("Ton formel 🎩.");
    expect(usablePromptList(command, text)).toHaveLength(2);
  });
});

describe("assemblePromptTurn with line breaks", () => {
  it("keeps the line breaks of a prompt as stored, and its slice still reads back", () => {
    const draft = "Avant\r\n/summary ensuite";
    const body = "Ligne un.\r\n\r\nLigne deux.";
    const { text, command } = assemblePromptTurn(draft, [prompt(draft, "summary", `${body}\r\n`)]);
    const [entry] = command.prompts!;

    expect(text).toBe(`Avant\n\n${body}\n\nensuite`);
    expect(entry.draft_offset).toBe(7);
    expect(text.slice(entry.text_offset, entry.text_offset + entry.text_length)).toBe(body);
    expect(usablePromptList(command, text)).toHaveLength(1);
  });
});

describe("command words", () => {
  it("finds every delimited /name, and nothing inside a path or a word", () => {
    const value = "/one see /etc/hosts a/b\n/two\t/three-3 /Four /five";
    expect(findCommandWords(value).map((word) => [word.name, value.slice(word.from, word.to)])).toEqual([
      ["one", "/one"],
      ["two", "/two"],
      ["three-3", "/three-3"],
      ["five", "/five"],
    ]);
  });

  it.each([
    ["/sum", 0, true],
    ["a /sum b", 2, true],
    ["a\n/sum\tb", 2, true],
    ["/summary", 0, false],
    ["x/sum", 1, false],
    ["a /sum. b", 2, false],
    ["a /su b", 2, false],
  ])("reads %j at %i as a token of /sum: %s", (value, from, expected) => {
    expect(isCommandTokenAt(value, from, "sum")).toBe(expected);
  });
});

describe("usablePromptList", () => {
  const draft = "First /summary then /tone please";
  const sent = assemblePromptTurn(draft, [
    prompt(draft, "summary", "Summarise the document."),
    prompt(draft, "tone", "Use a formal tone."),
  ]);
  const withList = (prompts: unknown, over: Partial<CommandDescriptor> = {}) =>
    ({ ...sent.command, ...over, prompts }) as CommandDescriptor;
  const [first, second] = sent.command.prompts!;

  it("returns nothing for a descriptor that has only the single fields", () => {
    const { prompts: _prompts, ...single } = sent.command;
    expect(usablePromptList(single, sent.text)).toBeNull();
    expect(usablePromptList(null, sent.text)).toBeNull();
  });

  it.each([
    ["empty", []],
    ["not a list", { 0: first }],
    ["unsorted", [second, first]],
    ["overlapping in the text", [first, { ...second, text_offset: first.text_offset + 3 }]],
    ["the same position twice in the line", [first, { ...second, command: "summary", draft_offset: 6 }]],
    ["outside the text", [first, { ...second, text_length: 500 }]],
    ["an empty slice", [{ ...first, text_length: 0 }, second]],
    ["a negative position", [{ ...first, text_offset: -1 }, second]],
    ["a position that is not an integer", [{ ...first, draft_offset: "6" }, second]],
    ["a command that is not at its position in the line", [first, { ...second, draft_offset: 21 }]],
    ["a command that is not the one typed there", [first, { ...second, command: "ton" }]],
    ["an entry without a command", [first, { ...second, command: "" }]],
    ["holding an entry that is null", [first, null]],
    ["holding an entry that is not an object", [first, "tone"]],
  ])("refuses a list that is %s", (_label, prompts) => {
    expect(usablePromptList(withList(prompts), sent.text)).toBeNull();
  });

  it("refuses a list longer than the limit", () => {
    const line = Array.from({ length: MAX_TURN_PROMPTS + 1 }, () => "/summary").join(" ");
    const many = assemblePromptTurn(
      line,
      Array.from({ length: MAX_TURN_PROMPTS + 1 }, (_, index) => prompt(line, "summary", "S.", index)),
    );
    expect(usablePromptList(many.command, many.text)).toBeNull();
  });

  it("refuses a list whose command has a character glued to it in the typed line", () => {
    for (const glued of ["First /summaryx then /tone please", "First x/summary then /tone please"])
      expect(usablePromptList(withList([first, second], { draft_text: glued }), sent.text)).toBeNull();
  });

  it("refuses a list when the typed line was not stored", () => {
    expect(usablePromptList(withList([first, second], { draft_text: null }), sent.text)).toBeNull();
  });
});
