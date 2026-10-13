// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import type { CommandDescriptor, CommandPromptDescriptor, TurnCommand } from "../../slices/runtime/runtimeOpenApi";

/** Most prompt commands one message may hold. Mirrors `MAX_TURN_PROMPTS` in
 *  fred-sdk (`contracts/context.py`): the runtime refuses a longer list. */
export const MAX_TURN_PROMPTS = 16;

/** A prompt command of the typed line, with the text read from its library. */
export interface ResolvedPromptCommand {
  command: string;
  promptId: string;
  promptName: string;
  /** Position of the `/command` token in the typed line. */
  from: number;
  to: number;
  text: string;
}

/**
 * The text to send for a line holding prompt commands, and its descriptor.
 * Each command is replaced in place by its prompt; the list records where each
 * prompt's text sits, so the transcript can show one prompt on its own.
 */
export function assemblePromptTurn(
  draft: string,
  prompts: readonly ResolvedPromptCommand[],
): { text: string; command: TurnCommand } {
  const ordered = [...prompts].sort((a, b) => a.from - b.from);
  const own: string[] = [];
  const listed: NonNullable<TurnCommand["prompts"]> = [];
  let text = "";
  const push = (segment: string) => {
    const offset = text ? text.length + 2 : 0;
    text = text ? `${text}\n\n${segment}` : segment;
    return offset;
  };
  let cursor = 0;
  for (const prompt of ordered) {
    const before = draft.slice(cursor, prompt.from).trim();
    if (before) {
      own.push(before);
      push(before);
    }
    const body = prompt.text.trim();
    listed.push({
      command: prompt.command,
      prompt_id: prompt.promptId,
      prompt_name: prompt.promptName,
      draft_offset: prompt.from,
      text_offset: push(body),
      text_length: body.length,
    });
    cursor = prompt.to;
  }
  const after = draft.slice(cursor).trim();
  if (after) {
    own.push(after);
    push(after);
  }
  const first = ordered[0];
  const appended = own.join("\n\n");
  return {
    text,
    command: {
      command: first.command,
      ...(appended ? { appended_text: appended } : {}),
      prompt_id: first.promptId,
      prompt_name: first.promptName,
      draft_text: draft,
      draft_command_offset: first.from,
      prompts: listed,
    },
  };
}

/**
 * The prompt list of a stored descriptor, when it fits the turn it came with.
 * The list is client-supplied and unchecked by the runtime: one that does not
 * fit is ignored whole and the turn renders from the single fields.
 */
export function usablePromptList(
  command: CommandDescriptor | null | undefined,
  text: string,
): CommandPromptDescriptor[] | null {
  const list = command?.prompts;
  const draft = command?.draft_text;
  if (!Array.isArray(list) || !list.length || list.length > MAX_TURN_PROMPTS || typeof draft !== "string") return null;
  const index = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 0;
  let draftEnd = 0;
  let textEnd = 0;
  for (const entry of list) {
    if (typeof entry?.command !== "string" || !entry.command) return null;
    if (!index(entry.draft_offset) || !index(entry.text_offset) || !index(entry.text_length)) return null;
    if (entry.text_length < 1 || entry.draft_offset < draftEnd || entry.text_offset < textEnd) return null;
    if (!findSkillInvocations(draft, [entry.command]).some((token) => token.from === entry.draft_offset)) return null;
    draftEnd = entry.draft_offset + entry.command.length + 1;
    textEnd = entry.text_offset + entry.text_length;
    if (textEnd > text.length) return null;
  }
  return list;
}

/** Every `/name`-shaped word: a name delimited by whitespace or a text boundary. */
export function findCommandWords(value: string) {
  const result: { name: string; from: number; to: number }[] = [];
  for (const match of value.matchAll(/(?:^|\s)\/([a-z0-9_-]+)(?=\s|$)/g)) {
    const from = match.index + match[0].length - match[1].length - 1;
    result.push({ name: match[1], from, to: from + match[1].length + 1 });
  }
  return result;
}

/** The one rule for a token: `/name` at `from`, delimited on both sides by
 *  whitespace or a text boundary. A character glued to it makes it plain text. */
export function isCommandTokenAt(value: string, from: number, name: string): boolean {
  const to = from + name.length + 1;
  return (
    value.slice(from, to) === `/${name}` &&
    (from === 0 || /\s/.test(value[from - 1])) &&
    (to === value.length || /\s/.test(value[to]))
  );
}

/** Resolve only complete, whitespace-delimited names in the current catalog. */
export function findSkillInvocations(value: string, names: readonly string[], requireDelimiter = false) {
  return findCommandWords(value).filter(
    (word) => names.includes(word.name) && (!requireDelimiter || word.to < value.length),
  );
}

export function findSkillInvocation(value: string, names: readonly string[], requireDelimiter = false) {
  return findSkillInvocations(value, names, requireDelimiter)[0] ?? null;
}

/** Older turns stored the request separately from the skill's name. */
export function skillInvocationText(text: string, name?: string | null): string {
  if (!name) return text;
  const legacy = `/skill ${name}`;
  if (text === legacy || text.startsWith(legacy + " ") || text.startsWith(legacy + "\n"))
    return `/${name}${text.slice(legacy.length)}`;
  if (findSkillInvocation(text, [name])) return text;
  return `/${name}${text ? " " + text : ""}`;
}

/** Reconstruct mixed legacy turns from their descriptors; canonical drafts win. */
export function skillInvocationsText(
  text: string,
  names: readonly string[],
  command?: CommandDescriptor | null,
): string {
  if (command?.draft_text != null) return command.draft_text;
  if (command && names.length) {
    const request = skillInvocationsText(command.appended_text ?? "", names);
    return `/${command.command}${request ? " " + request : ""}`;
  }
  return [...names].reverse().reduce((value, name) => skillInvocationText(value, name), text);
}

/** Badges show `/name` as text. A selection touching one is still serialised
 * here: the browser would copy icon glyphs as words and break lines around the
 * badge's flex box. */
export function selectedSkillText(range: Range, container: HTMLElement): string | null {
  if (!container.contains(range.commonAncestorContainer)) return null;
  const regionOf = (node: Node) =>
    (node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement)?.closest("[data-skill-message]");
  const region = regionOf(range.startContainer);
  // Cross-turn selections keep the browser's block-boundary serialisation.
  if (!region || region !== regionOf(range.endContainer)) return null;
  const fragment = range.cloneContents();
  fragment.querySelectorAll('.material-symbols-outlined[aria-hidden="true"]').forEach((icon) => icon.remove());
  const text = fragment.textContent ?? "";
  const touchesBadge = Array.from(region.querySelectorAll("[data-skill-name]")).some((label) =>
    range.intersectsNode(label),
  );
  return touchesBadge || text !== range.toString() ? text : null;
}
