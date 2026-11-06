// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { runtimeExecuteStreamPath } from "../../../core/utils/runtimeExecutionUrl";
import { parseSseFrames } from "../../../core/utils/runtimeStream";
import { parseWebReport, reportProbes } from "../scenarios/webResearchScenario";
import { FRESH } from "../deps/api";
import { verifyWebProbes } from "./webReport";
import { managerActor } from "../../imports/managerImportRun";
import {
  attachmentUploadScope,
  uploadAttachments,
  forgetAttachmentUpload,
} from "../../../components/pages/ManagedChatPage/attachmentUploads";
import { runStep, SkipStep } from "../step";
import { MAX_HOLD_SECONDS, type Scenario, type Reporter } from "../types";
import { captureSessionCredential, type CapturedCredential } from "../sessionCredential";
import { expiryWaitSeconds } from "../scenarios/credentialExpiryScenario";
import { authedFetch } from "../useAuthzProbeRun";
import type { WeaverChecks } from "./checks";
import {
  assert,
  cp,
  ingestKnowledgeFixture,
  provisionDisposableAgent,
  requireSpace,
  pause,
  registerTestConversation,
  deleteTestConversation,
} from "./resourceSupport";

export const TEST_ASSISTANT = "fred.github.test_assistant";
export interface RuntimeProbeOptions {
  mode: "retrieval" | "expiry" | "web" | "tabular";
  query?: string;
  marker?: string;
  hold_seconds?: number;
}
export interface RuntimeProbeReport {
  mode: RuntimeProbeOptions["mode"];
  tabular?: boolean;
  before?: boolean;
  after?: boolean;
  before_at?: number;
  after_at?: number;
  search_live?: boolean;
}

export async function runRuntimeTurn(
  checks: WeaverChecks,
  agentInstanceId: string,
  signal: AbortSignal,
  question: string | ((secondsLeft: number) => string),
  context: {
    sessionId?: string;
    runtimeContext?: Record<string, unknown>;
    admission?: { credential: CapturedCredential; expiresAt: number };
    onStatus?: (status: string) => void;
  } = {},
) {
  requireSpace(checks, signal);
  const prep = await checks
    .dispatch(
      cp.prepareExecution.initiate({
        spaceId: checks.spaceId,
        agentInstanceId,
        sessionId: context.sessionId,
      }),
    )
    .unwrap();
  const sessionId =
    context.sessionId ?? (await registerTestConversation(checks, agentInstanceId, prep.agent_configuration_revision));
  let executionFailed = false;
  try {
    signal.throwIfAborted();
    const captured =
      context.admission ??
      (() => {
        const session = captureSessionCredential();
        return session && { credential: session.credential, expiresAt: Date.now() + session.secondsLeft * 1000 };
      })();
    if (!captured) throw new SkipStep("A signed-in session with a known expiry is required.");
    const expiresAt = captured.expiresAt;
    const input = typeof question === "function" ? question((expiresAt - Date.now()) / 1000) : question;
    const response = await fetch(runtimeExecuteStreamPath(prep.execute_stream_url), {
      method: "POST",
      redirect: "error",
      signal,
      headers: { Authorization: `Bearer ${captured.credential}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_instance_id: agentInstanceId,
        input,
        session_id: sessionId,
        runtime_context: { ...context.runtimeContext, space_id: checks.spaceId },
      }),
    });
    if (!response.ok)
      throw Object.assign(new Error("The protected turn was not admitted."), { status: response.status });
    assert(response.body, "The protected turn did not open a stream.");
    let answer: string | null = null;
    for await (const event of parseSseFrames(response.body)) {
      signal.throwIfAborted();
      if (event.kind === "status" && typeof event.status === "string") context.onStatus?.(event.status);
      if (["error", "execution_error", "node_error"].includes(String(event.kind))) {
        throw new Error("Runtime diagnostic execution failed.");
      }
      if (event.kind === "final" && typeof event.content === "string") answer = event.content;
    }
    assert(answer !== null, "The runtime did not return a terminal answer.");
    return { answer, expiresAt };
  } catch (error) {
    executionFailed = true;
    throw error;
  } finally {
    if (!context.sessionId) {
      try {
        await deleteTestConversation(checks, sessionId);
      } catch (error) {
        if (executionFailed)
          throw new Error("Diagnostic execution failed and its disposable conversation could not be cleaned up.");
        throw error;
      }
    }
  }
}

export async function runRuntimeProbe(
  checks: WeaverChecks,
  agentInstanceId: string,
  signal: AbortSignal,
  options: RuntimeProbeOptions,
  context: Parameters<typeof runRuntimeTurn>[4] = {},
) {
  const turn = await runRuntimeTurn(
    checks,
    agentInstanceId,
    signal,
    (secondsLeft) => {
      const actual = { ...options };
      if (options.mode === "expiry") {
        const hold = expiryWaitSeconds(secondsLeft);
        if (secondsLeft < 10 || !hold || hold > MAX_HOLD_SECONDS)
          throw new SkipStep("Session lifetime changed outside the bounded expiry window; retry.");
        actual.hold_seconds = hold;
      }
      return `runtime probe ${JSON.stringify(actual)}`;
    },
    context,
  );
  assert(turn.answer.startsWith("RUNTIME-PROBE "), "The agent did not return the diagnostic contract.");
  let report: RuntimeProbeReport;
  try {
    report = JSON.parse(turn.answer.slice("RUNTIME-PROBE ".length)) as RuntimeProbeReport;
  } catch {
    throw new Error("The runtime diagnostic report is invalid.");
  }
  assert(report && report.mode === options.mode, "The runtime diagnostic mode does not match.");
  if (options.mode === "web" && (report as RuntimeProbeReport & { unavailable?: boolean }).unavailable)
    throw new SkipStep("Web research is unavailable on this deployment.");
  return { ...turn, report };
}

export const web: Scenario<WeaverChecks> = async (checks, report, signal) => {
  let instanceId: string | undefined;
  try {
    const agent = await runStep(report, "web-agent", "Create a deterministic diagnostic agent", async () => {
      const value = await provisionDisposableAgent(checks, signal, "web", TEST_ASSISTANT, ["web_research"]);
      instanceId = value.agent_instance_id;
      return { value };
    });
    if (!agent) return;
    await runStep(report, "web-probes", "Validate the web diagnostic report and its reported outcomes", async () => {
      const result = await runRuntimeProbe(checks, agent.agent_instance_id, signal, { mode: "web" });
      const parsed = parseWebReport(`WEB-SELF-TEST ${JSON.stringify(result.report)}`);
      assert(parsed?.enabled && parsed.ready, "The web diagnostic did not return a ready report.");
      verifyWebProbes(parsed.probes);
      reportProbes(report, parsed.probes);
      assert(
        !parsed.probes.some((probe) => probe.verdict === "failed"),
        "The web diagnostic contains failed probes; inspect their results below.",
      );
      return {
        value: true,
        detail:
          result.report.search_live === true
            ? "Fixed battery completed using the configured network search provider."
            : "Fixed battery completed using fixture search; remote probes are reported separately.",
      };
    });
  } finally {
    if (instanceId)
      await runStep(report, "web-cleanup", "Delete the diagnostic agent", async () => {
        await deleteDiagnosticAgent(checks, instanceId!);
        return { value: true };
      });
  }
};

export const expiry: Scenario<WeaverChecks> = async (checks, report, signal) => {
  let instanceId: string | undefined;
  let fixture: Awaited<ReturnType<typeof ingestKnowledgeFixture>> | null = null;
  try {
    const prepared = await runStep(report, "expiry-prepare", "Prepare the diagnostic agent and session", async () => {
      requireSpace(checks, signal);
      const agent = await provisionDisposableAgent(checks, signal, "expiry", TEST_ASSISTANT, ["document_access"]);
      instanceId = agent.agent_instance_id;
      return { value: agent };
    });
    if (!prepared) return;
    fixture = await ingestKnowledgeFixture(checks, signal, undefined, {
      report,
      id: "expiry-document",
      title: "Upload and index a disposable expiry document",
    });
    if (!fixture) return;
    const session = await runStep(report, "session-token", "Use the current SSO session", async () => {
      let fresh = false;
      try {
        fresh = await KeyCloakService.ensureFreshToken(30);
      } catch {
        throw new Error("The SSO session could not be refreshed; sign in again before retrying.");
      }
      signal.throwIfAborted();
      const captured = captureSessionCredential();
      const hold = captured && expiryWaitSeconds(captured.secondsLeft);
      assert(fresh && captured && hold, "A valid SSO session with a known expiry is required.");
      if (hold > MAX_HOLD_SECONDS)
        throw new SkipStep(
          "The session exceeds the 15-minute limit; retry closer to expiry without changing realm settings.",
        );
      const admission = { credential: captured.credential, expiresAt: Date.now() + captured.secondsLeft * 1000 };
      const before = await authedFetch("/control-plane/v1/me", admission.credential);
      assert(before.status === 200, "The captured credential was not accepted before the turn.");
      return {
        value: admission,
        detail: `The agent will wait approximately ${hold} s before repeating protected access; browser refresh stays enabled.`,
      };
    });
    if (!session) return;
    const published = fixture;
    const baseline = { id: "baseline-access", title: "Access before your session expires" };
    const after = { id: "expiry-turn", title: "Access after your session expires" };
    const started = performance.now();
    let baselineSeen = false;
    report({ ...baseline, status: "running" });
    try {
      await runStep(report, after.id, after.title, async () => {
        const observer = new AbortController();
        const expiredCredential = (async () => {
          await pause(AbortSignal.any([signal, observer.signal]), Math.max(0, session.expiresAt + 5000 - Date.now()));
          const response = await authedFetch("/control-plane/v1/me", session.credential);
          return { status: response.status, observedAt: Date.now() };
        })().catch(() => null);
        try {
          const result = await runRuntimeProbe(
            checks,
            prepared.agent_instance_id,
            signal,
            { mode: "expiry", query: published.text, marker: published.text },
            {
              admission: session,
              runtimeContext: { selected_document_uids: [published.documentId], search_rag_scope: "corpus_only" },
              onStatus: (status) => {
                if (status === "runtime_probe_baseline" && !baselineSeen) {
                  baselineSeen = true;
                  report({
                    ...baseline,
                    status: "passed",
                    detail: "Protected retrieval succeeded before the wait.",
                    durationMs: Math.round(performance.now() - started),
                  });
                  report({
                    ...after,
                    status: "running",
                    detail: "Waiting beyond the captured session's expiry before repeating protected retrieval.",
                  });
                }
              },
            },
          );
          const validBaseline =
            baselineSeen &&
            result.report.before === true &&
            typeof result.report.before_at === "number" &&
            Number.isFinite(result.report.before_at) &&
            result.report.before_at * 1000 < session.expiresAt;
          if (!validBaseline) {
            baselineSeen = true;
            report({ ...baseline, status: "failed", error: "Protected access before expiry was not demonstrated." });
            throw new Error("Inconclusive: no valid before-expiry baseline.");
          }
          assert(result.report.after === true, "Protected retrieval after the wait did not succeed.");
          assert(
            typeof result.report.after_at === "number" &&
              Number.isFinite(result.report.after_at) &&
              result.report.after_at * 1000 > session.expiresAt + 5000 &&
              Date.now() > session.expiresAt + 5000,
            "Inconclusive: the second protected search did not follow the captured credential's expiry.",
          );
          signal.throwIfAborted();
          const expired = await expiredCredential;
          assert(
            expired?.status === 401 && expired.observedAt < result.report.after_at * 1000,
            "Inconclusive: the original credential was not observed rejected with HTTP 401 before the second search. Keep the page active and retry; elapsed time alone does not prove expiry.",
          );
          return {
            value: true,
            detail:
              "Protected retrieval succeeded before and after expiry in one admitted turn. The original credential was rejected with HTTP 401 before the second search. Downstream token renewal or absence is not exposed by this API.",
          };
        } finally {
          observer.abort();
          await expiredCredential;
        }
      });
    } finally {
      if (!baselineSeen)
        report({
          ...baseline,
          status: "skipped",
          detail: "The turn did not reach the first protected call.",
          durationMs: Math.round(performance.now() - started),
        });
    }
  } finally {
    await runStep(report, "expiry-cleanup", "Delete diagnostic resources", async () => {
      try {
        if (fixture) await fixture.cleanup();
      } finally {
        if (instanceId) await deleteDiagnosticAgent(checks, instanceId!);
      }
      return { value: true };
    });
  }
};

export async function checkAgentRuntime(
  checks: WeaverChecks,
  report: Reporter,
  signal: AbortSignal,
  agent: ManagedAgentInstanceSummary,
) {
  const id = agent.agent_instance_id;
  await runStep(report, "runtime-echo", "Verify agent execution without a model", async () => {
    const value = await runRuntimeTurn(checks, id, signal, "echo diagnostic");
    assert(value.answer.includes("Echo: echo diagnostic"), "The deterministic echo was not returned.");
    return { value: true };
  });
}

export async function checkKnowledgeRuntime(
  checks: WeaverChecks,
  report: Reporter,
  signal: AbortSignal,
  agent: ManagedAgentInstanceSummary,
  fixture: { documentId: string; text: string },
) {
  const id = agent.agent_instance_id;
  await runStep(report, "runtime-retrieval", "Retrieve the fixture through trusted runtime scope", async () => {
    const value = await runRuntimeProbe(
      checks,
      id,
      signal,
      {
        mode: "retrieval",
        query: fixture.text,
        marker: fixture.text,
      },
      {
        runtimeContext: {
          selected_document_uids: [fixture.documentId],
          search_rag_scope: "corpus_only",
        },
      },
    );
    assert(value.report.before === true, "The authorized runtime retrieval did not find the fixture.");
    return { value: true };
  });
}

export async function checkConversationRuntime(
  checks: WeaverChecks,
  report: Reporter,
  signal: AbortSignal,
  agent: ManagedAgentInstanceSummary,
  sessions: string[],
) {
  const id = agent.agent_instance_id;
  assert(sessions.length === 2, "Two diagnostic conversations are required.");
  await runStep(
    report,
    "runtime-attachment-isolation",
    "Keep attachment retrieval inside its owning conversation",
    async () => {
      const marker = `violet lantern ${crypto.randomUUID()}`;
      const scope = attachmentUploadScope(managerActor(), checks.spaceId, sessions[0]);
      await uploadAttachments(checks.dispatch as Parameters<typeof uploadAttachments>[0], scope, [
        new File([marker], "attachment.txt", { type: "text/plain" }),
      ]);
      const upload = scope.entries[scope.entries.length - 1];
      assert(upload?.receipt?.status === "stored", "Attachment upload did not complete.");
      const bounded = AbortSignal.any([signal, AbortSignal.timeout(120_000)]);
      while (true) {
        bounded.throwIfAborted();
        const items = await checks
          .dispatch(cp.listAttachments.initiate({ spaceId: checks.spaceId, sessionId: sessions[0] }, FRESH))
          .unwrap();
        const item = items.find((entry) => entry.document_id === upload.receipt?.document_id);
        assert(item?.processing?.status !== "failed", "Attachment ingestion failed.");
        if (item?.ready) break;
        await pause(bounded);
      }
      forgetAttachmentUpload(scope, upload.key);
      const options: RuntimeProbeOptions = { mode: "retrieval", query: marker, marker };
      const own = await runRuntimeProbe(checks, id, signal, options, {
        sessionId: sessions[0],
        runtimeContext: { search_rag_scope: "hybrid" },
      });
      assert(own.report.before === true, "The owning conversation could not retrieve its attachment.");
      try {
        const other = await runRuntimeProbe(checks, id, signal, options, {
          sessionId: sessions[1],
          runtimeContext: {
            search_rag_scope: "hybrid",
            selected_document_uids: [upload.receipt.document_id],
          },
        });
        assert(other.report.before === false, "Another conversation retrieved the private attachment.");
      } catch (error) {
        if ((error as { status?: unknown })?.status !== 403) throw error;
      }
      return {
        value: true,
        detail: "Attachment found in its owning conversation and absent from a different conversation.",
      };
    },
  );
}

async function deleteDiagnosticAgent(checks: WeaverChecks, agentInstanceId: string) {
  const args = { spaceId: checks.spaceId, agentInstanceId };
  await checks.dispatch(cp.deleteAgentInstance.initiate(args)).unwrap();
  try {
    await checks.dispatch(cp.getAgentInstance.initiate(args, FRESH)).unwrap();
  } catch (error) {
    if ((error as { status?: unknown })?.status === 404) return;
    throw error;
  }
  throw new Error("The diagnostic agent remains readable after deletion.");
}
