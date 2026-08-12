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
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import { hitlResponseKey, reconstructPendingHitl, toThreadMessages } from "./toThreadMessages";

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
      // Answered (a hitl_response completes the exchange) — an UNanswered
      // trailing gate is a still-open confirmation, which toThreadMessages
      // deliberately omits from this per-exchange fold (reconstructPendingHitl
      // reconstructs it as the live, interactive prompt instead; see that
      // function's own describe block).
      msg({
        role: "user",
        channel: "hitl_response" as never,
        parts: [{ type: "hitl_response", choice_id: "yes", label: null } as never],
      }),
    ];

    const rows = toThreadMessages(messages, false);
    const user = rows.find((r) => r.role === "user");
    const hitl = rows.find((r) => r.role === "hitl_request");

    expect(user?.uiParts).toEqual([]);
    expect(hitl?.uiParts).toEqual([]);
  });
});

describe("hitlResponseKey", () => {
  it("maps the tool-approval gate's stable choice ids to i18n keys", () => {
    expect(hitlResponseKey("proceed")).toBe("rework.hitlPrompt.accepted");
    expect(hitlResponseKey("cancel")).toBe("rework.hitlPrompt.refused");
  });

  it("returns null for an unrecognized id, so the caller can fall back to raw text", () => {
    expect(hitlResponseKey("some_custom_choice")).toBeNull();
  });
});

// ── reconstructPendingHitl + toThreadMessages' "open gate" handling ──────────
// Reload-mid-confirmation bug: refreshing while a HITL gate was still open
// made the prompt vanish (live-only state) and left the gated tool stuck
// showing "running" with no way to answer it.

function hitlRequestMsg(eid: string, overrides: Record<string, unknown> = {}): ChatMessage {
  return msg({
    exchange_id: eid,
    role: "system",
    channel: "hitl_request" as never,
    parts: [
      {
        type: "hitl_request",
        question: "Extract requirements?",
        title: "Confirm",
        stage: "tool_approval",
        choices: [
          { id: "proceed", label: "Accepter" },
          { id: "cancel", label: "Refuser" },
        ],
        free_text: false,
        interrupt_id: "int-1",
        checkpoint_id: null,
        pending_calls: [{ tool_call_id: "call-1", tool_name: "extract_from_document", args_preview: "{}" }],
        ...overrides,
      } as never,
    ],
  });
}

function hitlResponseMsg(eid: string): ChatMessage {
  return msg({
    exchange_id: eid,
    role: "user",
    channel: "hitl_response" as never,
    parts: [{ type: "hitl_response", choice_id: "proceed", label: null } as never],
  });
}

describe("reconstructPendingHitl", () => {
  it("returns null for no messages", () => {
    expect(reconstructPendingHitl([])).toBeNull();
  });

  it("returns null when the last exchange has no hitl_request", () => {
    const messages = [msg({ exchange_id: "e1", channel: "final", parts: [{ type: "text", text: "hi" } as never] })];
    expect(reconstructPendingHitl(messages)).toBeNull();
  });

  it("returns null when the last exchange's gate was already answered", () => {
    const messages = [hitlRequestMsg("e1"), hitlResponseMsg("e1")];
    expect(reconstructPendingHitl(messages)).toBeNull();
  });

  it("reconstructs a full, resumable event for a still-open trailing gate", () => {
    const messages = [
      msg({ exchange_id: "e0", channel: "final", parts: [{ type: "text", text: "earlier turn" } as never] }),
      hitlRequestMsg("e1"),
    ];

    const event = reconstructPendingHitl(messages);

    expect(event).not.toBeNull();
    expect(event?.exchange_id).toBe("e1");
    expect(event?.payload.question).toBe("Extract requirements?");
    expect(event?.payload.choices).toEqual([
      { id: "proceed", label: "Accepter" },
      { id: "cancel", label: "Refuser" },
    ]);
    // The resume identity — without these, sendHitlResume cannot answer it.
    expect(event?.payload.interrupt_id).toBe("int-1");
    expect(event?.payload.pending_calls).toEqual([
      { tool_call_id: "call-1", tool_name: "extract_from_document", args_preview: "{}" },
    ]);
  });
});

describe("toThreadMessages — open HITL gate rendering", () => {
  it("still renders a readonly card for a PAST answered exchange", () => {
    const messages = [hitlRequestMsg("e1"), hitlResponseMsg("e1"), hitlRequestMsg("e2"), hitlResponseMsg("e2")];
    const rows = toThreadMessages(messages, false);
    expect(rows.filter((r) => r.role === "hitl_request")).toHaveLength(2);
  });

  it("omits the trailing UNANSWERED gate's readonly card (the live prompt renders it instead)", () => {
    const messages = [hitlRequestMsg("e1"), hitlResponseMsg("e1"), hitlRequestMsg("e2")];
    const rows = toThreadMessages(messages, false);
    // Only e1's (answered) card renders; e2's dangling one does not duplicate
    // the interactive prompt `reconstructPendingHitl` reconstructs for it.
    expect(rows.filter((r) => r.role === "hitl_request")).toHaveLength(1);
  });
});
