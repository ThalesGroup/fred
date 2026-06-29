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

import { describe, it, expect, vi } from "vitest";
import { mergeContextPromptText, parseSseFrames } from "./runtimeStream";

// Build a ReadableStream<Uint8Array> from string chunks, mirroring how a fetch
// body delivers SSE bytes (chunk boundaries do not respect frame boundaries).
function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

async function collect<T>(gen: AsyncGenerator<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const frame of gen) out.push(frame);
  return out;
}

describe("parseSseFrames", () => {
  it("yields the parsed JSON of each data frame", async () => {
    const frames = await collect(parseSseFrames(streamOf('data: {"kind":"a"}\n\ndata: {"kind":"b"}\n\n')));
    expect(frames).toEqual([{ kind: "a" }, { kind: "b" }]);
  });

  it("reassembles a frame split across read() chunks", async () => {
    const frames = await collect(parseSseFrames(streamOf('data: {"k', '":1}\n', "\n")));
    expect(frames).toEqual([{ k: 1 }]);
  });

  it("skips [DONE] sentinels and empty frames", async () => {
    const frames = await collect(parseSseFrames(streamOf('data: {"k":1}\n\ndata: [DONE]\n\n\n\n')));
    expect(frames).toEqual([{ k: 1 }]);
  });

  it("ignores non-data lines such as comments and heartbeats", async () => {
    const frames = await collect(parseSseFrames(streamOf(': keep-alive\n\ndata: {"k":1}\n\n')));
    expect(frames).toEqual([{ k: 1 }]);
  });

  it("reports malformed JSON via onParseError and keeps going", async () => {
    const onParseError = vi.fn();
    const frames = await collect(parseSseFrames(streamOf('data: {not json\n\ndata: {"k":2}\n\n'), onParseError));
    expect(frames).toEqual([{ k: 2 }]);
    expect(onParseError).toHaveBeenCalledTimes(1);
    expect(onParseError).toHaveBeenCalledWith("{not json");
  });

  it("swallows malformed JSON silently when no handler is given", async () => {
    const frames = await collect(parseSseFrames(streamOf("data: {bad\n\n")));
    expect(frames).toEqual([]);
  });
});

describe("mergeContextPromptText", () => {
  it("adds context_prompt_text when a value is present", () => {
    expect(mergeContextPromptText({ search_policy: "hybrid" }, "PROMPT")).toEqual({
      search_policy: "hybrid",
      context_prompt_text: "PROMPT",
    });
  });

  it("omits the key when the prompt is null or undefined", () => {
    expect(mergeContextPromptText({ search_policy: "hybrid" }, null)).toEqual({ search_policy: "hybrid" });
    expect(mergeContextPromptText({ search_policy: "hybrid" }, undefined)).toEqual({ search_policy: "hybrid" });
  });

  it("keeps an empty-string prompt (only null/undefined are dropped)", () => {
    expect(mergeContextPromptText({}, "")).toEqual({ context_prompt_text: "" });
  });
});
