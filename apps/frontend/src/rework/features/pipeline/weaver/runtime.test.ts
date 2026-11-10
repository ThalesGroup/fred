// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it, vi } from "vitest";
import { runRuntimeProbe, runRuntimeTurn } from "./runtime";
import type { WeaverChecks } from "./checks";

vi.mock("../sessionCredential", () => ({
  captureSessionCredential: () => ({ credential: "private-test-value", secondsLeft: 40 }),
}));
const api = vi.hoisted(() =>
  Object.fromEntries(
    ["prepareExecution", "createSession", "deleteSession", "getSession", "listSessions"].map((name) => [
      name,
      { initiate: (args: unknown) => ({ name, args }) },
    ]),
  ),
);
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: { endpoints: api },
}));
const dispatch = vi.fn();
const checks = {
  spaceId: "space",
  userId: "operator",
  dispatch: (action: unknown) => ({ unwrap: () => dispatch(action) }),
} as unknown as WeaverChecks;

function response(content: string) {
  return new Response(`data: ${JSON.stringify({ kind: "final", content })}\n\n`, { status: 200 });
}

describe("bound runtime diagnostic", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    dispatch.mockReset().mockImplementation(async ({ name, args }) => {
      if (name === "prepareExecution")
        return { execute_stream_url: "/control-plane/v1/agents/execute/stream", agent_configuration_revision: 3 };
      if (name === "createSession") return { ...args.createSessionRequest, space_id: args.spaceId };
      if (name === "deleteSession")
        return {
          id: "deletion",
          target_id: args.sessionId,
          target_parent_id: args.spaceId,
          target_kind: "session",
          actor_subject: "operator",
          status: "completed",
          due_at: new Date().toISOString(),
        };
      if (name === "getSession") throw { status: 404 };
      if (name === "listSessions") return [];
      throw new Error("Unexpected operation");
    });
  });
  it("registers the conversation before execution and removes it after the turn", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => {
      const creation = dispatch.mock.calls.find(([call]) => call.name === "createSession")![0].args;
      expect(creation.createSessionRequest.agent_configuration_revision).toBe(3);
      expect(creation.createSessionRequest.agent_instance_id).toBe("agent");
      expect(JSON.parse(options!.body as string).session_id).toBe(creation.createSessionRequest.session_id);
      expect(dispatch.mock.calls.some(([call]) => call.name === "deleteSession")).toBe(false);
      return response("Echo: diagnostic");
    });
    await runRuntimeTurn(checks, "agent", new AbortController().signal, "echo diagnostic");
    const sessionId = JSON.parse(fetch.mock.calls[0][1]!.body as string).session_id;
    expect(dispatch).toHaveBeenCalledWith({
      name: "deleteSession",
      args: { spaceId: "space", sessionId, immediate: true },
    });
    expect(dispatch.mock.calls.map(([call]) => call.name)).toEqual([
      "prepareExecution",
      "createSession",
      "deleteSession",
      "getSession",
      "listSessions",
    ]);
  });
  it("does not execute when registration fails", async () => {
    const original = dispatch.getMockImplementation()!;
    dispatch.mockImplementation((call) => {
      if (call.name === "createSession") throw new Error("Registration failed");
      return original(call);
    });
    const fetch = vi.spyOn(globalThis, "fetch");
    await expect(runRuntimeTurn(checks, "agent", new AbortController().signal, "echo diagnostic")).rejects.toThrow(
      "Registration failed",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(["rejected", "stream error", "aborted"])("cleans its conversation after execution is %s", async (failure) => {
    const controller = new AbortController();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      if (failure === "rejected") return new Response(null, { status: 403 });
      if (failure === "aborted") controller.abort();
      return new Response('data: {"kind":"execution_error"}\n\n');
    });
    await expect(runRuntimeTurn(checks, "agent", controller.signal, "echo diagnostic")).rejects.toThrow();
    expect(dispatch.mock.calls.some(([call]) => call.name === "deleteSession")).toBe(true);
  });
  it("reuses a caller-owned conversation without creating or deleting it", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response("Echo: diagnostic"));
    await runRuntimeTurn(checks, "agent", new AbortController().signal, "echo diagnostic", { sessionId: "existing" });
    expect(JSON.parse(fetch.mock.calls[0][1]!.body as string).session_id).toBe("existing");
    expect(dispatch.mock.calls.map(([call]) => call.name)).toEqual(["prepareExecution"]);
  });
  it("reports unsuccessful conversation cleanup", async () => {
    const original = dispatch.getMockImplementation()!;
    dispatch.mockImplementation((call) => {
      if (call.name === "deleteSession") throw new Error("Cleanup failed");
      return original(call);
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response("Echo: diagnostic"));
    await expect(runRuntimeTurn(checks, "agent", new AbortController().signal, "echo diagnostic")).rejects.toThrow(
      "Cleanup failed",
    );
  });
  it("derives a bounded hold from the credential used for admission without returning it", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(response('RUNTIME-PROBE {"mode":"expiry","before":true,"after":true}'));
    const value = await runRuntimeProbe(checks, "agent", new AbortController().signal, { mode: "expiry" });
    const body = JSON.parse(fetch.mock.calls[0][1]!.body as string);
    expect(JSON.parse(body.input.slice("runtime probe ".length)).hold_seconds).toBe(55);
    expect(body.runtime_context.space_id).toBe("space");
    expect(JSON.stringify(value)).not.toContain("private-test-value");
  });
  it("does not copy a malformed diagnostic answer into failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response("private-test-value"));
    await expect(runRuntimeProbe(checks, "agent", new AbortController().signal, { mode: "web" })).rejects.toThrow(
      "The agent did not return the diagnostic contract.",
    );
  });
  it("reports unavailable web research as skipped", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response('RUNTIME-PROBE {"mode":"web","unavailable":true}'));
    await expect(runRuntimeProbe(checks, "agent", new AbortController().signal, { mode: "web" })).rejects.toThrow(
      "Web research is unavailable",
    );
  });
});
