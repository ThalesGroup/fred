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

import { KeyCloakService } from "../../../../security/KeycloakService";
import { captureSessionCredential } from "../sessionCredential";
import { runStep, SkipStep } from "../step";
import {
  AgentTurnExecutionError,
  AgentTurnRejectedError,
  isCredentialExpiryFailure,
  isProtectedCallRefusal,
  isProtectedCallUnreachable,
} from "../actions";
import { MAX_HOLD_MINUTES, MAX_HOLD_SECONDS, type AgentTurnResult, type Scenario } from "../types";
import { SELF_TEST_AGENT_ID } from "./corpus";

const MARGIN_SECONDS = 15;
const TOLERANCE_MS = 5_000;
const BASELINE_STEP = { id: "baseline-access", title: "Check authenticated access before expiry" };
const EXPIRY_STEP = { id: "expiry-turn", title: "Check authenticated access after expiry" };
const EXPIRY_REFUSAL = "the credential expired during the protected call and the turn did not recover";
const CALL_REFUSED = "the protected call after the hold was refused, but not because the credential expired";
const CALL_UNREACHABLE = "the protected call after the hold did not reach the service";

export interface CredentialExpiryInput {
  now?: () => number;
}

/**
 * How long the run will wait, from what the session has left — `null` when that
 * is unknown or already spent. Shared with the page so the notice it asks the
 * admin to accept quotes the same wait the run will take.
 */
export function expiryWaitSeconds(secondsLeft: number | null): number | null {
  if (secondsLeft === null || !Number.isFinite(secondsLeft) || secondsLeft <= 0) return null;
  return Math.ceil(secondsLeft) + MARGIN_SECONDS;
}

/** Keep the captured credential private to this run while normal SSO refresh continues. */
export function credentialExpiryScenario(input: CredentialExpiryInput = {}): Scenario {
  const now = input.now ?? Date.now;
  return async (deps, report, signal) => {
    let agentInstanceId: string | null = null;
    try {
      if (signal.aborted) return;
      const session = await runStep(report, "session-token", "Use the current SSO session", async () => {
        if (!KeyCloakService.GetKeycloakRealmConfig()) throw new SkipStep("a secure SSO session is required");
        let fresh: boolean;
        try {
          fresh = await KeyCloakService.ensureFreshToken(30);
        } catch {
          throw new Error("the SSO session could not be refreshed; sign in again before retrying");
        }
        signal.throwIfAborted();
        const captured = captureSessionCredential();
        const holdSeconds = captured && expiryWaitSeconds(captured.secondsLeft);
        if (!fresh || !captured || !holdSeconds) {
          throw new Error("a valid SSO token with a known expiry is required; sign in again before retrying");
        }
        if (holdSeconds > MAX_HOLD_SECONDS) {
          throw new SkipStep(
            `the token exceeds the ${MAX_HOLD_MINUTES}-minute limit; retry closer to its expiry without changing the realm settings`,
          );
        }
        return {
          value: {
            bearer: captured.credential,
            expiresAt: now() + captured.secondsLeft * 1000,
            holdSeconds,
          },
          detail: `the agent will wait ${holdSeconds} s before repeating the protected call; browser refresh stays enabled`,
        };
      });
      if (!session || signal.aborted) return;
      agentInstanceId = await runStep(
        report,
        "provision-agent",
        "Create a temporary graph agent for this run",
        async () => {
          let id: string | null;
          try {
            id = await deps.provisionAgentInstance(
              SELF_TEST_AGENT_ID,
              {
                "settings.hold_seconds": session.holdSeconds,
                "settings.check_access": true,
              },
              signal,
            );
          } catch (err) {
            // A cancelled run must read as cancelled, never as a creation that failed.
            if (signal.aborted) throw err;
            throw new Error("the diagnostic agent could not be created");
          }
          if (!id)
            throw new SkipStep(
              `template '${SELF_TEST_AGENT_ID}' not found — restart the fred-agents pod with the new code`,
            );
          // Named so a run interrupted before teardown can be found and removed.
          return { value: id, detail: "deterministic stages, no model calls" };
        },
      );
      if (!agentInstanceId || signal.aborted) return;

      // Announced before the turn's own step so the two read in the order they
      // are proven; every path that ends without proving it settles it below.
      let baselineSettled = false;
      // Timed here rather than by the step runner, which only times the steps it
      // wraps; this one is settled from inside the turn.
      const baselineStart = performance.now();
      const baselineMs = () => Math.round(performance.now() - baselineStart);
      report({ ...BASELINE_STEP, status: "running" });

      await runStep(report, EXPIRY_STEP.id, EXPIRY_STEP.title, async () => {
        if (session.expiresAt - now() < 10_000) {
          throw new Error("inconclusive: the captured token is too close to expiry to start the turn; retry the test");
        }
        let turn: AgentTurnResult | undefined;
        let failure: AgentTurnExecutionError | undefined;
        try {
          turn = await deps.runAgentTurn({
            agentInstanceId: agentInstanceId!,
            question: "Check authenticated metadata access.",
            libraryIds: [],
            bearer: session.bearer,
            signal,
            onProgress: (detail) => {
              if (!signal.aborted) report({ ...EXPIRY_STEP, status: "running", detail });
            },
            onStatus: (status) => {
              if (status === "credential_baseline" && !signal.aborted) {
                baselineSettled = true;
                report({
                  ...BASELINE_STEP,
                  status: "passed",
                  detail: "the credential was accepted before the wait began",
                  durationMs: baselineMs(),
                });
              }
            },
          });
        } catch (err) {
          signal.throwIfAborted();
          if (err instanceof AgentTurnRejectedError) {
            throw new Error(
              "the turn was rejected before it started; this does not demonstrate expiry during execution",
            );
          }
          if (!(err instanceof AgentTurnExecutionError)) throw new Error("agent execution failed");
          failure = err;
        }
        const statuses = (failure ?? turn)?.statusSeenAt;
        if (!statuses?.credential_baseline) {
          const missing = "the authenticated call before the wait did not succeed; check the agent build and access";
          baselineSettled = true;
          report({ ...BASELINE_STEP, status: "failed", error: missing, durationMs: baselineMs() });
          throw new Error(`inconclusive: ${missing}`);
        }
        const holdSeenAt = statuses.hold;
        if (!holdSeenAt || holdSeenAt - session.expiresAt < TOLERANCE_MS) {
          throw new Error("inconclusive: the hold was not observed beyond the captured token's expiry");
        }
        if (failure) throw new Error(failure.credentialExpired ? EXPIRY_REFUSAL : "agent execution failed");
        if (!turn) throw new Error("agent execution failed");
        if (isCredentialExpiryFailure(turn.answer)) throw new Error(EXPIRY_REFUSAL);
        if (isProtectedCallRefusal(turn.answer)) throw new Error(CALL_REFUSED);
        if (isProtectedCallUnreachable(turn.answer)) throw new Error(CALL_UNREACHABLE);
        if (!statuses.protected_call_succeeded || statuses.protected_call_succeeded < holdSeenAt) {
          throw new Error("the protected call did not succeed after the hold");
        }
        if (!statuses.credential_renewed) {
          throw new Error(
            "inconclusive: the protected call succeeded, but renewal was not observed; the original token may still be accepted",
          );
        }
        return {
          value: true,
          detail: "authenticated metadata access succeeded after expiry and credential renewal was observed",
        };
      });

      if (!baselineSettled) {
        report({
          ...BASELINE_STEP,
          status: "skipped",
          detail: "the turn did not reach the first authenticated call",
          durationMs: baselineMs(),
        });
      }
    } finally {
      if (agentInstanceId) {
        await runStep(report, "delete-agent", "Delete this run's diagnostic agent", async () => {
          try {
            await deps.deleteAgentInstance(agentInstanceId);
          } catch (err) {
            if (!(typeof err === "object" && err !== null && (err as { status?: unknown }).status === 404)) {
              throw new Error(
                "the diagnostic agent could not be deleted; remove the temporary instance from your personal agents",
              );
            }
          }
          return { value: true };
        });
      }
    }
  };
}
