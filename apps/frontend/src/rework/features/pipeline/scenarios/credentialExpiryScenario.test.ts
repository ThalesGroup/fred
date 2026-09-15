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

import { beforeEach, describe, expect, it, vi } from "vitest";
import { credentialExpiryScenario } from "./credentialExpiryScenario";
import { SELF_TEST_AGENT_ID } from "./corpus";
import { AgentTurnExecutionError, AgentTurnRejectedError } from "../actions";
import { MAX_HOLD_MINUTES, type PipelineDeps, type StepReport } from "../types";

const NOW = 1_000_000;
const auth = vi.hoisted(() => ({
  configured: true,
  fresh: vi.fn(),
  token: "synthetic-session-token",
  secondsLeft: 300 as number | null,
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetKeycloakRealmConfig: () => (auth.configured ? {} : null),
    ensureFreshToken: auth.fresh,
    GetToken: () => auth.token,
    GetTokenSecondsLeft: () => auth.secondsLeft,
  },
}));

function setup() {
  const reports: StepReport[] = [];
  const forbidden = vi.fn(async () => {
    throw new Error("unexpected resource mutation");
  });
  const deps: PipelineDeps = {
    teamId: "personal-test",
    createLibrary: forbidden,
    deleteLibrary: forbidden,
    listLibraries: forbidden,
    ingestDocument: forbidden,
    provisionAgentInstance: vi.fn(async () => "temporary-instance"),
    deleteAgentInstance: vi.fn(async () => {}),
    createContextPrompt: forbidden,
    deleteContextPrompt: forbidden,
    createSession: forbidden,
    attachSessionPrompts: forbidden,
    deleteSession: forbidden,
    runAgentTurn: vi.fn(async () => ({
      answer: "Authenticated check completed.",
      sources: [],
      sessionId: null,
      statusSeenAt: {
        credential_baseline: NOW + 315_000,
        hold: NOW + 315_000,
        protected_call_succeeded: NOW + 316_000,
        credential_renewed: NOW + 316_000,
      },
    })),
  };
  const scenario = credentialExpiryScenario({ now: () => NOW });
  return {
    deps,
    forbidden,
    reports,
    run: (signal = new AbortController().signal) => scenario(deps, (step) => reports.push(step), signal),
    step: (id: string) => {
      const matching = reports.filter((step) => step.id === id);
      return matching[matching.length - 1];
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.configured = true;
  auth.fresh.mockResolvedValue(true);
  auth.token = "synthetic-session-token";
  auth.secondsLeft = 300;
});

describe("SSO credential expiry", () => {
  it("runs on the captured SSO token without document or permission mutations", async () => {
    const test = setup();
    await test.run();
    expect(test.step("expiry-turn")?.status).toBe("passed");
    expect(test.forbidden).not.toHaveBeenCalled();
    expect(test.deps.runAgentTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        bearer: "synthetic-session-token",
        libraryIds: [],
      }),
    );
    expect(test.deps.provisionAgentInstance).toHaveBeenCalledWith(
      expect.any(String),
      { "settings.hold_seconds": 315, "settings.check_access": true },
      expect.any(AbortSignal),
    );
    expect(test.deps.deleteAgentInstance).toHaveBeenCalledExactlyOnceWith("temporary-instance");
  });
});

describe("pre-expiry evidence", () => {
  it("reports access before expiry the moment the agent proves it, not when the turn ends", async () => {
    const test = setup();
    let seenDuringTurn: StepReport | undefined;
    vi.mocked(test.deps.runAgentTurn).mockImplementation(async (args) => {
      args.onStatus?.("credential_baseline");
      seenDuringTurn = test.step("baseline-access");
      return {
        answer: "Authenticated check completed.",
        sources: [],
        sessionId: null,
        statusSeenAt: {
          credential_baseline: NOW + 315_000,
          hold: NOW + 315_000,
          protected_call_succeeded: NOW + 316_000,
          credential_renewed: NOW + 316_000,
        },
      };
    });

    await test.run();

    expect(seenDuringTurn?.status).toBe("passed");
    expect(test.step("baseline-access")?.status).toBe("passed");
    // Timed like every other row, so the report reads consistently.
    expect(test.step("baseline-access")?.durationMs).toEqual(expect.any(Number));
    expect(test.step("expiry-turn")?.status).toBe("passed");
  });

  it("fails the pre-expiry step when the agent never proved access", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockResolvedValue({
      answer: "Authenticated check completed.",
      sources: [],
      sessionId: null,
      statusSeenAt: { hold: NOW + 315_000, protected_call_succeeded: NOW + 316_000 },
    });

    await test.run();

    expect(test.step("baseline-access")?.status).toBe("failed");
    expect(test.step("expiry-turn")?.status).toBe("failed");
  });

  it("reports the pre-expiry step above the turn it precedes", async () => {
    const test = setup();

    await test.run();

    // Rows are ordered by first appearance, so the evidence must be announced
    // before the step that waits for it, not from inside it.
    const order = [...new Set(test.reports.map((step) => step.id))];
    expect(order.indexOf("baseline-access")).toBeLessThan(order.indexOf("expiry-turn"));
  });

  it("leaves no pre-expiry step running when the turn never started", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockRejectedValue(new AgentTurnRejectedError(401));

    await test.run();

    expect(test.step("baseline-access")?.status).toBe("skipped");
  });

  it("says which kind of agent the run creates, without naming the template", async () => {
    const test = setup();

    await test.run();

    const step = test.step("provision-agent");
    expect(step?.title).toContain("graph agent");
    expect(step?.title).not.toContain(SELF_TEST_AGENT_ID);
    expect(step?.detail).toContain("no model calls");
    // The report identifies the kind of agent, never the instance it created.
    expect(step?.detail).not.toContain("temporary-instance");
  });
});

describe("expiry test guards", () => {
  it.each([null, 0, -1, Number.NaN, Number.POSITIVE_INFINITY])(
    "refuses unknown or invalid remaining time %s",
    async (remaining) => {
      auth.secondsLeft = remaining;
      const test = setup();
      await test.run();
      expect(test.step("session-token")?.status).toBe("failed");
      expect(test.deps.provisionAgentInstance).not.toHaveBeenCalled();
      expect(test.forbidden).not.toHaveBeenCalled();
    },
  );
  it("skips without secure SSO", async () => {
    auth.configured = false;
    const test = setup();
    await test.run();
    expect(test.step("session-token")?.status).toBe("skipped");
    expect(auth.fresh).not.toHaveBeenCalled();
    expect(test.deps.provisionAgentInstance).not.toHaveBeenCalled();
  });
  it("skips a wait exceeding the bounded agent hold, quoting the bound it enforces", async () => {
    auth.secondsLeft = 900;
    const test = setup();
    await test.run();
    expect(test.step("session-token")?.status).toBe("skipped");
    expect(test.step("session-token")?.detail).toContain(`${MAX_HOLD_MINUTES}-minute`);
    expect(test.deps.provisionAgentInstance).not.toHaveBeenCalled();
  });
  it("reports a failed session refresh without exposing the cause", async () => {
    auth.fresh.mockRejectedValue(new Error("private response"));
    const test = setup();
    await test.run();
    expect(test.step("session-token")?.status).toBe("failed");
    expect(JSON.stringify(test.reports)).not.toContain("private response");
    expect(test.deps.provisionAgentInstance).not.toHaveBeenCalled();
  });
  it("holds the captured token even when the browser refreshes during preparation", async () => {
    const test = setup();
    vi.mocked(test.deps.provisionAgentInstance).mockImplementation(async () => {
      auth.token = "replacement-browser-token";
      return "temporary-instance";
    });
    await test.run();
    expect(test.deps.runAgentTurn).toHaveBeenCalledWith(expect.objectContaining({ bearer: "synthetic-session-token" }));
    expect(JSON.stringify(test.reports)).not.toContain("synthetic-session-token");
  });
  it("fails expiry after the initial protected call succeeded", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockRejectedValue(
      new AgentTurnExecutionError({ credential_baseline: NOW, hold: NOW + 315_000 }, true),
    );
    await test.run();
    expect(test.step("expiry-turn")?.error).toContain("expired during the protected call");
    expect(test.deps.deleteAgentInstance).toHaveBeenCalledExactlyOnceWith("temporary-instance");
    expect(test.forbidden).not.toHaveBeenCalled();
  });
  it("fails expiry when the refusal arrives as the turn's own answer", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockResolvedValue({
      answer: "An error occurred: credential expired during protected call",
      sources: [],
      sessionId: null,
      statusSeenAt: { credential_baseline: NOW, hold: NOW + 315_000 },
    });
    await test.run();
    expect(test.step("expiry-turn")?.error).toContain("expired during the protected call");
    expect(test.deps.deleteAgentInstance).toHaveBeenCalledExactlyOnceWith("temporary-instance");
  });
  it.each([
    ["protected call refused", "refused, but not because the credential expired"],
    ["protected call failed", "did not reach the service"],
  ])("tells %s apart from a missing post-hold success", async (verdict, expected) => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockResolvedValue({
      answer: `An error occurred: ${verdict}`,
      sources: [],
      sessionId: null,
      statusSeenAt: { credential_baseline: NOW, hold: NOW + 315_000 },
    });
    await test.run();
    expect(test.step("expiry-turn")?.error).toContain(expected);
  });
  it("does not start the turn on a credential already at its expiry", async () => {
    auth.secondsLeft = 5;
    const test = setup();
    await test.run();
    expect(test.step("expiry-turn")?.status).toBe("failed");
    expect(test.step("expiry-turn")?.error).toContain("too close to expiry");
    expect(test.deps.runAgentTurn).not.toHaveBeenCalled();
    expect(test.deps.deleteAgentInstance).toHaveBeenCalledExactlyOnceWith("temporary-instance");
  });
  it("reports an unrecognised turn failure without exposing it", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockRejectedValue(new Error("private response"));
    await test.run();
    expect(test.step("expiry-turn")?.error).toBe("agent execution failed");
    expect(JSON.stringify(test.reports)).not.toContain("private response");
  });
  it("does not read a non-expiry execution failure as expiry", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockRejectedValue(
      new AgentTurnExecutionError({ credential_baseline: NOW, hold: NOW + 315_000 }, false),
    );
    await test.run();
    expect(test.step("expiry-turn")?.error).toBe("agent execution failed");
  });
  it("refuses a post-hold success reported before the hold ended", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockResolvedValue({
      answer: "success",
      sources: [],
      sessionId: null,
      statusSeenAt: {
        credential_baseline: NOW,
        hold: NOW + 315_000,
        protected_call_succeeded: NOW + 314_000,
        credential_renewed: NOW + 316_000,
      },
    });
    await test.run();
    expect(test.step("expiry-turn")?.status).toBe("failed");
    expect(test.step("expiry-turn")?.error).toContain("did not succeed after the hold");
  });
  it("treats an instance that is already gone as deleted", async () => {
    const test = setup();
    vi.mocked(test.deps.deleteAgentInstance).mockRejectedValue({ status: 404, data: {} });
    await test.run();
    expect(test.step("delete-agent")?.status).toBe("passed");
  });
  it("reports a cancelled creation as cancelled, not as a creation that failed", async () => {
    const controller = new AbortController();
    const test = setup();
    vi.mocked(test.deps.provisionAgentInstance).mockImplementation(async () => {
      controller.abort();
      throw new DOMException("cancelled", "AbortError");
    });
    await test.run(controller.signal);
    expect(test.step("provision-agent")?.error).toBe("cancelled");
    expect(test.deps.runAgentTurn).not.toHaveBeenCalled();
    expect(test.deps.deleteAgentInstance).not.toHaveBeenCalled();
  });
  it("does not classify admission rejection as in-turn expiry", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockRejectedValue(new AgentTurnRejectedError(401));
    await test.run();
    expect(test.step("expiry-turn")?.error).toContain("rejected before it started");
  });
  it.each(["credential_baseline", "hold", "protected_call_succeeded", "credential_renewed"])(
    "cannot pass without %s evidence",
    async (missing) => {
      const test = setup();
      const statuses: Record<string, number> = {
        credential_baseline: NOW,
        hold: NOW + 315_000,
        protected_call_succeeded: NOW + 316_000,
        credential_renewed: NOW + 316_000,
      };
      delete statuses[missing];
      vi.mocked(test.deps.runAgentTurn).mockResolvedValue({
        answer: "success",
        sources: [],
        sessionId: null,
        statusSeenAt: statuses,
      });
      await test.run();
      expect(test.step("expiry-turn")?.status).toBe("failed");
    },
  );
  it("does not accept a hold ending before expiry", async () => {
    const test = setup();
    vi.mocked(test.deps.runAgentTurn).mockResolvedValue({
      answer: "success",
      sources: [],
      sessionId: null,
      statusSeenAt: {
        credential_baseline: NOW,
        hold: NOW + 20_000,
        protected_call_succeeded: NOW + 21_000,
        credential_renewed: NOW + 21_000,
      },
    });
    await test.run();
    expect(test.step("expiry-turn")?.error).toContain("inconclusive");
  });
  it("does nothing when already cancelled", async () => {
    const controller = new AbortController();
    controller.abort();
    const test = setup();
    await test.run(controller.signal);
    expect(auth.fresh).not.toHaveBeenCalled();
    expect(test.deps.provisionAgentInstance).not.toHaveBeenCalled();
  });
  it("cleans up an instance created during cancellation and starts no turn", async () => {
    const controller = new AbortController();
    const test = setup();
    vi.mocked(test.deps.provisionAgentInstance).mockImplementation(async () => {
      controller.abort();
      return "temporary-instance";
    });
    await test.run(controller.signal);
    expect(test.deps.runAgentTurn).not.toHaveBeenCalled();
    expect(test.deps.deleteAgentInstance).toHaveBeenCalledExactlyOnceWith("temporary-instance");
  });
  it("reports cleanup failure without exposing upstream details", async () => {
    const test = setup();
    vi.mocked(test.deps.deleteAgentInstance).mockRejectedValue(new Error("private response"));
    await test.run();
    expect(test.step("delete-agent")?.status).toBe("failed");
    expect(JSON.stringify(test.reports)).not.toContain("private response");
  });
});
