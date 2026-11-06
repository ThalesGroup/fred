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

import { runStep, SkipStep } from "../step";
import type { PipelineDeps, Scenario } from "../types";
import { PROMPT_PROBE, SELF_TEST_AGENT_ID } from "./corpus";
import { INDEX_WAIT_MS, type SearchHit } from "./knowledgeScenario";
import { cleanup, newRunScope } from "./runScope";

const POLL_MS = 1_500;

export interface ConversationsDeps extends PipelineDeps {
  listSessions: () => Promise<Array<{ id: string; title: string | null }>>;
  readSession: (id: string) => Promise<{ title: string | null; agentId: string | null }>;
  renameSession: (id: string, title: string) => Promise<void>;
  /** Ingests the file into the session's own scope and records it as an attachment. */
  attach: (sessionId: string, file: File) => Promise<string>;
  listAttachments: (sessionId: string) => Promise<string[]>;
  deleteAttachment: (sessionId: string, attachmentId: string) => Promise<void>;
  searchSession: (sessionId: string, question: string) => Promise<SearchHit[]>;
  bulkDelete: (sessionIds: string[]) => Promise<{ deleted: string[]; failed: string[] }>;
  inactiveCount: () => Promise<number>;
  sleep: (ms: number) => Promise<void>;
}

/** Conversations family, in the personal space. */
export const conversationsScenario: Scenario<ConversationsDeps> = async (deps, report, signal) => {
  const scope = newRunScope();
  const marker = scope.name("Selftestattachment");
  let agentId: string | null = null;
  const sessions: string[] = [];
  let attachmentId: string | null = null;
  const deleted = new Set<string>();

  const until = async (check: () => Promise<boolean>) => {
    for (let waited = 0; ; waited += POLL_MS) {
      signal.throwIfAborted();
      if (await check()) return true;
      if (waited >= INDEX_WAIT_MS) return false;
      await deps.sleep(POLL_MS);
    }
  };
  const carries = (hits: SearchHit[]) => hits.some((h) => h.content.includes(marker));

  try {
    agentId = await runStep(report, "provision-agent", "Provision the self-test agent", async () => {
      const id = await deps.provisionAgentInstance(SELF_TEST_AGENT_ID, undefined, signal, scope.token);
      if (!id) throw new SkipStep(`template '${SELF_TEST_AGENT_ID}' is not available on this deployment`);
      return { value: id, detail: id };
    });
    const first = await runStep(report, "create-session", "Create two conversations", async () => {
      if (!agentId) throw new SkipStep("agent instance missing");
      for (let i = 0; i < 2; i++) sessions.push(await deps.createSession(agentId, scope.token));
      return { value: sessions[0], detail: sessions.join(", ") };
    });
    await runStep(report, "turn-in-session", "A turn runs inside the conversation", async () => {
      if (!agentId || !first) throw new SkipStep("agent or conversation missing");
      const turn = await deps.runAgentTurn({
        agentInstanceId: agentId,
        question: PROMPT_PROBE,
        libraryIds: [],
        sessionId: first,
        signal,
      });
      if (turn.sessionId && turn.sessionId !== first) throw new Error(`the turn ran in ${turn.sessionId}`);
      const stored = await deps.readSession(first);
      if (stored.agentId !== agentId) throw new Error("the conversation is bound to another agent");
      return { value: undefined, detail: "answered in the conversation" };
    });
    await runStep(report, "session-listed", "Both conversations are listed", async () => {
      if (sessions.length === 0) throw new SkipStep("no conversation was created");
      const listed = new Set((await deps.listSessions()).map((s) => s.id));
      const missing = sessions.filter((id) => !listed.has(id));
      if (missing.length) throw new Error(`not listed: ${missing.join(", ")}`);
      return { value: undefined, detail: `${sessions.length} listed` };
    });
    await runStep(report, "rename-session", "A renamed conversation keeps its new title", async () => {
      if (!first) throw new SkipStep("conversation missing");
      const title = scope.name("Self-test conversation");
      await deps.renameSession(first, title);
      const stored = await deps.readSession(first);
      if (stored.title !== title) throw new Error(`the title is '${stored.title}'`);
      return { value: undefined, detail: title };
    });

    await runStep(report, "attach-file", "A file attached to the conversation is recorded", async () => {
      if (!first) throw new SkipStep("conversation missing");
      const file = new File([`Self-test attachment. Marker: ${marker}.\n`], `${scope.name("fred-selftest")}.txt`, {
        type: "text/plain",
      });
      const id = await deps.attach(first, file);
      attachmentId = id;
      if (!(await deps.listAttachments(first)).includes(id)) throw new Error("the attachment is not listed");
      return { value: id, detail: id };
    });
    await runStep(report, "attachment-search", "The attachment is retrievable inside its conversation", async () => {
      if (!first || !attachmentId) throw new SkipStep("attachment missing");
      if (!(await until(async () => carries(await deps.searchSession(first, marker))))) {
        throw new Error(`no chunk carries '${marker}' after ${INDEX_WAIT_MS / 1000} s`);
      }
      return { value: undefined, detail: "marker found" };
    });
    await runStep(report, "attachment-isolation", "Another conversation never sees that attachment", async () => {
      if (!attachmentId || sessions.length < 2) throw new SkipStep("attachment or second conversation missing");
      if (carries(await deps.searchSession(sessions[1], marker))) {
        throw new Error("the attachment leaked into another conversation of the same person");
      }
      return { value: undefined, detail: "not returned" };
    });
    await runStep(report, "delete-attachment", "A deleted attachment is no longer listed or retrievable", async () => {
      if (!first || !attachmentId) throw new SkipStep("attachment missing");
      await deps.deleteAttachment(first, attachmentId);
      const deleted = attachmentId;
      attachmentId = null;
      if ((await deps.listAttachments(first)).includes(deleted)) throw new Error("the attachment is still listed");
      if (!(await until(async () => !carries(await deps.searchSession(first, marker))))) {
        throw new Error("the deleted attachment is still retrievable");
      }
      return { value: undefined, detail: deleted };
    });
    await runStep(report, "inactive-sessions", "Your inactive conversations can be listed", async () => ({
      value: undefined,
      detail: `${await deps.inactiveCount()} inactive conversation(s)`,
    }));
    await runStep(report, "bulk-delete", "Bulk deletion removes both conversations", async () => {
      if (sessions.length === 0) throw new SkipStep("no conversation");
      const result = await deps.bulkDelete(sessions);
      const missed = sessions.filter((id) => !result.deleted.includes(id));
      if (missed.length) throw new Error(`not deleted: ${missed.join(", ")}`);
      for (const id of result.deleted) {
        await deps.verifyDeleted("session", id);
        deleted.add(id);
      }
      return { value: undefined, detail: `${result.deleted.length} deleted and confirmed absent` };
    });
  } finally {
    const first = sessions[0] ?? null;
    if (first && attachmentId) {
      const id = attachmentId;
      await cleanup(
        report,
        "cleanup-attachment",
        "Delete the attachment",
        id,
        (a) => deps.deleteAttachment(first, a),
        async (a) => {
          if ((await deps.listAttachments(first)).includes(a))
            throw new Error(`attachment ${a} is still listed after deletion`);
        },
      );
    }
    for (const [i, id] of sessions.entries()) {
      if (!deleted.has(id))
        await cleanup(report, `delete-session-${i}`, "Delete a test conversation", id, deps.deleteSession, (id) =>
          deps.verifyDeleted("session", id),
        );
    }
    await cleanup(report, "delete-agent", "Delete the self-test agent", agentId, deps.deleteAgentInstance, (id) =>
      deps.verifyDeleted("agent", id),
    );
  }
};
