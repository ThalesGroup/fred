// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import type { CommandDescriptor } from "../../slices/runtime/runtimeOpenApi";

/** Resolve only complete, whitespace-delimited names in the current catalog. */
export function findSkillInvocations(value: string, names: readonly string[], requireDelimiter = false) {
  const result: { name: string; from: number; to: number }[] = [];
  const tokens = value.matchAll(/(?:^|\s)\/([a-z0-9_-]+)(?=\s|$)/g);
  for (const match of tokens) {
    const from = match.index + match[0].length - match[1].length - 1;
    const to = from + match[1].length + 1;
    if (names.includes(match[1]) && (!requireDelimiter || to < value.length)) result.push({ name: match[1], from, to });
  }
  return result;
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

/** Displayed names omit the slash; native selection-copy restores it only
 * for complete selected badges, leaving partial names and prose unchanged. */
export function selectedSkillText(range: Range, container: HTMLElement): string | null {
  if (!container.contains(range.commonAncestorContainer)) return null;
  const regionOf = (node: Node) =>
    (node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement)?.closest("[data-skill-message]");
  const region = regionOf(range.startContainer);
  // Cross-turn selections keep the browser's block-boundary serialisation.
  if (!region || region !== regionOf(range.endContainer)) return null;
  const selectedText = (selection: Range) => {
    const fragment = selection.cloneContents();
    fragment.querySelectorAll('.material-symbols-outlined[aria-hidden="true"]').forEach((icon) => icon.remove());
    return fragment.textContent ?? "";
  };
  const replacements: { from: number; to: number; text: string }[] = [];
  for (const label of region.querySelectorAll<HTMLElement>("[data-skill-name]")) {
    const name = label.dataset.skillName;
    if (!name || !label.firstChild || !range.intersectsNode(label)) continue;
    const nameRange = document.createRange();
    nameRange.selectNodeContents(label.firstChild);
    if (
      range.compareBoundaryPoints(Range.START_TO_START, nameRange) > 0 ||
      range.compareBoundaryPoints(Range.END_TO_END, nameRange) < 0
    )
      continue;
    const prefix = range.cloneRange();
    prefix.setEnd(nameRange.startContainer, nameRange.startOffset);
    const from = selectedText(prefix).length;
    replacements.push({ from, to: from + name.length, text: `/${name}` });
  }
  let text = selectedText(range);
  if (!replacements.length && text === range.toString()) return null;
  for (const replacement of replacements.sort((a, b) => b.from - a.from))
    text = text.slice(0, replacement.from) + replacement.text + text.slice(replacement.to);
  return text;
}
