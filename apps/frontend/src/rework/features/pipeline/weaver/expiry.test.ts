// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { expiry } from "./runtime";
import type { WeaverChecks } from "./checks";
import type { StepReport } from "../types";

const mock = vi.hoisted(() => ({ cleanup: vi.fn(), deleteConversation: vi.fn(), refresh: vi.fn() }));
vi.mock("../../../../security/KeycloakService", () => ({ KeyCloakService: { ensureFreshToken: mock.refresh } }));
vi.mock("../sessionCredential", () => ({
  captureSessionCredential: () => ({ credential: "private-captured", secondsLeft: 40 }),
}));
vi.mock("./resourceSupport", async (original) => ({
  ...(await original<typeof import("./resourceSupport")>()),
  cp: Object.fromEntries(
    ["prepareExecution", "deleteAgentInstance", "getAgentInstance"].map((name) => [name, { initiate: () => name }]),
  ),
  provisionDisposableAgent: async () => ({ agent_instance_id: "agent" }),
  ingestKnowledgeFixture: async () => ({ documentId: "fixture", text: "marker", cleanup: mock.cleanup }),
  registerTestConversation: async () => "conversation",
  deleteTestConversation: mock.deleteConversation,
}));
const dispatch = vi.fn();
const checks = {
  spaceId: "space",
  dispatch: (action: unknown) => ({ unwrap: () => dispatch(action) }),
} as unknown as WeaverChecks;
const origin = Date.parse("2026-01-01T00:00:00Z");
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(origin);
  vi.clearAllMocks();
  mock.refresh.mockResolvedValue(true);
  dispatch.mockImplementation(async (name) => {
    if (name === "prepareExecution") return { execute_stream_url: "/control-plane/v1/agents/execute/stream" };
    if (name === "getAgentInstance") throw { status: 404 };
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function run(
  options: { rejected?: number; baseline?: boolean; early?: boolean; executionFailure?: boolean } = {},
) {
  let identityCalls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer private-captured");
    if (url === "/control-plane/v1/me")
      return new Response("{}", { status: identityCalls++ === 0 ? 200 : (options.rejected ?? 401) });
    expect(JSON.parse(init!.body as string).runtime_context.selected_document_uids).toEqual(["fixture"]);
    if (options.executionFailure) return new Response(null, { status: 403 });
    if (!options.early) await vi.advanceTimersByTimeAsync(45000);
    vi.setSystemTime(origin + (options.early ? 20000 : 60000));
    const diagnostic = {
      mode: "expiry",
      before: true,
      after: true,
      before_at: origin / 1000,
      after_at: (origin + (options.early ? 20000 : 55000)) / 1000,
    };
    const events = [
      ...(options.baseline === false ? [] : [{ kind: "status", status: "runtime_probe_baseline" }]),
      { kind: "final", content: `RUNTIME-PROBE ${JSON.stringify(diagnostic)}` },
    ];
    return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""));
  });
  const steps: StepReport[] = [];
  await expiry(checks, (step) => steps.push(step), new AbortController().signal);
  expect(mock.cleanup).toHaveBeenCalledOnce();
  expect(mock.deleteConversation).toHaveBeenCalledOnce();
  expect(dispatch).toHaveBeenCalledWith("deleteAgentInstance");
  expect(JSON.stringify(steps)).not.toContain("private-captured");
  return steps;
}
it("reports before/wait/after access and rejection of the original credential", async () => {
  const steps = await run();
  expect(steps).toContainEqual(expect.objectContaining({ id: "baseline-access", status: "passed" }));
  expect(steps).toContainEqual(
    expect.objectContaining({ id: "expiry-turn", status: "running", detail: expect.stringContaining("Waiting") }),
  );
  expect(steps).toContainEqual(
    expect.objectContaining({ id: "expiry-turn", status: "passed", detail: expect.stringContaining("HTTP 401") }),
  );
});
it.each([200, 403, 500])("does not claim expiry when the original credential returns %s", async (rejected) => {
  const steps = await run({ rejected });
  expect(steps).toContainEqual(
    expect.objectContaining({ id: "expiry-turn", status: "failed", error: expect.stringContaining("Inconclusive") }),
  );
});
it("rejects a diagnostic without baseline evidence", async () => {
  const steps = await run({ baseline: false });
  expect(steps).toContainEqual(expect.objectContaining({ id: "baseline-access", status: "failed" }));
  expect(steps).not.toContainEqual(expect.objectContaining({ id: "expiry-turn", status: "passed" }));
});
it("rejects retrieval that completed before expiry", async () => {
  const steps = await run({ early: true });
  expect(steps).toContainEqual(expect.objectContaining({ id: "expiry-turn", status: "failed" }));
});
it("settles the baseline and cleans up after admission fails", async () => {
  const steps = await run({ executionFailure: true });
  expect(steps).toContainEqual(expect.objectContaining({ id: "baseline-access", status: "skipped" }));
  expect(steps).toContainEqual(expect.objectContaining({ id: "expiry-turn", status: "failed" }));
});
