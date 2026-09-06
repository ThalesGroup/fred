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

// A line diff for the wiki's approval modal (WIKI-04).
//
// Written here rather than pulled from a package: the only thing this screen
// needs is "which lines did the agent add, remove or leave alone", a wiki page
// is small by construction, and `diff` is only in the tree transitively today.

export type DiffOp = "same" | "added" | "removed";

/**
 * Above this many table cells, the line-by-line pass is abandoned.
 *
 * The table is O(lines × lines): a page allowed 100 000 characters can be tens
 * of thousands of lines, and 12 000 a side is already ~144 million cells —
 * enough to freeze or kill the tab of the person deciding. Two thousand lines
 * a side is far beyond any page a team writes by hand, and the fallback below
 * still shows the whole change, just without pairing.
 */
const MAX_DIFF_CELLS = 4_000_000;

export interface DiffLine {
  op: DiffOp;
  text: string;
}

/** Longest common subsequence of two line arrays, as an index-pair list. */
function lcsPairs(a: readonly string[], b: readonly string[]): [number, number][] {
  // Classic dynamic-programming table. A wiki page is capped at 100 000
  // characters, so the worst realistic input is a few thousand lines a side —
  // well inside what one table costs on a modal that opens on a click.
  const table: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const pairs: [number, number][] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      pairs.push([i, j]);
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }
  return pairs;
}

/**
 * The line-by-line difference from `before` to `after`.
 *
 * Removals come before the additions that replace them, so a changed line
 * reads as one pair rather than two unrelated edits several lines apart.
 */
export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.length === 0 ? [] : before.split("\n");
  const b = after.length === 0 ? [] : after.split("\n");

  if (a.length * b.length > MAX_DIFF_CELLS) {
    // Everything out, everything in. Coarse, but it is the whole change and it
    // renders — where the pairing pass would have taken the tab down with it.
    return [
      ...a.map((text): DiffLine => ({ op: "removed", text })),
      ...b.map((text): DiffLine => ({ op: "added", text })),
    ];
  }

  const pairs = lcsPairs(a, b);

  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  const flush = (untilA: number, untilB: number) => {
    for (; i < untilA; i++) out.push({ op: "removed", text: a[i] });
    for (; j < untilB; j++) out.push({ op: "added", text: b[j] });
  };
  for (const [ai, bj] of pairs) {
    flush(ai, bj);
    out.push({ op: "same", text: a[ai] });
    i = ai + 1;
    j = bj + 1;
  }
  flush(a.length, b.length);
  return out;
}

/** How many lines the change touches, for a one-line summary. */
export function diffStat(lines: readonly DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.op === "added").length,
    removed: lines.filter((l) => l.op === "removed").length,
  };
}
