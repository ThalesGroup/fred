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
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentTurnExecutionError, AgentTurnRejectedError, isCredentialExpiryFailure, streamAgentTurn } from "./actions";
import type { CapturedCredential } from "./sessionCredential";
import type { ExecutionPreparation } from "../../../slices/controlPlane/controlPlaneOpenApi";

const PREP = {
  execute_stream_url: "https://runtime.example/execute/stream",
  context_prompt_text: null,
  chat_default_profile_id: null,
  agent_profile_overrides: {},
  reasoning_enabled_model_ids: [],
} as unknown as ExecutionPreparation;

const ARGS = {
  agentInstanceId: "inst-1",
  teamId: "team-1",
  question: "is the marker still reachable?",
  libraryIds: ["lib-1"],
  // Stands in for a credential taken from the live session; the brand is what
  // stops production code pinning a turn to an arbitrary string.
  bearer: "probe-bearer" as CapturedCredential,
};

function sseBody(frames: string): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(frames));
      controller.close();
    },
  });
}

afterEach(() => vi.unstubAllGlobals());

it("refuses to pin a turn to a credential that did not come from the session", () => {
  // @ts-expect-error a bare string is not a CapturedCredential
  const pinned: CapturedCredential = "not-from-the-session";
  expect(typeof pinned).toBe("string");
});

describe("streamAgentTurn", () => {
  it("keeps hold evidence on a safe execution error", async () => {
    const frames =
      'data: {"kind":"status","status":"hold"}\n\n' +
      'data: {"kind":"execution_error","message":"credential expired during protected call"}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, body: sseBody(frames) })),
    );
    await expect(streamAgentTurn(PREP, ARGS)).rejects.toMatchObject({
      statusSeenAt: { hold: expect.any(Number) },
      credentialExpired: true,
    });
    await expect(streamAgentTurn(PREP, ARGS)).rejects.toBeInstanceOf(AgentTurnExecutionError);
  });

  it("classifies the expiry that arrives as the turn's own final answer", async () => {
    const frames =
      'data: {"kind":"status","status":"hold"}\n\n' +
      'data: {"kind":"final","content":"An error occurred: credential expired during protected call"}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, body: sseBody(frames) })),
    );
    const turn = await streamAgentTurn(PREP, ARGS);
    expect(isCredentialExpiryFailure(turn.answer)).toBe(true);
    expect(turn.statusSeenAt).toMatchObject({ hold: expect.any(Number) });
  });

  it("does not expose or classify an arbitrary 401 error as expiry", async () => {
    const frames = 'data: {"kind":"node_error","error_message":"401 invalid audience at https://service.invalid"}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, body: sseBody(frames) })),
    );
    await expect(streamAgentTurn(PREP, ARGS)).rejects.toMatchObject({
      message: "agent execution failed",
      credentialExpired: false,
    });
  });

  it("forwards safe hold progress while the stream is still open", async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start: (value) => {
        controller = value;
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, body })),
    );
    const onProgress = vi.fn();
    const turn = streamAgentTurn(PREP, { ...ARGS, onProgress });
    controller.enqueue(
      new TextEncoder().encode('data: {"kind":"thought_delta","delta":"holding 10/60 s before retrieval"}\n\n'),
    );
    await vi.waitFor(() => expect(onProgress).toHaveBeenCalledWith("holding 10/60 s before retrieval"));
    controller.enqueue(
      new TextEncoder().encode(
        'data: {"kind":"thought_delta","delta":"arbitrary upstream text"}\n\n' +
          'data: {"kind":"final","content":"done"}\n\n',
      ),
    );
    controller.close();
    await turn;
    expect(onProgress).toHaveBeenCalledTimes(1);
  });

  it("passes cancellation to the stream request and does not start when already aborted", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      body: sseBody('data: {"kind":"final","content":"done"}\n\n'),
    }));
    vi.stubGlobal("fetch", fetchMock);
    await streamAgentTurn(PREP, { ...ARGS, signal: controller.signal });
    expect(fetchMock).toHaveBeenCalledWith(
      PREP.execute_stream_url,
      expect.objectContaining({ signal: controller.signal }),
    );
    controller.abort();
    await expect(streamAgentTurn(PREP, { ...ARGS, signal: controller.signal })).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("throws the typed rejection with the status when the stream request is refused", async () => {
    const fetchMock = vi.fn(async () => ({ ok: false, status: 403, body: null }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(streamAgentTurn(PREP, ARGS)).rejects.toMatchObject({ status: 403 });
    await expect(streamAgentTurn(PREP, ARGS)).rejects.toBeInstanceOf(AgentTurnRejectedError);
    // The explicit bearer is what goes on the wire — not the caller's session.
    const headers = (fetchMock.mock.calls[0] as unknown as [string, { headers: Record<string, string> }])[1].headers;
    expect(headers.Authorization).toBe("Bearer probe-bearer");
  });

  it("hands each status to the caller as it arrives, before the stream ends", async () => {
    const frames =
      'data: {"kind":"status","status":"credential_baseline"}\n\n' +
      'data: {"kind":"status","status":"hold"}\n\n' +
      'data: {"kind":"final","content":"done","sources":[],"session_id":"s-1"}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, body: sseBody(frames) })),
    );
    const seen: string[] = [];

    await streamAgentTurn(PREP, { ...ARGS, onStatus: (status) => seen.push(status) });

    expect(seen).toEqual(["credential_baseline", "hold"]);
  });

  it("records when a named status arrived and returns the final answer", async () => {
    const before = Date.now();
    const frames =
      'data: {"kind":"status","status":"hold","detail":"60/60 s before retrieval"}\n\n' +
      'data: {"kind":"final","content":"SELF-TEST retrieved 1 chunk(s)","sources":[],"session_id":"s-1"}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, body: sseBody(frames) })),
    );

    const turn = await streamAgentTurn(PREP, ARGS);

    expect(turn.answer).toBe("SELF-TEST retrieved 1 chunk(s)");
    expect(turn.sessionId).toBe("s-1");
    expect(turn.statusSeenAt?.hold).toBeGreaterThanOrEqual(before);
    expect(turn.statusSeenAt?.hold).toBeLessThanOrEqual(Date.now());
  });
});
