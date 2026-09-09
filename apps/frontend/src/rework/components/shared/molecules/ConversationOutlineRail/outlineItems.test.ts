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

import { describe, expect, it } from "vitest";
import type { ThreadMessage } from "@rework/types/thread";
import { firstSentences, sameTurnIds, toOutlinePreview, toTurnIds } from "./outlineItems";

function msg(id: string, role: ThreadMessage["role"], text: string): ThreadMessage {
  return { id, role, text, isStreaming: false, traceMessages: [], sources: [], uiParts: [] };
}

describe("toTurnIds", () => {
  it("emits one id per user turn, in thread order", () => {
    expect(
      toTurnIds([
        msg("u1", "user", "first"),
        msg("a1", "assistant", "answer"),
        msg("u2", "user", "second"),
        msg("a2", "assistant", "answer"),
      ]),
    ).toEqual(["u1", "u2"]);
  });

  it("emits a turn that has no answer yet", () => {
    // Every mark is the same size, so a turn still being answered is no
    // different from any other — it just has nothing to preview.
    expect(toTurnIds([msg("u", "user", "q")])).toEqual(["u"]);
  });

  it("gives HITL rows no marks of their own", () => {
    expect(
      toTurnIds([
        msg("u1", "user", "q"),
        msg("h1", "hitl_request", "may I?"),
        msg("h2", "hitl_response", "proceed"),
        msg("a1", "assistant", "done"),
      ]),
    ).toEqual(["u1"]);
  });
});

describe("sameTurnIds", () => {
  // Identity of the fold's result is what keeps the rail's memo alive while a
  // turn streams, so equality has to notice every change the rail renders.
  it("treats the same turns as unchanged", () => {
    expect(sameTurnIds(["u1", "u2"], ["u1", "u2"])).toBe(true);
  });

  it("notices a new turn", () => {
    expect(sameTurnIds(["u1", "u2"], ["u1", "u2", "u3"])).toBe(false);
  });

  it("notices a different conversation of the same length", () => {
    // The staleness a session-plus-count cache key could not see.
    expect(sameTurnIds(["u1", "u2"], ["x1", "u2"])).toBe(false);
  });
});

describe("firstSentences", () => {
  it("stops after the requested number of sentences", () => {
    expect(firstSentences("One. Two. Three.", 2)).toBe("One. Two.");
  });

  it("does not split on a terminator with no whitespace after it", () => {
    // Decimals and version numbers are the common case; splitting here would
    // reduce the preview to a fragment.
    expect(firstSentences("Version 1.5 shipped. Next.", 1)).toBe("Version 1.5 shipped.");
  });

  it("keeps a sentence that ends the text", () => {
    // The common shape — an answer ends with a full stop and no trailing
    // whitespace. Requiring whitespace after the terminator dropped that last
    // sentence from almost every preview.
    expect(firstSentences("Yes. And also more detail follows here.", 2)).toBe(
      "Yes. And also more detail follows here.",
    );
    expect(firstSentences("Only one sentence.", 2)).toBe("Only one sentence.");
  });

  it("returns the text when it holds no sentence terminator", () => {
    expect(firstSentences("a title with no full stop", 2)).toBe("a title with no full stop");
  });

  it("strips markdown rather than showing its punctuation", () => {
    expect(firstSentences("## Heading\n- **bold** and `code` and [link](http://x)", 2)).toBe(
      "Heading bold and code and link",
    );
  });

  it("drops a fenced code block, closed or still open", () => {
    expect(firstSentences("Intro. ```js\nconst a = 1;\n```", 2)).toBe("Intro.");
    expect(firstSentences("Intro. ```js\nconst a = 1;", 2)).toBe("Intro.");
  });

  it("reads a bounded slice however long the answer is", () => {
    // The whole point of the bound: cost must not scale with the answer.
    const huge = `${"x".repeat(400)}. ${"tail. ".repeat(20000)}`;
    expect(firstSentences(huge, 2).length).toBeLessThanOrEqual(500);
  });

  it("returns empty for empty input", () => {
    expect(firstSentences("", 2)).toBe("");
  });
});

describe("toOutlinePreview", () => {
  it("pairs the turn's request with its own answer", () => {
    const preview = toOutlinePreview(
      [
        msg("u1", "user", "What is it? Second question."),
        msg("a1", "assistant", "It is that. Because of this. And more."),
        msg("u2", "user", "Other"),
      ],
      "u1",
    );
    expect(preview.request).toBe("What is it?");
    expect(preview.answer).toBe("It is that. Because of this.");
  });

  it("returns empty strings for an unknown turn", () => {
    expect(toOutlinePreview([msg("u1", "user", "q")], "nope")).toEqual({ request: "", answer: "" });
  });

  it("returns an empty answer for a turn still without one", () => {
    expect(toOutlinePreview([msg("u1", "user", "Question.")], "u1")).toEqual({
      request: "Question.",
      answer: "",
    });
  });
});
