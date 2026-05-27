import { describe, it, expect } from "vitest";
import type { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import type { VectorSearchHit } from "../../slices/runtime/runtimeOpenApi";
import { hitToSource, chatMessagesToMessage, buildConversation, activeThread } from "./conversationUtils";

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

function userMsg(text: string, exchangeId = "e1"): ChatMessage {
  return msg({ role: "user", exchange_id: exchangeId, parts: [{ type: "text", text }] });
}

function assistantMsg(text: string, exchangeId = "e1", rank = 1): ChatMessage {
  return msg({ role: "assistant", exchange_id: exchangeId, rank, parts: [{ type: "text", text }] });
}

function hit(overrides: Partial<VectorSearchHit> = {}): VectorSearchHit {
  return {
    uid: "doc-1",
    title: "My Doc",
    content: "body text",
    score: 0.9,
    ...overrides,
  };
}

// ── hitToSource ───────────────────────────────────────────────────────────────

describe("hitToSource", () => {
  it("maps uid + index to a stable id", () => {
    const src = hitToSource(hit(), 0);
    expect(src.id).toBe("doc-1-0");
  });

  it("prefers repository over file_path for domain", () => {
    const src = hitToSource(hit({ repository: "my-repo", file_path: "my-repo/file.txt" }), 0);
    expect(src.domain).toBe("my-repo");
  });

  it("falls back to first path segment when repository is absent", () => {
    const src = hitToSource(hit({ repository: undefined, file_path: "org/project/file.md" }), 0);
    expect(src.domain).toBe("org");
  });

  it("falls back to 'document' when both repository and file_path are absent", () => {
    const src = hitToSource(hit({ repository: undefined, file_path: undefined }), 0);
    expect(src.domain).toBe("document");
  });

  it("prefers citation_url over repo_url for url", () => {
    const src = hitToSource(hit({ citation_url: "https://cite.example", repo_url: "https://repo.example" }), 0);
    expect(src.url).toBe("https://cite.example");
  });

  it("falls back to repo_url when citation_url absent", () => {
    const src = hitToSource(hit({ citation_url: undefined, repo_url: "https://repo.example" }), 0);
    expect(src.url).toBe("https://repo.example");
  });

  it("sets url to undefined when neither citation_url nor repo_url present", () => {
    const src = hitToSource(hit({ citation_url: undefined, repo_url: undefined }), 0);
    expect(src.url).toBeUndefined();
  });

  it("maps confidential to restricted", () => {
    expect(hitToSource(hit({ confidential: true }), 0).restricted).toBe(true);
    expect(hitToSource(hit({ confidential: false }), 0).restricted).toBe(false);
    expect(hitToSource(hit({ confidential: undefined }), 0).restricted).toBe(false);
  });

  it("passes score through", () => {
    expect(hitToSource(hit({ score: 0.75 }), 0).score).toBe(0.75);
  });
});

// ── chatMessagesToMessage ─────────────────────────────────────────────────────

describe("chatMessagesToMessage", () => {
  it("returns null when no user or assistant final message exists", () => {
    const trace = msg({ channel: "thought", parts: [{ type: "text", text: "thinking" }] });
    expect(chatMessagesToMessage([trace])).toBeNull();
  });

  it("produces a user-role message from user messages", () => {
    const result = chatMessagesToMessage([userMsg("hello")]);
    expect(result?.role).toBe("user");
    expect(result?.content).toEqual({ kind: "text", text: "hello" });
  });

  it("produces streaming content when streaming_delta flag is set", () => {
    const m = msg({
      role: "user",
      parts: [{ type: "text", text: "partial" }],
      metadata: { extras: { streaming_delta: true } },
    });
    const result = chatMessagesToMessage([m]);
    expect(result?.content).toEqual({ kind: "streaming", partial: "partial" });
  });

  it("returns null for a standalone error-channel message (error is a trace channel, not user/final)", () => {
    const m = msg({ channel: "error", parts: [{ type: "text", text: "boom" }] });
    expect(chatMessagesToMessage([m])).toBeNull();
  });

  it("picks the highest-rank final assistant message", () => {
    const low = assistantMsg("low rank", "e1", 0);
    const high = assistantMsg("high rank", "e1", 5);
    // pass only assistant messages
    const result = chatMessagesToMessage([low, high]);
    expect(result?.content).toEqual({ kind: "text", text: "high rank" });
  });

  it("collects trace messages from trace-channel entries", () => {
    const thought = msg({ channel: "thought", parts: [{ type: "text", text: "thinking" }] });
    const result = chatMessagesToMessage([userMsg("q"), thought]);
    expect(result?.trace).toHaveLength(1);
    expect(result?.trace[0].role).toBe("thought");
    expect(result?.trace[0].content).toBe("thinking");
  });

  it("classifies tool_call and tool_result trace entries as 'tool'", () => {
    const toolCall = msg({
      channel: "tool_call",
      parts: [{ type: "tool_call", call_id: "c1", name: "search", args: {} }],
    });
    const toolResult = msg({
      channel: "tool_result",
      role: "tool" as ChatMessage["role"],
      parts: [{ type: "tool_result", call_id: "c1", ok: true, content: "result", latency_ms: null }],
    });
    const result = chatMessagesToMessage([userMsg("q"), toolCall, toolResult]);
    const roles = result?.trace.map((t) => t.role);
    expect(roles).toEqual(["tool", "tool"]);
  });

  it("attaches parentId when provided", () => {
    const result = chatMessagesToMessage([userMsg("q")], "parent-42");
    expect(result?.parentId).toBe("parent-42");
  });

  it("initialises childrenIds as empty and activeChildId as null", () => {
    const result = chatMessagesToMessage([userMsg("q")]);
    expect(result?.childrenIds).toEqual([]);
    expect(result?.activeChildId).toBeNull();
  });
});

// ── buildConversation ─────────────────────────────────────────────────────────

describe("buildConversation", () => {
  it("returns an empty conversation for empty message list", () => {
    const conv = buildConversation("s1", "Empty", []);
    expect(conv.id).toBe("s1");
    expect(conv.title).toBe("Empty");
    expect(conv.rootMessageIds).toHaveLength(0);
    expect(Object.keys(conv.messages)).toHaveLength(0);
  });

  it("groups user and assistant messages by exchange_id into a tree", () => {
    const u = userMsg("hello", "e1");
    const a = assistantMsg("world", "e1");
    const conv = buildConversation("s1", "Chat", [u, a]);

    // one root entry — the user message
    expect(conv.rootMessageIds).toHaveLength(1);

    const rootId = conv.rootMessageIds[0];
    const root = conv.messages[rootId];
    expect(root.role).toBe("user");
    expect(root.childrenIds).toHaveLength(1);

    // assistant gets a ':reply'-suffixed id to avoid colliding with the user entry
    const childId = root.childrenIds[0];
    expect(childId).toBe(`${rootId}:reply`);
    const child = conv.messages[childId];
    expect(child.role).toBe("assistant");
    expect(child.parentId).toBe(rootId);
  });

  it("handles two separate exchanges independently", () => {
    const messages = [userMsg("q1", "e1"), assistantMsg("a1", "e1"), userMsg("q2", "e2"), assistantMsg("a2", "e2")];
    const conv = buildConversation("s1", "Two turns", messages);
    expect(conv.rootMessageIds).toHaveLength(2);
    const total = Object.keys(conv.messages).length;
    // 2 user messages + 2 assistant reply messages (each with ':reply' suffix)
    expect(total).toBe(4);
  });

  it("sets activeChildId to the assistant message id", () => {
    const u = userMsg("hi", "e1");
    const a = assistantMsg("hey", "e1");
    const conv = buildConversation("s1", "Test", [u, a]);

    const rootId = conv.rootMessageIds[0];
    const root = conv.messages[rootId];
    expect(root.activeChildId).toBe(root.childrenIds[0]);
    expect(root.activeChildId).not.toBeNull();
  });
});

// ── activeThread ──────────────────────────────────────────────────────────────

describe("activeThread", () => {
  it("returns empty array for empty conversation", () => {
    const conv = buildConversation("s1", "Empty", []);
    expect(activeThread(conv)).toEqual([]);
  });

  it("returns messages in display order (user then assistant)", () => {
    const u = userMsg("hello", "e1");
    const a = assistantMsg("world", "e1");
    const conv = buildConversation("s1", "Chat", [u, a]);

    const thread = activeThread(conv);
    expect(thread).toHaveLength(2);
    expect(thread[0].role).toBe("user");
    expect(thread[1].role).toBe("assistant");
  });

  it("flattens multiple exchanges in order", () => {
    const messages = [userMsg("q1", "e1"), assistantMsg("a1", "e1"), userMsg("q2", "e2"), assistantMsg("a2", "e2")];
    const conv = buildConversation("s1", "Two turns", messages);
    const thread = activeThread(conv);
    // 4 messages total: u1, a1, u2, a2 — Map preserves insertion order
    expect(thread).toHaveLength(4);
    const roles = thread.map((m) => m.role);
    // Each exchange inserts user then assistant; two exchanges → [u,a,u,a]
    expect(roles).toEqual(["user", "assistant", "user", "assistant"]);
  });

  it("skips branches that have no activeChildId", () => {
    // Only user, no assistant reply yet
    const conv = buildConversation("s1", "Partial", [userMsg("pending", "e1")]);
    const thread = activeThread(conv);
    expect(thread).toHaveLength(1);
    expect(thread[0].role).toBe("user");
  });
});
