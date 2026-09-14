import { describe, it, expect } from "vitest";
import type { ChatMessage } from "../../slices/runtime/runtimeOpenApi";
import {
  asRagSearchResult,
  asSqlQueryResult,
  formatLatencyMs,
  groupTraceEntries,
  humanizeToolName,
  isDocumentTreeTool,
  entryLabel,
  isCancelledByUser,
  isTraceChannel,
  isFinalChannel,
  uiPartsOf,
  isSummarizeDocumentTool,
  parseToolResultContent,
  primaryTextForEntry,
  secondaryTextForEntry,
  statusForEntry,
  stripDocumentUids,
  textOf,
  toolCopyText,
  toolDiscriminator,
  totalLatencyMs,
  traceRows,
  traceSummary,
} from "./traceUtils";

// ── Factory ───────────────────────────────────────────────────────────────────

function msg(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    session_id: "s1",
    exchange_id: "e1",
    rank: 0,
    timestamp: "2026-01-01T00:00:00.000Z",
    role: "assistant",
    channel: "final",
    parts: [],
    ...overrides,
  };
}

function textMsg(text: string, overrides: Partial<ChatMessage> = {}): ChatMessage {
  return msg({ parts: [{ type: "text", text }], ...overrides });
}

function toolCallMsg(callId: string, name: string, args: Record<string, unknown> = {}): ChatMessage {
  return msg({
    channel: "tool_call",
    parts: [{ type: "tool_call", call_id: callId, name, args }],
  });
}

function toolResultMsg(callId: string, content: string, ok = true, latencyMs?: number): ChatMessage {
  return msg({
    channel: "tool_result",
    role: "tool",
    parts: [{ type: "tool_result", call_id: callId, ok, content, latency_ms: latencyMs ?? null }],
  });
}

function thoughtMsg(
  text: string,
  extras: {
    streaming_delta?: boolean;
    title?: string;
    conclusion?: string;
    phase?: string;
    duration_ms?: number;
    source?: string;
  } = {},
): ChatMessage {
  return msg({
    channel: "thought",
    parts: [{ type: "text", text }],
    metadata: { extras },
  });
}

// ── isTraceChannel / isFinalChannel ──────────────────────────────────────────

describe("isTraceChannel", () => {
  it("returns true for thought, tool_call, tool_result, plan, observation, error, system_note", () => {
    for (const ch of ["thought", "tool_call", "tool_result", "plan", "observation", "error", "system_note"] as const) {
      expect(isTraceChannel(ch), ch).toBe(true);
    }
  });

  it("returns false for final", () => {
    expect(isTraceChannel("final")).toBe(false);
  });
});

describe("isFinalChannel", () => {
  it("returns true for final only", () => {
    expect(isFinalChannel("final")).toBe(true);
    expect(isFinalChannel("thought")).toBe(false);
    expect(isFinalChannel("tool_call")).toBe(false);
  });
});

// ── textOf ───────────────────────────────────────────────────────────────────

describe("textOf", () => {
  it("returns text from text parts", () => {
    expect(textOf(textMsg("hello"))).toBe("hello");
  });

  it("concatenates multiple text parts", () => {
    const m = msg({
      parts: [
        { type: "text", text: "foo" },
        { type: "text", text: "bar" },
      ],
    });
    expect(textOf(m)).toBe("foobar");
  });

  it("ignores non-text parts", () => {
    const m = msg({ parts: [{ type: "tool_call", call_id: "c1", name: "search", args: {} }] });
    expect(textOf(m)).toBe("");
  });

  it("returns empty string for empty parts", () => {
    expect(textOf(msg({ parts: [] }))).toBe("");
  });
});

// ── formatLatencyMs ───────────────────────────────────────────────────────────

describe("uiPartsOf", () => {
  // A capability part: not a member of the closed `MessagePart` union, which is
  // the whole point - the renderer registry resolves it by `type` at render time.
  const deck = { type: "ppt_preview", preview_id: "p1", title: "Q3 review" } as unknown as ChatMessage["parts"][number];

  it("reads the parts a streamed message carries inline", () => {
    expect(uiPartsOf(msg({ parts: [{ type: "text", text: "hi" }, deck] }))).toEqual([deck]);
  });

  it("reads the parts a STORED message carries on its metadata", () => {
    // The whole reason a reloaded conversation kept its text and lost every
    // capability card: `MessagePart` is closed, so storage puts them here.
    expect(uiPartsOf(msg({ parts: [{ type: "text", text: "hi" }], metadata: { ui_parts: [deck] } }))).toEqual([deck]);
  });

  it("renders a part carried on both sides once, whatever its key order", () => {
    // The stored copy comes back from a JSON column, so its keys need not be in
    // the order the streamed one had.
    const reordered = { title: "Q3 review", preview_id: "p1", type: "ppt_preview" };
    expect(uiPartsOf(msg({ parts: [deck], metadata: { ui_parts: [reordered] } }))).toEqual([deck]);
  });

  it("drops a stored part whose kind collides with a message-body part", () => {
    // The inline branch filters those out; the stored one must agree, or the same
    // turn renders differently before and after a reload.
    expect(uiPartsOf(msg({ metadata: { ui_parts: [{ type: "code", code: "x" }] } }))).toEqual([]);
  });

  it("keeps a stored part of a kind this build does not know", () => {
    const future = { type: "kind_from_the_future", payload: 1 };
    expect(uiPartsOf(msg({ metadata: { ui_parts: [future] } }))).toEqual([future]);
  });

  it("is empty for a message with neither", () => {
    expect(uiPartsOf(msg({ parts: [{ type: "text", text: "hi" }] }))).toEqual([]);
  });
});

describe("formatLatencyMs", () => {
  it("returns empty string for null", () => {
    expect(formatLatencyMs(null)).toBe("");
  });

  it("formats sub-second as Xms", () => {
    expect(formatLatencyMs(0)).toBe("0ms");
    expect(formatLatencyMs(500)).toBe("500ms");
    expect(formatLatencyMs(999)).toBe("999ms");
  });

  it("formats >= 1000ms as X.Xs", () => {
    expect(formatLatencyMs(1000)).toBe("1.0s");
    expect(formatLatencyMs(1500)).toBe("1.5s");
    expect(formatLatencyMs(2750)).toBe("2.8s");
  });
});

// ── groupTraceEntries ─────────────────────────────────────────────────────────

describe("groupTraceEntries", () => {
  it("returns empty array for empty input", () => {
    expect(groupTraceEntries([])).toEqual([]);
  });

  it("returns empty array when messages contain no trace channels", () => {
    expect(groupTraceEntries([textMsg("hi", { channel: "final" })])).toEqual([]);
  });

  it("makes a solo entry for a thought message", () => {
    const t = thoughtMsg("thinking…");
    const entries = groupTraceEntries([t]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({ kind: "solo", message: t });
  });

  it("pairs a tool_call with its matching tool_result by call_id", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([call, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result });
  });

  it("pairs tool_call+result even when result appears before call in array", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([result, call]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result });
  });

  it("handles multiple distinct pairs correctly", () => {
    const call1 = toolCallMsg("c1", "search");
    const result1 = toolResultMsg("c1", "r1");
    const call2 = toolCallMsg("c2", "fetch");
    const result2 = toolResultMsg("c2", "r2");
    const entries = groupTraceEntries([call1, result1, call2, result2]);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({ kind: "combo", call: call1, result: result1 });
    expect(entries[1]).toMatchObject({ kind: "combo", call: call2, result: result2 });
  });

  it("marks combo as pending when tool_call has no matching result", () => {
    const call = toolCallMsg("c1", "search");
    const entries = groupTraceEntries([call]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result: undefined });
  });

  it("makes orphan tool_result a solo entry", () => {
    const orphan = toolResultMsg("c99", "unexpected");
    const entries = groupTraceEntries([orphan]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({ kind: "solo", message: orphan });
  });

  it("preserves thought solo entries alongside combos", () => {
    const thought = thoughtMsg("planning");
    const call = toolCallMsg("c1", "lookup");
    const result = toolResultMsg("c1", "data");
    const entries = groupTraceEntries([thought, call, result]);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toEqual({ kind: "solo", message: thought });
    expect(entries[1]).toMatchObject({ kind: "combo" });
  });

  it("filters out synthetic tool_use thought entries — redundant with the paired combo row", () => {
    const toolUseThought = thoughtMsg("", { phase: "tool_use", title: "Calling search", conclusion: "Done" });
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([toolUseThought, call, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call, result });
  });

  it("keeps non-tool_use thought phases (planning, reflection, synthesis) alongside combos", () => {
    const planning = thoughtMsg("thinking it through", { phase: "planning" });
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([planning, call, result]);
    expect(entries).toHaveLength(2);
    expect(entries[0]).toEqual({ kind: "solo", message: planning });
    expect(entries[1]).toMatchObject({ kind: "combo", call, result });
  });
});

// ── statusForEntry ────────────────────────────────────────────────────────────

describe("statusForEntry", () => {
  it("returns 'streaming' for a streaming thought", () => {
    const m = thoughtMsg("partial…", { streaming_delta: true });
    expect(statusForEntry({ kind: "solo", message: m })).toBe("streaming");
  });

  it("returns 'error' for an error-channel message", () => {
    const m = msg({ channel: "error" });
    expect(statusForEntry({ kind: "solo", message: m })).toBe("error");
  });

  it("keeps a turn-crash error line short and copyable (DOCREAD-01)", () => {
    const raw = 'Error code: 429 - {"message":"Rate limit exceeded"}';
    const entry = { kind: "solo", message: textMsg(raw, { channel: "error" }) } as const;
    // Line: no raw dump inline (the row renders a localized short indication);
    // drawer: the raw message is what gets copied.
    expect(primaryTextForEntry(entry)).toBe("");
    expect(toolCopyText(entry)).toBe(raw);
    expect(entryLabel(entry)).toBe("Error");
  });
});

describe("isCancelledByUser", () => {
  it("flags a combo whose result is marked cancelled_by_user", () => {
    const call = toolCallMsg("c1", "extract_from_document");
    const result = msg({
      channel: "tool_result",
      role: "tool",
      parts: [{ type: "tool_result", call_id: "c1", ok: false, content: "", latency_ms: null }],
      metadata: { extras: { cancelled_by_user: true } },
    });
    const entry = { kind: "combo", call, result } as const;
    expect(isCancelledByUser(entry)).toBe(true);
    // Still a red (error) dot, but distinguishable from a genuine tool failure.
    expect(statusForEntry(entry)).toBe("error");
  });

  it("is false for a normal failed tool result and for the crash line", () => {
    const call = toolCallMsg("c1", "x");
    expect(isCancelledByUser({ kind: "combo", call, result: toolResultMsg("c1", "boom", false) })).toBe(false);
    expect(isCancelledByUser({ kind: "solo", message: textMsg("err", { channel: "error" }) })).toBe(false);
  });

  it("returns 'ok' for a completed solo thought", () => {
    const m = thoughtMsg("done");
    expect(statusForEntry({ kind: "solo", message: m })).toBe("ok");
  });

  it("returns 'pending' for a combo with no result yet", () => {
    const call = toolCallMsg("c1", "search");
    expect(statusForEntry({ kind: "combo", call })).toBe("pending");
  });

  it("returns 'ok' for a combo with a successful result", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found", true);
    expect(statusForEntry({ kind: "combo", call, result })).toBe("ok");
  });

  it("returns 'error' for a combo with a failed result", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "boom", false);
    expect(statusForEntry({ kind: "combo", call, result })).toBe("error");
  });

  it("returns 'awaiting_confirmation' for a combo whose call_id is in the pending HITL id list", () => {
    const call = toolCallMsg("c1", "summarize_document");
    expect(statusForEntry({ kind: "combo", call }, ["c1"])).toBe("awaiting_confirmation");
  });

  it("returns 'awaiting_confirmation' for EACH call batched into one HITL prompt (#2177)", () => {
    expect(statusForEntry({ kind: "combo", call: toolCallMsg("c1", "summarize_document") }, ["c1", "c2", "c3"])).toBe(
      "awaiting_confirmation",
    );
    expect(statusForEntry({ kind: "combo", call: toolCallMsg("c2", "summarize_document") }, ["c1", "c2", "c3"])).toBe(
      "awaiting_confirmation",
    );
  });

  it("returns 'pending' for a combo with no result yet when a DIFFERENT call is pending confirmation", () => {
    const call = toolCallMsg("c1", "search");
    expect(statusForEntry({ kind: "combo", call }, ["c-other"])).toBe("pending");
  });
});

// ── primaryTextForEntry ───────────────────────────────────────────────────────

describe("primaryTextForEntry", () => {
  it("returns thought title when set", () => {
    const m = thoughtMsg("long body", { title: "My Title" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("My Title");
  });

  it("falls back to thought body when no title", () => {
    const m = thoughtMsg("body text");
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("body text");
  });

  it("returns body text for non-thought solo entries", () => {
    const m = textMsg("some output", { channel: "plan" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("some output");
  });

  it("returns empty string for combo with args — raw tool name and arguments are suppressed", () => {
    const call = toolCallMsg("c1", "search", { query: "vitest" });
    expect(primaryTextForEntry({ kind: "combo", call })).toBe("");
  });

  it("returns empty string for combo with no args", () => {
    const call = toolCallMsg("c1", "refresh", {});
    expect(primaryTextForEntry({ kind: "combo", call })).toBe("");
  });

  it("shows tool_use thought title (e.g. 'Calling tavily search')", () => {
    const m = thoughtMsg("", { title: "Calling tavily search", phase: "tool_use" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("Calling tavily search");
  });

  it("shows title for non-tool_use thought phases", () => {
    const m = thoughtMsg("body", { title: "Planning step", phase: "planning" });
    expect(primaryTextForEntry({ kind: "solo", message: m })).toBe("Planning step");
  });
});

// ── secondaryTextForEntry ────────────────────────────────────────────────────

describe("secondaryTextForEntry", () => {
  it("returns conclusion for a completed thought", () => {
    const m = thoughtMsg("body", { conclusion: "All good" });
    expect(secondaryTextForEntry({ kind: "solo", message: m })).toBe("All good");
  });

  it("returns latency string for combo with result that has latency", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "The answer is 42", true, 1500);
    expect(secondaryTextForEntry({ kind: "combo", call, result })).toBe("1.5s");
  });

  it("returns empty string when result has no latency", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", '{"raw":"json response"}');
    expect(secondaryTextForEntry({ kind: "combo", call, result })).toBe("");
  });

  it("does not expose raw result content", () => {
    const call = toolCallMsg("c1", "get_issue");
    const result = toolResultMsg("c1", '{"expand":"renderedFields,names,schema","summary":"Secret data"}');
    const text = secondaryTextForEntry({ kind: "combo", call, result });
    expect(text).not.toContain("renderedFields");
    expect(text).not.toContain("Secret");
    expect(text).not.toContain("{");
  });

  it("returns empty string for pending combo", () => {
    const call = toolCallMsg("c1", "search");
    expect(secondaryTextForEntry({ kind: "combo", call })).toBe("");
  });
});

// ── totalLatencyMs ────────────────────────────────────────────────────────────

describe("totalLatencyMs", () => {
  it("returns 0 for empty entries", () => {
    expect(totalLatencyMs([])).toBe(0);
  });

  it("sums latencies of all combo results", () => {
    const entries = [
      { kind: "combo" as const, call: toolCallMsg("c1", "a"), result: toolResultMsg("c1", "r1", true, 100) },
      { kind: "combo" as const, call: toolCallMsg("c2", "b"), result: toolResultMsg("c2", "r2", true, 250) },
    ];
    expect(totalLatencyMs(entries)).toBe(350);
  });

  it("ignores solo entries and pending combos", () => {
    const entries = [
      { kind: "solo" as const, message: thoughtMsg("thinking") },
      { kind: "combo" as const, call: toolCallMsg("c1", "search") },
    ];
    expect(totalLatencyMs(entries)).toBe(0);
  });
});

// ── restated reasoning ────────────────────────────────────────────────────────

/** The display text of each reasoning block of one turn, in order. */
function reasoningTexts(...blocks: (string | ChatMessage)[]) {
  const rows = traceRows(
    blocks.map((block) => ({ kind: "solo" as const, message: typeof block === "string" ? thoughtMsg(block) : block })),
  );
  return rows.map((row) => row.reasoningText);
}

describe("traceRows — restated reasoning", () => {
  it("leaves the first block untouched", () => {
    expect(reasoningTexts("Only block. Nothing before it.")).toEqual(["Only block. Nothing before it."]);
  });

  it("drops the sentences an earlier block already said", () => {
    const shared = "The user asked for a document. I identified it and summarised it.";
    expect(reasoningTexts(shared, `${shared} However, the tool is unavailable.`)).toEqual([
      shared,
      "However, the tool is unavailable.",
    ]);
  });

  // The shape seen in real conversations: the model restates its context at every
  // round, rephrased rather than verbatim, so a character-level match finds nothing.
  it("drops a rephrased restatement", () => {
    const first =
      "L'utilisateur demande de traduire deux pages du wiki en espagnol et en italien. Je dois les localiser.";
    const second =
      "L'utilisateur a demandé de traduire deux pages du wiki en espagnol et en italien. J'ai lu les deux pages.";
    expect(reasoningTexts(first, second)[1]).toBe("J'ai lu les deux pages.");
  });

  it("drops what any earlier block said, not only the previous one", () => {
    const texts = reasoningTexts(
      "The user wants a summary. I will list the files.",
      "Two PDF files were found.",
      "The user wants a summary. Two PDF files were found. Reading the first one now.",
    );
    expect(texts[2]).toBe("Reading the first one now.");
  });

  it("drops the list items an earlier block already listed", () => {
    const first = "I read both pages:\n- Activities / Spain\n- Activities / Italy";
    const second = "I read both pages:\n- Activities / Spain\n- Activities / Italy\n\nNow translating them.";
    expect(reasoningTexts(first, second)[1]).toBe("Now translating them.");
  });

  // The shape of a real session: the agent re-lists the user's instructions at
  // every round, verbatim, under an intro rephrased too far to match on its own.
  it("drops a repeated list together with its rephrased intro", () => {
    const tasks = "1. Lister les documents\n2. Résumer un document au hasard\n3. Générer un document Word";
    const first = `L'utilisateur me donne des instructions détaillées sur mon processus de travail :\n${tasks}\n\nJe commence.`;
    const second = `L'utilisateur m'a donné des instructions très précises sur la manière de procéder :\n${tasks}\n\nLe document est créé.`;
    expect(reasoningTexts(first, second)[1]).toBe("Le document est créé.");
  });

  it("keeps an intro whose list brings something new", () => {
    const first = "Voici le plan :\n1. Lister les documents";
    const second = "Voici ce qui reste à faire :\n1. Lister les documents\n2. Écrire le rapport";
    expect(reasoningTexts(first, second)[1]).toBe(
      "Voici ce qui reste à faire : 1. Lister les documents 2. Écrire le rapport",
    );
  });

  it("drops a repeated list even when one item was retouched", () => {
    const first =
      "L'utilisateur me demande de :\n1. Chercher dans les documents RAG (vector search)\n2. Lister les documents";
    const second =
      "L'utilisateur me demande de :\n1. Chercher dans les documents RAG\n2. Lister les documents\n\nJ'ai reçu la liste.";
    expect(reasoningTexts(first, second)[1]).toBe("J'ai reçu la liste.");
  });

  // One sentence reworded just below the threshold used to stop the trim, and
  // every verbatim sentence after it stayed on the row.
  it("does not let one reworded sentence shield the verbatim ones after it", () => {
    const tail =
      "Je dois localiser ces pages dans l'index du wiki. Je vais utiliser wiki_read_page pour les deux pages.";
    const first = `L'utilisateur demande de traduire en espagnol et en italien deux pages du wiki. ${tail}`;
    const second = `L'utilisateur demande de traduire deux pages du wiki en espagnol et en italien. ${tail} Les pages sont lues.`;
    expect(reasoningTexts(first, second)[1]).toBe("Les pages sont lues.");
  });

  // Near repeats are dropped only INSIDE a lead of real repeats: a trailing one
  // may be the only new fact of the block.
  it("keeps a near-repeated sentence that would end the lead", () => {
    const shared = "La page parente a été créée dans le wiki.";
    const texts = reasoningTexts(
      `${shared} Je dois maintenant publier la page Italie.`,
      `${shared} Je dois maintenant publier la page Espagne.`,
    );
    expect(texts[1]).toBe("Je dois maintenant publier la page Espagne.");
  });

  // Every recap item resembles an earlier one, but a lead of near repeats with
  // few real ones is progress told in new words, not a restatement.
  it("keeps a recap told in new words", () => {
    const first =
      "Je dois :\n- Lister les documents disponibles dans le chat\n- Résumer un document au hasard dans le corpus";
    const recap =
      "Bilan :\n- Documents disponibles dans le chat listés hier soir\n- Document au hasard dans le corpus résumé ce matin";
    const second = `- Lister les documents disponibles dans le chat\n\n${recap}\n\nSuite.`;
    expect(reasoningTexts(first, second)[1]).toBe(
      "Bilan : Documents disponibles dans le chat listés hier soir Document au hasard dans le corpus résumé ce matin Suite.",
    );
  });

  it("keeps a near-repeated sentence between repeats", () => {
    const before = "La page parente a été créée dans le wiki.";
    const after = "Je vais utiliser wiki_propose_page pour cela.";
    const texts = reasoningTexts(
      `${before} Je dois maintenant publier la page Italie. ${after}`,
      `${before} Je dois maintenant publier la page Espagne. ${after}`,
    );
    expect(texts[1]).toBe(`Je dois maintenant publier la page Espagne. ${after}`);
  });

  it.each([
    ["before a repeated sentence", "Trois pages manquent encore :\nLa page parente a été créée dans le wiki."],
    ["before a repeated list", "Deux étapes restent bloquées :\n1. Lister les documents\n2. Résumer un document"],
  ])("keeps a new intro %s", (_label, second) => {
    const first =
      "Plan :\n1. Lister les documents\n2. Résumer un document\n\nLa page parente a été créée dans le wiki.";
    expect(reasoningTexts(first, second)[1]).not.toBe("");
    expect(reasoningTexts(first, second)[1]).toMatch(/^(Trois|Deux)/);
  });

  it("recognises a numbered item still streaming as a repeat", () => {
    const earlier = thoughtMsg("Plan :\n1. Lister les documents disponibles du corpus.");
    const streaming = thoughtMsg("Plan :\n2. Lister les documents disponibles du cor", { streaming_delta: true });
    const rows = traceRows([
      { kind: "solo", message: earlier },
      { kind: "solo", message: streaming },
    ]);
    expect(rows[1]).toMatchObject({ reasoningText: "", restated: false });
  });

  it("still drops a renumbered list item", () => {
    expect(
      reasoningTexts("1. Lister les documents disponibles", "2. Lister les documents disponibles\n\nEnsuite.")[1],
    ).toBe("Ensuite.");
  });

  it("only drops the leading run, never a sentence in the middle", () => {
    const texts = reasoningTexts("The user wants a summary.", "A new finding. The user wants a summary.");
    expect(texts[1]).toBe("A new finding. The user wants a summary.");
  });

  it("keeps a sentence that differs from an earlier one by a single noun", () => {
    const texts = reasoningTexts(
      "Je dois maintenant publier la page Italie.",
      "Je dois maintenant publier la page Espagne.",
    );
    expect(texts[1]).toBe("Je dois maintenant publier la page Espagne.");
  });

  it.each([
    ["a number", "Il reste 3 pages à traduire dans le wiki.", "Il reste 2 pages à traduire dans le wiki."],
    ["a negation", "The search returned relevant results.", "The search returned no relevant results."],
    ["a French negation", "La page parente existe dans le wiki.", "La page parente n'existe pas dans le wiki."],
  ])("keeps a sentence that changes %s", (_label, first, second) => {
    expect(reasoningTexts(first, second)[1]).toBe(second);
  });

  // Were a soft-wrapped line its own segment, its first half would match and
  // the row would open on "and then check the logs".
  it("does not treat a soft-wrapped line as a sentence end", () => {
    const text = "I will reread the configuration file\nand then check the logs.";
    expect(reasoningTexts("I will reread the configuration file", text)[1]).toBe(
      "I will reread the configuration file and then check the logs.",
    );
  });

  it("recomputes a block when an earlier block changes", () => {
    const later = thoughtMsg("The user wants a summary. Reading the files.");
    const rows = (first: string) =>
      traceRows([
        { kind: "solo", message: thoughtMsg(first) },
        { kind: "solo", message: later },
      ]);
    expect(rows("The user wants a summary.")[1].reasoningText).toBe("Reading the files.");
    expect(rows("Something unrelated.")[1].reasoningText).toBe("The user wants a summary. Reading the files.");
  });

  // A `.` is not a sentence end on its own. Were the block split after one of
  // these, the head alone would match the earlier block and the row would open
  // mid-sentence — so each case must come back untouched.
  it.each([
    ["an abbreviation before a capital", "See cf.", "See cf. Section 4 and the appendix."],
    ["a titled reference before a digit", "See Fig.", "See Fig. 2 and the appendix."],
    ["a numbered list marker", "1.", "1. Read the configuration file."],
    ["an ordinal before a digit", "Ranked No.", "Ranked No. 3 by score."],
    ["a person's title", "Escalated to Dr.", "Escalated to Dr. Martin and the on-call."],
  ])("does not cut inside %s", (_label, head, text) => {
    expect(reasoningTexts(head, text)[1]).toBe(text);
  });

  it("marks a block with nothing new as restated", () => {
    const rows = traceRows([
      { kind: "solo", message: thoughtMsg("The user wants a summary. I will list the files.") },
      { kind: "solo", message: thoughtMsg("The user wants a summary. I will list the files.") },
    ]);
    expect(rows.map((row) => row.restated)).toEqual([false, true]);
    expect(rows[1].reasoningText).toBe("");
  });

  // Still streaming, the block may yet add something: it shows nothing rather
  // than a restatement label, and its unfinished sentence does not flash in.
  it("does not call a streaming block restated, nor show its restated tail", () => {
    const earlier = thoughtMsg("The user asked for a translation of two pages.");
    const streaming = thoughtMsg("The user asked for a transl", { streaming_delta: true });
    const rows = traceRows([
      { kind: "solo", message: earlier },
      { kind: "solo", message: streaming },
    ]);
    expect(rows[1]).toMatchObject({ reasoningText: "", restated: false });
  });
});

// ── traceRows ─────────────────────────────────────────────────────────────────

describe("traceRows", () => {
  it("returns no rows for an empty trace", () => {
    expect(traceRows([])).toEqual([]);
  });

  // The flattened preview is cached on the message object. That is only sound
  // because a streaming block arrives as a NEW object each delta (`upsertOne`
  // rebuilds it rather than mutating in place) — if that ever changes, a live
  // reasoning row would freeze at its first token.
  it("reflects a growing block, which arrives as a new message object", () => {
    const first = thoughtMsg("I will search", { phase: "planning" });
    const grown = thoughtMsg("I will search the corpus", { phase: "planning" });
    expect(traceRows([{ kind: "solo", message: first }])[0].reasoningText).toBe("I will search");
    expect(traceRows([{ kind: "solo", message: grown }])[0].reasoningText).toBe("I will search the corpus");
  });

  it("tags reasoning channels as the reasoning lane", () => {
    const planning = thoughtMsg("thinking", { phase: "planning" });
    const plan = msg({ channel: "plan", parts: [{ type: "text", text: "step 1" }] });
    const observation = msg({ channel: "observation", parts: [{ type: "text", text: "noted" }] });
    const rows = traceRows([
      { kind: "solo", message: planning },
      { kind: "solo", message: plan },
      { kind: "solo", message: observation },
    ]);
    expect(rows.map((r) => r.lane)).toEqual(["reasoning", "reasoning", "reasoning"]);
    expect(rows.every((r) => r.index === null)).toBe(true);
  });

  it("numbers tool steps 1-based in arrival order", () => {
    const entries = [
      { kind: "combo" as const, call: toolCallMsg("c1", "read_query"), result: toolResultMsg("c1", "{}", true, 100) },
      { kind: "combo" as const, call: toolCallMsg("c2", "read_query"), result: toolResultMsg("c2", "{}", true, 200) },
    ];
    expect(traceRows(entries).map((r) => r.index)).toEqual([1, 2]);
  });

  it("keeps reasoning out of the step numbering", () => {
    const planning = thoughtMsg("thinking", { phase: "planning" });
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found", true, 50);
    const rows = traceRows(groupTraceEntries([planning, call, result]));
    expect(rows.map((r) => [r.lane, r.index])).toEqual([
      ["reasoning", null],
      ["step", 1],
    ]);
  });

  it("sequences notes and errors with the steps but leaves them unnumbered", () => {
    const call = toolCallMsg("c1", "search");
    const result = toolResultMsg("c1", "found", true, 50);
    const failure = msg({ channel: "error", parts: [{ type: "text", text: "boom" }] });
    const rows = traceRows(groupTraceEntries([call, result, failure]));
    expect(rows.map((r) => [r.lane, r.index])).toEqual([
      ["step", 1],
      ["step", null],
    ]);
  });

  // The whole point of the rewrite: a turn that reasoned, called a tool,
  // reasoned again and called another must render in that order — not as every
  // thought hoisted above every tool, which is an order that never happened.
  it("interleaves reasoning and tool steps in arrival order", () => {
    const rows = traceRows(
      groupTraceEntries([
        thoughtMsg("first", { phase: "planning" }),
        toolCallMsg("c1", "search"),
        toolResultMsg("c1", "found", true, 50),
        thoughtMsg("second", { phase: "reflection" }),
        toolCallMsg("c2", "read_query"),
        toolResultMsg("c2", "rows", true, 20),
      ]),
    );
    expect(rows.map((r) => [r.lane, r.index])).toEqual([
      ["reasoning", null],
      ["step", 1],
      ["reasoning", null],
      ["step", 2],
    ]);
  });

  it("leaves step rows without reasoning text", () => {
    const rows = traceRows(groupTraceEntries([toolCallMsg("c1", "search"), toolResultMsg("c1", "ok", true, 10)]));
    expect(rows[0].reasoningText).toBeNull();
  });
});

// ── traceSummary ──────────────────────────────────────────────────────────────

describe("traceSummary", () => {
  it("reports nothing for an empty trace", () => {
    expect(traceSummary([])).toEqual({
      reasoningMs: null,
      toolCount: 0,
      toolMs: 0,
      running: false,
      awaitingConfirmation: false,
    });
  });

  // The runtime now closes the model-native block at every tool round, so the
  // blocks are disjoint stretches of thinking. A max would report only the
  // longest one and silently drop the rest.
  it("sums the reasoning durations across the turn's blocks", () => {
    const first = thoughtMsg("first", { phase: "planning", duration_ms: 16400 });
    const second = thoughtMsg("second", { phase: "reflection", duration_ms: 1200 });
    expect(
      traceSummary([
        { kind: "solo", message: first },
        { kind: "solo", message: second },
      ]).reasoningMs,
    ).toBe(17600);
  });

  it("ignores blocks that reported no duration rather than counting them as zero", () => {
    const timed = thoughtMsg("timed", { phase: "planning", duration_ms: 900 });
    const untimed = thoughtMsg("untimed", { phase: "reflection" });
    expect(
      traceSummary([
        { kind: "solo", message: timed },
        { kind: "solo", message: untimed },
      ]).reasoningMs,
    ).toBe(900);
    expect(traceSummary([{ kind: "solo", message: untimed }]).reasoningMs).toBeNull();
  });

  it("counts tools and sums their latency separately from the reasoning duration", () => {
    const reasoning = thoughtMsg("thinking", { phase: "planning", duration_ms: 16400 });
    const entries = [
      { kind: "solo" as const, message: reasoning },
      { kind: "combo" as const, call: toolCallMsg("c1", "a"), result: toolResultMsg("c1", "r", true, 148) },
      { kind: "combo" as const, call: toolCallMsg("c2", "b"), result: toolResultMsg("c2", "r", true, 140) },
    ];
    expect(traceSummary(entries)).toEqual({
      reasoningMs: 16400,
      toolCount: 2,
      toolMs: 288,
      running: false,
      awaitingConfirmation: false,
    });
  });

  it("is running while a thought still streams", () => {
    const streaming = thoughtMsg("partial…", { streaming_delta: true });
    expect(traceSummary([{ kind: "solo", message: streaming }]).running).toBe(true);
  });

  it("is running while a tool call awaits its result", () => {
    expect(traceSummary([{ kind: "combo", call: toolCallMsg("c1", "search") }]).running).toBe(true);
  });

  it("is running, and awaitingConfirmation, while a tool call is gated behind an unanswered HITL prompt", () => {
    const entries = [{ kind: "combo" as const, call: toolCallMsg("c1", "summarize_document") }];
    expect(traceSummary(entries, ["c1"])).toEqual({
      reasoningMs: null,
      toolCount: 1,
      toolMs: 0,
      running: true,
      awaitingConfirmation: true,
    });
  });

  it("is awaitingConfirmation for a batch of several calls gated by ONE combined HITL prompt (#2177)", () => {
    const entries = [
      { kind: "combo" as const, call: toolCallMsg("c1", "summarize_document") },
      { kind: "combo" as const, call: toolCallMsg("c2", "summarize_document") },
      { kind: "combo" as const, call: toolCallMsg("c3", "summarize_document") },
    ];
    const summary = traceSummary(entries, ["c1", "c2", "c3"]);
    expect(summary.awaitingConfirmation).toBe(true);
    expect(summary.running).toBe(true);
    expect(summary.toolCount).toBe(3);
  });

  it("does not mark awaitingConfirmation for an unrelated pending call_id", () => {
    const entries = [{ kind: "combo" as const, call: toolCallMsg("c1", "summarize_document") }];
    expect(traceSummary(entries, ["c-other"]).awaitingConfirmation).toBe(false);
  });
});

// ── toolDiscriminator ─────────────────────────────────────────────────────────

describe("toolDiscriminator", () => {
  it("reports the row count of a SQL result", () => {
    const result = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [{ a: 1 }, { a: 2 }] }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "read_query"), result })).toEqual({
      kind: "rows",
      count: 2,
    });
  });

  it("reports the hit count of a RAG result", () => {
    const result = toolResultMsg("c1", JSON.stringify({ query: "cars", hits: [{}, {}, {}] }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "search"), result })).toEqual({
      kind: "sources",
      count: 3,
    });
  });

  it("reports 0 rows for an empty SQL result instead of going bare", () => {
    const result = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [] }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "read_query"), result })).toEqual({
      kind: "rows",
      count: 0,
    });
  });

  it("reports 0 rows for a SQL result that carries an error", () => {
    const result = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [], error: "syntax error" }));
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "read_query"), result })).toEqual({
      kind: "rows",
      count: 0,
    });
  });

  it("reports 0 rows for a query whose result came back in an unreadable shape", () => {
    const opaque = toolResultMsg("c1", "Tool error: binder error on column CA");
    expect(
      toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "mcp__knowledge_flow__read_query"), result: opaque }),
    ).toEqual({
      kind: "rows",
      count: 0,
    });
  });

  it("returns null for unrecognized, pending, failed and solo entries", () => {
    const opaque = toolResultMsg("c1", "plain text");
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "x"), result: opaque })).toBeNull();
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "x") })).toBeNull();
    const failed = toolResultMsg("c1", JSON.stringify({ sql_query: "SELECT 1", rows: [{ a: 1 }] }), false);
    expect(toolDiscriminator({ kind: "combo", call: toolCallMsg("c1", "x"), result: failed })).toBeNull();
    expect(toolDiscriminator({ kind: "solo", message: thoughtMsg("thinking") })).toBeNull();
  });
});

// ── humanizeToolName ──────────────────────────────────────────────────────────

describe("humanizeToolName", () => {
  it("handles MCP web_search → 'Searching the web'", () => {
    expect(humanizeToolName("mcp__tavily__web_search")).toBe("Searching the web");
  });

  it("handles bare web_search (no mcp prefix)", () => {
    expect(humanizeToolName("web_search")).toBe("Searching the web");
  });

  it("handles MCP verb-first with provider: search_issues → 'Searching GitHub issues'", () => {
    expect(humanizeToolName("mcp__github__search_issues")).toBe("Searching GitHub issues");
  });

  it("handles MCP create with provider: create_ticket → 'Creating Jira ticket'", () => {
    expect(humanizeToolName("mcp__jira__create_ticket")).toBe("Creating Jira ticket");
  });

  it("strips trailing numeric suffix before humanizing", () => {
    expect(humanizeToolName("mcp__jira__create_ticket_3")).toBe("Creating Jira ticket");
    expect(humanizeToolName("search_2")).toBe("Searching");
  });

  it("falls back to title-cased words for unknown tools without verbs", () => {
    expect(humanizeToolName("my_custom_tool")).toBe("My Custom Tool");
  });

  it("strips numeric suffix on unknown tools", () => {
    expect(humanizeToolName("my_custom_tool_3")).toBe("My Custom Tool");
  });

  it("handles single-word verb tools", () => {
    expect(humanizeToolName("search")).toBe("Searching");
    expect(humanizeToolName("create")).toBe("Creating");
  });

  it("handles tavily-search (raw name from tavily-mcp v0.2.x)", () => {
    expect(humanizeToolName("tavily-search")).toBe("Searching the web");
  });

  it("returns 'Tool' for empty string", () => {
    expect(humanizeToolName("")).toBe("Tool");
  });

  it("handles verb-at-end pattern (code_search)", () => {
    const result = humanizeToolName("code_search");
    expect(result).toContain("Searching");
    expect(result.toLowerCase()).toContain("code");
  });

  it("includes provider label for non-web MCP tools with no verb object", () => {
    expect(humanizeToolName("mcp__github__search")).toBe("Searching GitHub");
  });

  it("handles the ppt_filler capability tool (fill_ppt_template)", () => {
    expect(humanizeToolName("fill_ppt_template")).toBe("Generating the PowerPoint");
  });

  it("handles the writable_document capability tool (write_document)", () => {
    expect(humanizeToolName("write_document")).toBe("Writing document");
  });
});

// ── parseToolResultContent / asSqlQueryResult / asRagSearchResult ───────────

describe("parseToolResultContent", () => {
  it("parses valid JSON object content", () => {
    const result = toolResultMsg("c1", '{"foo":"bar"}');
    expect(parseToolResultContent(result)).toEqual({ foo: "bar" });
  });

  it("returns null for non-JSON content", () => {
    const result = toolResultMsg("c1", "plain text answer");
    expect(parseToolResultContent(result)).toBeNull();
  });

  it("returns null for JSON arrays (not an object)", () => {
    const result = toolResultMsg("c1", "[1,2,3]");
    expect(parseToolResultContent(result)).toBeNull();
  });
});

describe("asSqlQueryResult", () => {
  it("recognizes a RawSQLResponse-shaped object", () => {
    const data = { sql_query: "SELECT * FROM ships", rows: [{ id: 1 }], error: null };
    expect(asSqlQueryResult(data)).toEqual(data);
  });

  it("returns null when sql_query is missing", () => {
    expect(asSqlQueryResult({ rows: [] })).toBeNull();
  });

  it("returns null when rows is not an array", () => {
    expect(asSqlQueryResult({ sql_query: "SELECT 1", rows: "not an array" })).toBeNull();
  });

  it("returns null for null input", () => {
    expect(asSqlQueryResult(null)).toBeNull();
  });
});

describe("asRagSearchResult", () => {
  it("recognizes a {query, hits} shaped object", () => {
    const data = { query: "how many ships", hits: [{ uid: "u1", title: "t", content: "c", score: 0.9 }] };
    expect(asRagSearchResult(data)).toEqual(data);
  });

  it("returns null when query is missing", () => {
    expect(asRagSearchResult({ hits: [] })).toBeNull();
  });

  it("returns null when hits is not an array", () => {
    expect(asRagSearchResult({ query: "q", hits: "not an array" })).toBeNull();
  });

  it("returns null for null input", () => {
    expect(asRagSearchResult(null)).toBeNull();
  });

  it("does not misclassify a SQL result as a RAG result", () => {
    const sqlData = { sql_query: "SELECT 1", rows: [] };
    expect(asRagSearchResult(sqlData)).toBeNull();
  });
});

describe("isSummarizeDocumentTool / isDocumentTreeTool", () => {
  it("recognizes the exact first-party tool names only", () => {
    expect(isSummarizeDocumentTool("summarize_document")).toBe(true);
    expect(isSummarizeDocumentTool("list_document_tree")).toBe(false);
    expect(isSummarizeDocumentTool("mcp__tavily__web_search")).toBe(false);

    expect(isDocumentTreeTool("list_document_tree")).toBe(true);
    expect(isDocumentTreeTool("summarize_document")).toBe(false);
  });
});

describe("stripDocumentUids", () => {
  it("removes a bracketed uid after a document name", () => {
    expect(stripDocumentUids("report.pdf [doc-abc123] (2026-01-01)")).toBe("report.pdf (2026-01-01)");
  });

  it("strips uids on every line of a multi-line tree", () => {
    const tree = ["Sales", "  report.pdf [doc-1] (2026-01-01)", "  HR", "    notes.docx [doc-2] (2026-02-02)"].join(
      "\n",
    );
    expect(stripDocumentUids(tree)).toBe(
      ["Sales", "  report.pdf (2026-01-01)", "  HR", "    notes.docx (2026-02-02)"].join("\n"),
    );
  });

  it("leaves text with no bracketed uid unchanged", () => {
    expect(stripDocumentUids("Sales\n  HR")).toBe("Sales\n  HR");
  });

  it("strips folder tag ids rendered as [folder:tag-id] (issue #2244)", () => {
    const tree = ["docs [folder:8e0927eb-3650-4696-a21c-47e78d48f54f]/", "  report.pdf [doc-1] (2026-01-01)"].join(
      "\n",
    );
    expect(stripDocumentUids(tree)).toBe(["docs/", "  report.pdf (2026-01-01)"].join("\n"));
  });
});

describe("toolCopyText", () => {
  it("copies the raw summary text for summarize_document", () => {
    const call = toolCallMsg("c1", "summarize_document", { document_uid: "doc-1" });
    const result = toolResultMsg("c1", "This document is about...");
    const entries = groupTraceEntries([call, result]);
    expect(toolCopyText(entries[0])).toBe("This document is about...");
  });

  it("copies the uid-stripped tree text for list_document_tree", () => {
    const call = toolCallMsg("c1", "list_document_tree", {});
    const result = toolResultMsg("c1", "report.pdf [doc-1] (2026-01-01)");
    const entries = groupTraceEntries([call, result]);
    expect(toolCopyText(entries[0])).toBe("report.pdf (2026-01-01)");
  });

  it("falls back to the generic {action, status} payload when the tool call has no result yet", () => {
    const call = toolCallMsg("c1", "summarize_document", {});
    const entries = groupTraceEntries([call]);
    expect(JSON.parse(toolCopyText(entries[0]) ?? "")).toEqual({ action: "Summarize Document", status: "running" });
  });
});

// ── groupTraceEntries — deduplication ────────────────────────────────────────

describe("groupTraceEntries deduplication", () => {
  it("collapses duplicate tool_call messages with the same call_id into one row", () => {
    const call1 = toolCallMsg("c1", "search");
    const call1dup = toolCallMsg("c1", "search"); // same call_id, duplicate
    const result = toolResultMsg("c1", "found it");
    const entries = groupTraceEntries([call1, call1dup, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "combo", call: call1, result });
  });

  it("preserves args and result on the surviving combo entry", () => {
    const call = toolCallMsg("c1", "mcp__tavily__web_search", { query: "hello" });
    const callDup = toolCallMsg("c1", "mcp__tavily__web_search", { query: "hello" });
    const result = toolResultMsg("c1", "some result");
    const entries = groupTraceEntries([call, callDup, result]);
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("combo");
    if (entries[0].kind === "combo") {
      expect(entries[0].result).toBe(result);
    }
  });

  it("does not collapse tool_calls with different call_ids", () => {
    const call1 = toolCallMsg("c1", "search");
    const call2 = toolCallMsg("c2", "search");
    const entries = groupTraceEntries([call1, call2]);
    expect(entries).toHaveLength(2);
  });
});
