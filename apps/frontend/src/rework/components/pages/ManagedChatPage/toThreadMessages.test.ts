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
import { groupTraceEntries, isCancelledByUser, traceSummary } from "../../../utils/traceUtils";
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

function hitlRequestMsg(eid: string, overrides: Record<string, unknown> = {}, rank = 0): ChatMessage {
  return msg({
    exchange_id: eid,
    rank,
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
        pending_calls: [{ tool_call_id: "call-1", tool_name: "extract_from_document", args_preview: "{}" }],
        ...overrides,
      } as never,
    ],
  });
}

function hitlResponseMsg(eid: string, overrides: Record<string, unknown> = {}, rank = 0): ChatMessage {
  return msg({
    exchange_id: eid,
    rank,
    role: "user",
    channel: "hitl_response" as never,
    parts: [{ type: "hitl_response", choice_id: "proceed", label: null, ...overrides } as never],
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

describe("toThreadMessages pause metadata", () => {
  it("retains pre-pause sources, UI parts, and usage after the answer resumes", () => {
    const source = { uid: "source-1", title: "Guide", content: "Evidence", score: 1 } as never;
    const toolCall = msg({
      rank: 1,
      channel: "tool_call",
      parts: [{ type: "tool_call", call_id: "call-1", name: "search", args: {} } as never],
    });
    const pauseMetadata = msg({
      rank: 2,
      role: "system",
      channel: "system_note",
      parts: [],
      metadata: {
        extras: { pause_metadata: true },
        sources: [source],
        ui_parts: [LINK],
        model: "test-model",
        token_usage: { input_tokens: 230, output_tokens: 30, total_tokens: 260 },
        context_tokens: 130,
      },
    });
    const request = hitlRequestMsg("e1", { occurrence_id: "call-1" }, 3);

    const open = toThreadMessages([toolCall, pauseMetadata, request], false).find((row) => row.role === "assistant");
    expect(open?.sources).toEqual([source]);
    expect(open?.uiParts).toEqual([LINK]);
    expect(open?.tokenUsage?.total_tokens).toBe(260);

    const final = msg({
      rank: 5,
      parts: [{ type: "text", text: "Done" } as never],
      metadata: {
        token_usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
        context_tokens: 140,
      },
    });
    const resumed = toThreadMessages(
      [toolCall, pauseMetadata, request, hitlResponseMsg("e1", { occurrence_id: "call-1" }, 4), final],
      false,
    ).find((row) => row.role === "assistant");
    expect(resumed?.text).toBe("Done");
    expect(resumed?.sources).toEqual([source]);
    expect(resumed?.uiParts).toEqual([LINK]);
    expect(resumed?.tokenUsage).toEqual({ input_tokens: 240, output_tokens: 35, total_tokens: 275 });
    expect(resumed?.contextTokens).toBe(140);
  });

  it("reads metadata from a previously persisted HITL request row", () => {
    const source = { uid: "legacy-source", title: "Guide", content: "Evidence", score: 1 } as never;
    const request = {
      ...hitlRequestMsg("e1", { occurrence_id: "legacy-question" }, 1),
      metadata: {
        sources: [source],
        ui_parts: [LINK],
        token_usage: { input_tokens: 100, output_tokens: 20, total_tokens: 120 },
        context_tokens: 100,
      },
    } as ChatMessage;
    const final = msg({
      rank: 2,
      parts: [{ type: "text", text: "Done" } as never],
      metadata: { token_usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 }, context_tokens: 110 },
    });

    const assistant = toThreadMessages([request, final], false).find((row) => row.role === "assistant");
    expect(assistant?.text).toBe("Done");
    expect(assistant?.sources).toEqual([source]);
    expect(assistant?.uiParts).toEqual([LINK]);
    expect(assistant?.tokenUsage?.total_tokens).toBe(135);
  });

  it("adds metadata from a resumed stream even when no new question row is written", () => {
    const request = hitlRequestMsg("e1", { occurrence_id: "sibling" }, 2);
    const firstPause = msg({
      rank: 1,
      role: "system",
      channel: "system_note",
      metadata: { extras: { pause_metadata: true }, token_usage: { total_tokens: 100 } },
    });
    const resumedPause = msg({
      rank: 3,
      role: "system",
      channel: "system_note",
      metadata: { extras: { pause_metadata: true }, token_usage: { total_tokens: 25 } },
    });
    const rows = toThreadMessages([firstPause, request, resumedPause], false);
    const assistant = rows.find((row) => row.role === "assistant");
    expect(rows.filter((row) => row.role === "hitl_request")).toHaveLength(0);
    expect(assistant?.traceMessages).toHaveLength(0);
    expect(assistant?.tokenUsage?.total_tokens).toBe(125);
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

  it("pairs several requests and responses by occurrence_id and restores the first unanswered request", () => {
    const messages = [
      hitlRequestMsg("e1", { occurrence_id: "call-1", question: "First?" }, 1),
      hitlRequestMsg("e1", { occurrence_id: "call-2", question: "Second?" }, 2),
      hitlResponseMsg("e1", { occurrence_id: "call-2", choice_id: "cancel" }, 3),
      hitlResponseMsg("e1", { occurrence_id: "call-1", choice_id: "proceed" }, 4),
      hitlRequestMsg("e1", { occurrence_id: "call-3", question: "Third?" }, 5),
    ];

    const pending = reconstructPendingHitl(messages);
    const rows = toThreadMessages(messages, false);

    expect(pending?.payload.occurrence_id).toBe("call-3");
    expect(pending?.payload.question).toBe("Third?");
    expect(rows.filter((row) => row.role === "hitl_request").map((row) => row.text)).toEqual(["First?", "Second?"]);
    expect(rows.filter((row) => row.role === "hitl_response").map((row) => row.text)).toEqual(["proceed", "cancel"]);
  });

  it("keeps position-based pairing for legacy rows without occurrence_id", () => {
    const messages = [
      hitlRequestMsg("e1", { question: "First legacy?" }, 1),
      hitlResponseMsg("e1", { choice_id: "first" }, 2),
      hitlRequestMsg("e1", { question: "Second legacy?" }, 3),
      hitlResponseMsg("e1", { choice_id: "second" }, 4),
    ];

    const rows = toThreadMessages(messages, false);

    expect(rows.filter((row) => row.role === "hitl_response").map((row) => row.text)).toEqual(["first", "second"]);
    expect(reconstructPendingHitl(messages)).toBeNull();
  });

  it("resolves and renders a skipped agent question after reload", () => {
    const messages = [
      hitlRequestMsg("e1", { stage: "agent_question", occurrence_id: "call-skip" }, 1),
      hitlResponseMsg("e1", { occurrence_id: "call-skip", choice_id: null, skipped: true }, 2),
    ];
    expect(reconstructPendingHitl(messages)).toBeNull();
    const response = toThreadMessages(messages, false).find((row) => row.role === "hitl_response");
    expect(response?.hitlSkipped).toBe(true);
  });

  it("renders a selected option with its optional comment", () => {
    const messages = [
      hitlRequestMsg("e1", { stage: "agent_question", occurrence_id: "call-comment" }, 1),
      hitlResponseMsg("e1", { occurrence_id: "call-comment", choice_id: "yes", text: "Please" }, 2),
    ];
    expect(toThreadMessages(messages, false).find((row) => row.role === "hitl_response")?.text).toBe("yes: Please");
  });

  it("attaches an answered agent question to its matching tool call", () => {
    const messages = [
      msg({
        rank: 0,
        channel: "tool_call",
        parts: [{ type: "tool_call", call_id: "call-bread", name: "ask_user", args: {} }],
      }),
      hitlRequestMsg(
        "e1",
        {
          stage: "agent_question",
          occurrence_id: "call-bread",
          question: "Which bread?",
          choices: [{ id: "complet", label: "Pain complet" }],
        },
        1,
      ),
      hitlResponseMsg("e1", { occurrence_id: "call-bread", choice_id: "complet" }, 2),
    ];

    const rows = toThreadMessages(messages, false);
    expect(rows.map((row) => row.role)).toEqual(["assistant"]);
    expect(rows[0].hitlAnswerSummariesByCallId?.["call-bread"]).toMatchObject({
      question: "Which bread?",
      answer: "Pain complet",
      choiceId: "complet",
    });
  });

  it("renders a pure free-text response from its dedicated text field", () => {
    const messages = [
      hitlRequestMsg("e1", { occurrence_id: "call-text", question: "Explain" }, 1),
      hitlResponseMsg("e1", { occurrence_id: "call-text", choice_id: null, text: "Because it is safer" }, 2),
    ];

    const rows = toThreadMessages(messages, false);

    expect(rows.find((row) => row.role === "hitl_response")?.text).toBe("Because it is safer");
  });
});

describe("persisted tool refusals", () => {
  it.each([false, true])("restores every refusal after reload (occurrence IDs: %s)", (withOccurrences) => {
    const messages: ChatMessage[] = [];
    for (let i = 0; i < 5; i++) {
      const callId = `call-${i}`;
      const identity = withOccurrences ? { occurrence_id: `gate-${i}` } : {};
      messages.push(
        msg({
          rank: i * 3,
          channel: "tool_call",
          parts: [{ type: "tool_call", name: "summarize_document", call_id: callId, args: {} }],
        }),
        hitlRequestMsg(
          "e1",
          {
            ...identity,
            pending_calls: [{ tool_call_id: callId, tool_name: "summarize_document", args_preview: "{}" }],
          },
          i * 3 + 1,
        ),
        hitlResponseMsg("e1", { ...identity, choice_id: "cancel" }, i * 3 + 2),
      );
    }
    messages.push(msg({ rank: 15, parts: [{ type: "text", text: "Finished" }] }));
    const before = JSON.stringify(messages);
    const assistant = toThreadMessages(messages, false).find((row) => row.role === "assistant")!;
    const entries = groupTraceEntries(assistant.traceMessages);
    expect(entries).toHaveLength(5);
    expect(entries.every(isCancelledByUser)).toBe(true);
    expect(traceSummary(entries).running).toBe(false);
    expect(assistant.text).toBe("Finished");
    expect(JSON.stringify(messages)).toBe(before);
  });

  it("restores all calls of one refused batch without duplicating IDs", () => {
    const assistant = toThreadMessages(
      [
        hitlRequestMsg("e1", {
          pending_calls: ["c1", "c2", "c1", null].map((tool_call_id) => ({
            tool_call_id,
            tool_name: "summarize_document",
            args_preview: "{}",
          })),
        }),
        hitlResponseMsg("e1", { choice_id: "cancel" }, 1),
      ],
      false,
    ).find((row) => row.role === "assistant")!;
    expect(assistant.traceMessages.flatMap((m) => m.parts)).toEqual([
      { type: "tool_result", call_id: "c1", ok: false, content: "" },
      { type: "tool_result", call_id: "c2", ok: false, content: "" },
    ]);
  });

  it.each([false, true])("preserves existing results without duplication (optimistic: %s)", (optimistic) => {
    const result = msg({
      role: "tool",
      channel: "tool_result",
      rank: 3,
      parts: [{ type: "tool_result", call_id: "call-1", ok: !optimistic, content: "result" }],
      metadata: optimistic ? { extras: { cancelled_by_user: true } } : {},
    });
    const assistant = toThreadMessages(
      [hitlRequestMsg("e1"), hitlResponseMsg("e1", { choice_id: "cancel" }, 2), result],
      false,
    ).find((row) => row.role === "assistant")!;
    expect(assistant.traceMessages).toEqual([result]);
  });

  it("does not cancel approved or pending calls, or matching IDs in another exchange", () => {
    const messages = [
      hitlRequestMsg("e1"),
      hitlResponseMsg("e1", { choice_id: "cancel" }, 1),
      hitlRequestMsg("e2", {}, 2),
      hitlResponseMsg("e2", {}, 3),
      hitlRequestMsg("e3", {}, 4),
    ];
    const assistants = toThreadMessages(messages, false).filter((row) => row.role === "assistant");
    expect(assistants).toHaveLength(1);
    expect(assistants[0].id).toBe("e1:assistant");
    expect(reconstructPendingHitl(messages)?.payload.pending_calls?.[0].tool_call_id).toBe("call-1");
  });
});
