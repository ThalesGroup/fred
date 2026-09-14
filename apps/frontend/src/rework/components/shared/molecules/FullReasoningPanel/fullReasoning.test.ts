import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import { fullReasoning, fullReasoningMarkdown } from "./fullReasoning";

let rank = 0;
function msg(exchange: string, overrides: Partial<ChatMessage>): ChatMessage {
  return {
    session_id: "s1",
    exchange_id: exchange,
    rank: rank++,
    timestamp: "2026-01-01T00:00:00.000Z",
    role: "assistant",
    channel: "final",
    parts: [],
    ...overrides,
  };
}

const question = (exchange: string, text: string) =>
  msg(exchange, { role: "user", channel: "final", parts: [{ type: "text", text }] });
const thought = (exchange: string, text: string, extras: Record<string, unknown> = {}) =>
  msg(exchange, {
    channel: "thought",
    parts: [{ type: "text", text }],
    metadata: { extras: { thought_id: `t${rank}`, ...extras } },
  });
const call = (exchange: string, id: string, name: string) =>
  msg(exchange, { channel: "tool_call", parts: [{ type: "tool_call", call_id: id, name, args: {} }] });
const result = (exchange: string, id: string) =>
  msg(exchange, {
    channel: "tool_result",
    role: "tool",
    parts: [{ type: "tool_result", call_id: id, ok: true, content: "{}" }],
  });
const answer = (exchange: string, text: string) => msg(exchange, { parts: [{ type: "text", text }] });

describe("fullReasoning", () => {
  it("returns no turn for a conversation without reasoning", () => {
    expect(fullReasoning([question("e1", "Hi"), answer("e1", "Hello")])).toEqual([]);
  });

  it("groups every turn's reasoning under its question, in order", () => {
    const turns = fullReasoning([
      question("e1", "List the files"),
      thought("e1", "I will list them."),
      answer("e1", "Here they are."),
      question("e2", "Summarise one"),
      thought("e2", "Picking the first file."),
    ]);

    expect(turns.map((turn) => turn.question)).toEqual(["List the files", "Summarise one"]);
    expect(turns.map((turn) => turn.steps.map((step) => step.kind === "reasoning" && step.text))).toEqual([
      ["I will list them."],
      ["Picking the first file."],
    ]);
  });

  // The chain of thought trims a block of what earlier blocks said; this view
  // is the untouched record.
  it("keeps every block whole, restatements included", () => {
    const restated = "The user wants a summary. I will list the files.";
    const turns = fullReasoning([
      question("e1", "Go"),
      thought("e1", restated),
      thought("e1", `${restated} Now reading the first one.`),
    ]);

    expect(turns[0].steps).toMatchObject([
      { kind: "reasoning", text: restated },
      { kind: "reasoning", text: `${restated} Now reading the first one.` },
    ]);
  });

  it("collapses the tools run between two blocks into one marker, and only between blocks", () => {
    const turns = fullReasoning([
      question("e1", "Go"),
      call("e1", "c0", "list_document_tree"),
      result("e1", "c0"),
      thought("e1", "First block."),
      call("e1", "c1", "list_document_tree"),
      result("e1", "c1"),
      call("e1", "c2", "summarize_document"),
      thought("e1", "Second block."),
      call("e1", "c3", "write_document"),
    ]);

    expect(turns[0].steps.map((step) => step.kind)).toEqual(["reasoning", "tools", "reasoning"]);
    expect(turns[0].steps[1]).toMatchObject({ kind: "tools", labels: ["Listing document tree", "Summarize Document"] });
  });

  it("carries a block's duration, and keeps a streaming block that has no text yet", () => {
    const turns = fullReasoning([
      question("e1", "Go"),
      thought("e1", "Done thinking.", { duration_ms: 1200 }),
      thought("e1", "", { streaming_delta: true }),
      thought("e1", ""),
    ]);

    expect(turns[0].steps).toMatchObject([
      { kind: "reasoning", durationMs: 1200, streaming: false },
      { kind: "reasoning", text: "", streaming: true },
    ]);
  });
});

describe("fullReasoning — restatements hidden", () => {
  const restated = "The user wants a summary. I will list the files.";
  const conversation = () => [
    question("e1", "Go"),
    thought("e1", restated),
    thought("e1", `${restated}\n\n- **Read** the first file`),
    thought("e1", restated),
  ];

  it("trims each block of what the turn already said, markdown kept", () => {
    const [turn] = fullReasoning(conversation(), true);
    expect(turn.steps).toMatchObject([
      { kind: "reasoning", text: restated, restated: false },
      { kind: "reasoning", text: "- **Read** the first file", restated: false },
      { kind: "reasoning", text: "", restated: true },
    ]);
  });

  it("marks a restated block in the copied markdown", () => {
    const markdown = fullReasoningMarkdown(fullReasoning(conversation(), true), "Restated");
    expect(markdown).toBe(["## Go", restated, "- **Read** the first file", "_Restated_"].join("\n\n"));
  });

  it("leaves every block whole while the toggle is off", () => {
    const [turn] = fullReasoning(conversation());
    expect(
      turn.steps.every((step) => step.kind === "reasoning" && !step.restated && step.text.startsWith(restated)),
    ).toBe(true);
  });
});

describe("fullReasoningMarkdown", () => {
  it("renders each turn as a heading followed by its blocks and tool markers", () => {
    const turns = fullReasoning([
      question("e1", "List\nthe files"),
      thought("e1", "First block."),
      call("e1", "c1", "list_document_tree"),
      thought("e1", "Second block."),
      question("e2", "Next"),
      thought("e2", "Third block."),
    ]);

    expect(fullReasoningMarkdown(turns, "Restated")).toBe(
      [
        "## List the files",
        "First block.",
        "_→ Listing document tree_",
        "Second block.",
        "## Next",
        "Third block.",
      ].join("\n\n"),
    );
  });
});
