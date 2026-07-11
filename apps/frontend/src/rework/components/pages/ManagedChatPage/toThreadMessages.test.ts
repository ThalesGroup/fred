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

// ThreadMessage raw-part retention (#1977): the fold must carry EVERY ui_part
// (link, geo, capability kinds, unknown kinds) — pre-folding per kind was
// lossy and is the exact regression this suite pins against.

import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../../../../slices/agentic/agenticOpenApi";
import { toThreadMessages } from "./toThreadMessages";

function msg(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    exchange_id: "e1",
    session_id: "s1",
    rank: 0,
    timestamp: "2026-07-10T00:00:00Z",
    role: "assistant",
    channel: "final",
    parts: [],
    metadata: {},
    ...overrides,
  } as ChatMessage;
}

const LINK = { type: "link", href: "https://example.test/report.pdf", title: "Report" };
const GEO = { type: "geo", geojson: { type: "FeatureCollection", features: [] } };
const DEMO_CARD = { type: "demo_card", title: "Demo echo", body: "HELLO" };
const UNKNOWN = { type: "part_kind_from_the_future", payload: { x: 1 } };

describe("toThreadMessages — raw ui_part retention (#1977)", () => {
  it("keeps link, geo, capability, and unknown parts on the assistant row", () => {
    const messages = [
      msg({ role: "user", channel: "final", parts: [{ type: "text", text: "hi" } as never] }),
      msg({
        parts: [
          { type: "text", text: "done" } as never,
          LINK as never,
          GEO as never,
          DEMO_CARD as never,
          UNKNOWN as never,
        ],
      }),
    ];

    const [, assistant] = toThreadMessages(messages, false);

    expect(assistant.role).toBe("assistant");
    expect(assistant.text).toBe("done");
    expect(assistant.uiParts).toEqual([LINK, GEO, DEMO_CARD, UNKNOWN]);
  });

  it("excludes message-body part kinds from uiParts", () => {
    const messages = [
      msg({
        parts: [
          { type: "text", text: "answer" } as never,
          { type: "tool_call", tool_call_id: "c1" } as never,
          { type: "tool_result", tool_call_id: "c1", content: "ok" } as never,
          LINK as never,
        ],
      }),
    ];

    const [assistant] = toThreadMessages(messages, false);

    expect(assistant.uiParts).toEqual([LINK]);
  });

  it("collects parts across several final messages of one exchange", () => {
    const messages = [msg({ rank: 1, parts: [LINK as never] }), msg({ rank: 2, parts: [DEMO_CARD as never] })];

    const [assistant] = toThreadMessages(messages, false);

    expect(assistant.uiParts).toEqual([LINK, DEMO_CARD]);
  });

  it("leaves user and HITL rows with empty uiParts", () => {
    const messages = [
      msg({ role: "user", parts: [{ type: "text", text: "question" } as never] }),
      msg({
        channel: "hitl_request" as never,
        parts: [{ type: "hitl_request", question: "sure?", choices: [] } as never],
      }),
    ];

    const rows = toThreadMessages(messages, false);
    const user = rows.find((r) => r.role === "user");
    const hitl = rows.find((r) => r.role === "hitl_request");

    expect(user?.uiParts).toEqual([]);
    expect(hitl?.uiParts).toEqual([]);
  });
});
