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
// Test-only, in-memory stand-in for the platform the families drive. Its agent
// behaves like the deterministic self-test agent: it echoes retrieved text and
// the prompts it received.
import type { PipelineDeps, Reporter, StepReport } from "../types";
import type { AgentsDeps } from "./agentsScenario";
import type { ConversationsDeps } from "./conversationsScenario";
import type { KnowledgeDeps } from "./knowledgeScenario";
import type { PromptsDeps } from "./promptsScenario";
import { PROBE, PROMPT_PROBE, SELF_TEST_AGENT_ID } from "./corpus";
import JSZip from "jszip";

export interface FakeDocument {
  uid: string;
  name: string;
  text: string;
  libraries: Set<string>;
  retrievable: boolean;
}

/** Reads the first sheet back as CSV text, so the fake's SQL path treats a spreadsheet like a CSV. */
async function sheetAsCsv(file: File): Promise<string> {
  const zip = await JSZip.loadAsync(await file.arrayBuffer());
  const sheet = (await zip.file("xl/worksheets/sheet1.xml")?.async("string")) ?? "";
  const rows = [...sheet.matchAll(/<row[^>]*>(.*?)<\/row>/g)].map((row) =>
    [...row[1].matchAll(/<(?:v|t)>([^<]*)<\/(?:v|t)>/g)].map((cell) => cell[1]).join(","),
  );
  return `${rows.join("\n")}\n`;
}

export class FakePlatform {
  libraries = new Map<string, string>();
  documents: FakeDocument[] = [];
  agents = new Map<string, { template: string; name: string; system: string; enabled: boolean }>();
  prompts = new Map<
    string,
    { name: string; text: string; categoryId?: string; command?: string; favorite?: boolean }
  >();
  categories = new Map<string, string>();
  attachments = new Map<string, { sessionId: string; text: string }>();
  sessions = new Map<string, { agent: string; title: string; prompts: string[] }>();
  templates = new Set([SELF_TEST_AGENT_ID]);
  failures = new Set<string>();
  private next = 0;

  id(prefix: string): string {
    this.next += 1;
    return `${prefix}-${this.next}`;
  }

  fail(name: string): void {
    if (this.failures.has(name)) throw new Error(`${name} failed`);
  }

  answer(agentId: string, question: string, libraryIds: string[], sessionId?: string | null) {
    const agent = this.agents.get(agentId);
    if (!agent || !agent.enabled) throw Object.assign(new Error("agent unavailable"), { status: 409 });
    if (question === PROMPT_PROBE) {
      const session = sessionId ? this.sessions.get(sessionId) : undefined;
      const context = (session?.prompts ?? []).map((id) => this.prompts.get(id)?.text ?? "").join("\n");
      return { answer: `system_prompt: ${agent.system}\ncontext_prompt: ${context}`, sources: [] };
    }
    if (question === PROBE) {
      const hits = this.search(libraryIds);
      return { answer: hits.map((d) => d.text).join("\n"), sources: hits.map((d) => d.uid) };
    }
    return { answer: "", sources: [] };
  }

  search(libraryIds: string[]): FakeDocument[] {
    return this.documents.filter((d) => d.retrievable && libraryIds.some((l) => d.libraries.has(l)));
  }

  /** Documents whose chunks the index still returns after a delete (simulates residue). */
  residue: FakeDocument[] = [];
  /** Inconsistencies the store audit reports, by document. */
  auditFindings: Array<{ uid: string; issues: string[] }> = [];

  agentsDeps(): AgentsDeps {
    const base = this.deps();
    return {
      ...base,
      updateAgent: async (id, { system, enabled }) => {
        const agent = this.agents.get(id);
        if (!agent) throw Object.assign(new Error("not found"), { status: 404 });
        if (system !== undefined) agent.system = system;
        if (enabled !== undefined) agent.enabled = enabled;
      },
      listAgents: async () => [...this.agents].map(([id, a]) => ({ id, name: a.name })),
      effectiveModel: async () => ({ name: "chat-model", usable: true }),
      copyTargets: async () => [{ teamId: base.teamId, templateEnabled: true }],
      duplicate: async (id, name) => {
        const source = this.agents.get(id);
        if (!source) throw Object.assign(new Error("not found"), { status: 404 });
        const taken = new Set([...this.agents.values()].map((a) => a.name));
        if (name && taken.has(name)) return { agentId: null, name: null, errorCode: "agent_name_conflict" };
        let free = name ?? `${source.name} (copy)`;
        for (let n = 2; !name && taken.has(free); n++) free = `${source.name} (copy ${n})`;
        const copyId = this.id("agent");
        this.agents.set(copyId, { ...source, name: free });
        return { agentId: copyId, name: free, errorCode: null };
      },
    };
  }

  promptsDeps(): PromptsDeps {
    const missing = () => Object.assign(new Error("not found"), { status: 404 });
    return {
      ...this.deps(),
      createPrompt: async (args) => {
        const id = this.id("prompt");
        this.prompts.set(id, { ...args });
        return id;
      },
      updatePrompt: async (id, args) => {
        const prompt = this.prompts.get(id);
        if (!prompt) throw missing();
        this.prompts.set(id, { ...prompt, ...args });
      },
      readPrompt: async (id) => {
        const prompt = this.prompts.get(id);
        if (!prompt) throw missing();
        return { text: prompt.text, categoryId: prompt.categoryId ?? null, favorite: prompt.favorite ?? false };
      },
      setFavorite: async (id, favorite) => {
        const prompt = this.prompts.get(id);
        if (!prompt) throw missing();
        prompt.favorite = favorite;
      },
      listFavorites: async () => [...this.prompts].filter(([, p]) => p.favorite).map(([id]) => id),
      listCommands: async () =>
        [...this.prompts].filter(([, p]) => p.command).map(([id, p]) => ({ promptId: id, command: p.command! })),
      createCategory: async (name) => {
        const id = this.id("category");
        this.categories.set(id, name);
        return id;
      },
      renameCategory: async (id, name) => {
        if (!this.categories.has(id)) throw missing();
        this.categories.set(id, name);
      },
      listCategories: async () => [...this.categories].map(([id, name]) => ({ id, name })),
      deleteCategory: async (id) => {
        this.categories.delete(id);
      },
      marketplaceCount: async () => 0,
    };
  }

  conversationsDeps(): ConversationsDeps {
    const missing = () => Object.assign(new Error("not found"), { status: 404 });
    const base = this.deps();
    return {
      ...base,
      deleteSession: async (id) => {
        this.sessions.delete(id);
        for (const [a, v] of this.attachments) if (v.sessionId === id) this.attachments.delete(a);
      },
      listSessions: async () => [...this.sessions].map(([id, s]) => ({ id, title: s.title })),
      readSession: async (id) => {
        const session = this.sessions.get(id);
        if (!session) throw missing();
        return { title: session.title, agentId: session.agent };
      },
      renameSession: async (id, title) => {
        const session = this.sessions.get(id);
        if (!session) throw missing();
        session.title = title;
      },
      attach: async (sessionId, file) => {
        const id = this.id("attachment");
        this.attachments.set(id, { sessionId, text: await file.text() });
        return id;
      },
      listAttachments: async (sessionId) =>
        [...this.attachments].filter(([, a]) => a.sessionId === sessionId).map(([id]) => id),
      deleteAttachment: async (_sessionId, id) => {
        this.attachments.delete(id);
      },
      searchSession: async (sessionId) =>
        [...this.attachments]
          .filter(([, a]) => a.sessionId === sessionId)
          .map(([uid, a]) => ({ uid, content: a.text })),
      bulkDelete: async (ids) => {
        const deleted = ids.filter((id) => this.sessions.delete(id));
        return { deleted, failed: ids.filter((id) => !deleted.includes(id)) };
      },
      inactiveCount: async () => 0,
      sleep: async () => {},
    };
  }

  knowledgeDeps(): KnowledgeDeps {
    return {
      ...this.deps(),
      documentsIn: async (libraryId) =>
        this.documents.filter((d) => d.libraries.has(libraryId)).map((d) => ({ uid: d.uid, name: d.name })),
      search: async ({ libraryIds, documentUids }) => {
        this.fail("search");
        const pool = [...this.documents, ...this.residue].filter((d) => d.retrievable);
        const hits = pool.filter(
          (d) =>
            (!libraryIds || libraryIds.some((l) => d.libraries.has(l))) &&
            (!documentUids || documentUids.includes(d.uid)),
        );
        return hits.map((d) => ({ uid: d.uid, content: d.text }));
      },
      linkDocument: async (libraryId, uid) => {
        this.documents.find((d) => d.uid === uid)?.libraries.add(libraryId);
      },
      unlinkDocument: async (libraryId, uid) => {
        this.fail("unlink");
        this.documents.find((d) => d.uid === uid)?.libraries.delete(libraryId);
      },
      setRetrievable: async (uid, retrievable) => {
        const doc = this.documents.find((d) => d.uid === uid);
        if (doc) doc.retrievable = retrievable;
      },
      documentTree: async (libraryId) =>
        this.documents
          .filter((d) => d.libraries.has(libraryId))
          .map((d) => d.name)
          .join("\n"),
      tabularRows: async (_libraryId, uid, sql) => {
        const doc = this.documents.find((d) => d.uid === uid);
        if (!doc || !sql("alias").includes("alias")) return [];
        const [header, ...lines] = doc.text.trim().split("\n");
        const columns = header.split(",");
        return lines
          .map((line) => Object.fromEntries(line.split(",").map((v, i) => [columns[i], i === 0 ? Number(v) : v])))
          .filter((row) => row.code === 1)
          .map((row) => ({ label: row.label }));
      },
      audit: async () => [
        ...this.auditFindings,
        ...this.residue.map((d) => ({ uid: d.uid, issues: ["orphan_vectors"] })),
      ],
      sleep: async () => {},
    };
  }

  deps(): PipelineDeps {
    return {
      teamId: "personal-admin",
      createLibrary: async (name) => {
        this.fail("createLibrary");
        const id = this.id("lib");
        this.libraries.set(id, name);
        return id;
      },
      deleteLibrary: async (id) => {
        this.libraries.delete(id);
        this.documents = this.documents.filter((d) => {
          d.libraries.delete(id);
          return d.libraries.size > 0;
        });
      },
      listLibraries: async () => [...this.libraries].map(([id, name]) => ({ id, name })),
      verifyDeleted: async (kind, id) => {
        const resources = {
          library: this.libraries,
          agent: this.agents,
          prompt: this.prompts,
          session: this.sessions,
        };
        if (resources[kind].has(id)) throw new Error(`${kind} ${id} is still listed after deletion`);
      },
      ingestDocument: async (libraryId, file) => {
        this.fail(`ingest:${file.name}`);
        this.documents.push({
          uid: this.id("doc"),
          name: file.name,
          text: file.name.endsWith(".xlsx") ? await sheetAsCsv(file) : await file.text(),
          libraries: new Set([libraryId]),
          retrievable: true,
        });
      },
      provisionAgentInstance: async (template, tuning) => {
        if (!this.templates.has(template)) return null;
        const id = this.id("agent");
        const system = String(tuning?.["prompts.system"] ?? "");
        this.agents.set(id, { template, name: "Self-test (auto)", system, enabled: true });
        return id;
      },
      deleteAgentInstance: async (id) => {
        this.agents.delete(id);
      },
      createContextPrompt: async (name, text) => {
        // Prompt names are unique per team, as on the platform.
        if ([...this.prompts.values()].some((p) => p.name === name))
          throw Object.assign(new Error("prompt name taken"), { status: 409 });
        const id = this.id("prompt");
        this.prompts.set(id, { name, text });
        return id;
      },
      deleteContextPrompt: async (id) => {
        this.prompts.delete(id);
      },
      createSession: async (agent) => {
        const id = this.id("session");
        this.sessions.set(id, { agent, title: "Self-test (auto)", prompts: [] });
        return id;
      },
      attachSessionPrompts: async (sessionId, promptIds) => {
        const session = this.sessions.get(sessionId);
        if (session) session.prompts = [...promptIds];
      },
      deleteSession: async (id) => {
        this.sessions.delete(id);
      },
      runAgentTurn: async ({ agentInstanceId, question, libraryIds, sessionId }) => {
        this.fail("runAgentTurn");
        const { answer, sources } = this.answer(agentInstanceId, question, libraryIds, sessionId);
        return { answer, sources, sessionId: sessionId ?? null, statusSeenAt: {} };
      },
    };
  }
}

/** Collects the last report of every step, in first-seen order. */
export function collect(): { steps: StepReport[]; report: Reporter; status: (id: string) => string } {
  const steps: StepReport[] = [];
  const report: Reporter = (step) => {
    const i = steps.findIndex((s) => s.id === step.id);
    if (i === -1) steps.push(step);
    else steps[i] = step;
  };
  return { steps, report, status: (id) => steps.find((s) => s.id === id)?.status ?? "missing" };
}

export const signal = new AbortController().signal;
