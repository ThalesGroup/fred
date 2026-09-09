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

// Pure folds behind the conversation outline rail: the thread's messages to
// one mark per exchange, and a turn's raw text to the two lines its hover tile
// shows. Kept free of React and DOM so the boundaries that actually matter —
// the height buckets, sentence splitting — are unit-testable.

import type { ThreadMessage } from "@rework/types/thread";

export interface OutlinePreview {
  request: string;
  answer: string;
}

/** Sentence detection reads this many characters, never the whole answer — an
 *  answer can be tens of kilobytes, and the tile shows two sentences. */
const PREVIEW_SCAN_CHARS = 500;

/**
 * One mark per user-opened exchange, in thread order — the turn ids, which are
 * also the `data-turn-id` anchors in the thread.
 *
 * Every mark is the same size: the rail says where the turns are, and nothing
 * about them. Encoding the answer's length in a mark's height was tried and
 * dropped — it made the rail a second thing to read rather than a place to aim.
 *
 * HITL rows are skipped rather than given marks of their own: `hitl_response`
 * renders through `UserTurn` but is a reply to the agent, not a turn the reader
 * would navigate back to.
 */
export function toTurnIds(messages: ThreadMessage[]): string[] {
  const ids: string[] = [];
  for (const message of messages) {
    if (message.role === "user") ids.push(message.id);
  }
  return ids;
}

/**
 * Whether two folds describe the same rail.
 *
 * Lets the caller hand back the previous array when nothing changed, keeping
 * its identity stable so the rail's `memo` holds. That matters because the
 * message list is replaced on every streamed token: without this the rail
 * would re-render every mark tens of times a second, and with a coarser cache
 * key than the messages themselves it would instead go stale — a session
 * switch between two conversations of equal length would leave the previous
 * one's marks on screen.
 */
export function sameTurnIds(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id, i) => id === b[i]);
}

/**
 * Strip the markdown that would otherwise show up as punctuation in a preview
 * line. Deliberately shallow — this runs on a 500-character slice to produce
 * two lines of plain text, not to render anything.
 */
function toPlainText(text: string): string {
  return text
    .replace(/```[\s\S]*?(```|$)/g, " ") // fenced code, closed or still open
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1") // links and images keep their label
    .replace(/^\s{0,3}(#{1,6}|>|[-*+]|\d+[.)])\s+/gm, "") // headings, quotes, list markers
    .replace(/[*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The first `count` sentences of `text`, as one line.
 *
 * Returns the whole scanned slice when no terminator is found — a preview that
 * is one long unpunctuated line is still worth showing, and the tile clamps it
 * to its line budget anyway.
 */
export function firstSentences(text: string, count: number): string {
  const plain = toPlainText(text.slice(0, PREVIEW_SCAN_CHARS));
  if (!plain) return "";

  const sentences: string[] = [];
  // A terminator ends a sentence only at whitespace or the end of the text, so
  // decimals and abbreviations mid-line don't split the preview into fragments.
  // The `$` is not decoration: without it the last sentence of a short answer —
  // which is most answers — has no whitespace after its full stop and is
  // silently dropped from the preview.
  const terminator = /[.!?]+(?=\s|$)/g;
  let start = 0;
  let match: RegExpExecArray | null;
  while (sentences.length < count && (match = terminator.exec(plain)) !== null) {
    // Trimmed: the slice starts at the previous terminator, so it carries the
    // separating space, which the join would then double.
    sentences.push(plain.slice(start, match.index + match[0].length).trim());
    start = match.index + match[0].length;
  }
  if (sentences.length === 0) return plain;
  return sentences.join(" ").trim();
}

/** The hover tile's two lines. Computed on hover for the hovered turn only:
 *  during streaming the message list changes on every token, so deriving this
 *  for every turn up front is string work across the whole conversation tens of
 *  times a second — the shape that already cost the composer its typing speed. */
export function toOutlinePreview(messages: ThreadMessage[], turnId: string): OutlinePreview {
  const index = messages.findIndex((m) => m.id === turnId);
  if (index === -1) return { request: "", answer: "" };

  let answer = "";
  for (let j = index + 1; j < messages.length && messages[j].role !== "user"; j++) {
    if (messages[j].role === "assistant") {
      answer = messages[j].text;
      break;
    }
  }
  return {
    request: firstSentences(messages[index].text, 1),
    answer: firstSentences(answer, 2),
  };
}
