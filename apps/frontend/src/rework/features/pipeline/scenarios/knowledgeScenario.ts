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
import type { SearchPolicyName } from "../../../../slices/legacyKnowledgeFlow/knowledgeFlowOpenApi";
import { runStep, SkipStep } from "../step";
import type { PipelineDeps, Scenario } from "../types";
import { ALPHA, BETA, BETA_MARKER, fileOf, MARKER, PROBE, SELF_TEST_AGENT_ID } from "./corpus";
import { formatFixtures, tabularFixtures } from "./formats";
import { cleanup, newRunScope } from "./runScope";

export const SEARCH_POLICIES: SearchPolicyName[] = ["hybrid", "semantic", "strict"];
/** How long a positive check waits for the index to catch up; negative checks never wait. */
export const INDEX_WAIT_MS = 30_000;
const POLL_MS = 1_500;

export interface SearchHit {
  uid: string;
  content: string;
}

export interface SearchArgs {
  question: string;
  libraryIds?: string[];
  documentUids?: string[];
  policy?: SearchPolicyName;
}

export interface AuditFinding {
  uid: string;
  issues: string[];
}

export interface KnowledgeDeps extends PipelineDeps {
  documentsIn: (libraryId: string) => Promise<Array<{ uid: string; name: string }>>;
  search: (args: SearchArgs) => Promise<SearchHit[]>;
  linkDocument: (libraryId: string, uid: string) => Promise<void>;
  unlinkDocument: (libraryId: string, uid: string) => Promise<void>;
  setRetrievable: (uid: string, retrievable: boolean) => Promise<void>;
  documentTree: (libraryId: string) => Promise<string>;
  /** Rows of a SQL query on the document's dataset; `sql` receives the dataset alias. */
  tabularRows: (
    libraryId: string,
    uid: string,
    sql: (alias: string) => string,
  ) => Promise<Array<Record<string, unknown>>>;
  /** Documents the store audit finds inconsistent, across the whole platform. */
  audit: () => Promise<AuditFinding[]>;
  sleep: (ms: number) => Promise<void>;
}

const hasMarker = (hits: SearchHit[], marker: string) => hits.some((h) => h.content.includes(marker));

/** Polls a positive condition until the index shows it. */
async function eventually(deps: KnowledgeDeps, check: () => Promise<boolean>, signal: AbortSignal): Promise<boolean> {
  for (let waited = 0; ; waited += POLL_MS) {
    signal.throwIfAborted();
    if (await check()) return true;
    if (waited >= INDEX_WAIT_MS) return false;
    await deps.sleep(POLL_MS);
  }
}

/**
 * Knowledge family, in the personal space. The marker lives in ALPHA only, so
 * "found in ALPHA, absent from BETA" is deterministic even though real
 * retrieval answered. Each format fixture carries its own marker.
 */
export const knowledgeScenario: Scenario<KnowledgeDeps> = async (deps, report, signal) => {
  const scope = newRunScope();
  const alphaFile = fileOf(ALPHA, scope.token);
  const betaFile = fileOf(BETA, scope.token);
  let alpha: string | null = null;
  let beta: string | null = null;
  let formats: string | null = null;
  let agentInstanceId: string | null = null;
  let alphaDoc: string | null = null;
  const uids: string[] = [];

  const ingest = async (libraryId: string, file: File): Promise<string> => {
    await deps.ingestDocument(libraryId, file, signal);
    const doc = (await deps.documentsIn(libraryId)).find((d) => d.name === file.name);
    if (!doc) throw new Error(`${file.name} is indexed but not listed in its folder`);
    uids.push(doc.uid);
    return doc.uid;
  };

  try {
    alpha = await runStep(report, "create-alpha", "Create folder ALPHA", async () => {
      const id = await deps.createLibrary(scope.name(ALPHA.library));
      return { value: id, detail: `${scope.name(ALPHA.library)} (${id})` };
    });
    beta = await runStep(report, "create-beta", "Create folder BETA", async () => {
      const id = await deps.createLibrary(scope.name(BETA.library));
      return { value: id, detail: `${scope.name(BETA.library)} (${id})` };
    });
    agentInstanceId = await runStep(report, "provision-agent", "Provision the self-test agent", async () => {
      const id = await deps.provisionAgentInstance(SELF_TEST_AGENT_ID, undefined, signal, scope.token);
      if (!id) throw new SkipStep(`template '${SELF_TEST_AGENT_ID}' is not available on this deployment`);
      return { value: id, detail: id };
    });
    alphaDoc = await runStep(report, "ingest-alpha", "Upload and index a document into ALPHA", async () => {
      if (!alpha) throw new SkipStep("ALPHA folder missing");
      const uid = await ingest(alpha, alphaFile);
      return { value: uid, detail: `${alphaFile.name} (${uid})` };
    });
    await runStep(report, "ingest-beta", "Upload and index a document into BETA", async () => {
      if (!beta) throw new SkipStep("BETA folder missing");
      const uid = await ingest(beta, betaFile);
      return { value: undefined, detail: `${betaFile.name} (${uid})` };
    });

    await runStep(report, "query-alpha", "Ask the agent about ALPHA: the marker must be found", async () => {
      if (!alpha || !agentInstanceId) throw new SkipStep("ALPHA folder or agent instance missing");
      const turn = await deps.runAgentTurn({ agentInstanceId, question: PROBE, libraryIds: [alpha], signal });
      if (!turn.answer.includes(MARKER)) {
        throw new Error(`marker '${MARKER}' not in the agent answer (${turn.answer.slice(0, 80)}…)`);
      }
      return { value: undefined, detail: `marker retrieved (${turn.sources.length} source(s))` };
    });
    await runStep(report, "query-beta", "Ask the agent about BETA: B retrieved, ALPHA marker absent", async () => {
      if (!beta || !agentInstanceId) throw new SkipStep("BETA folder or agent instance missing");
      const turn = await deps.runAgentTurn({ agentInstanceId, question: PROBE, libraryIds: [beta], signal });
      // Absence of MARKER means isolation only if B retrieval actually ran and returned B content.
      if (turn.sources.length === 0 || !turn.answer.includes(BETA_MARKER)) {
        throw new Error(
          `BETA retrieval did not return B content (sources=${turn.sources.length}); the ALPHA marker's absence proves nothing`,
        );
      }
      if (turn.answer.includes(MARKER)) throw new Error(`marker '${MARKER}' leaked into the BETA scope`);
      return { value: undefined, detail: `B retrieved (${turn.sources.length} source(s)), ALPHA marker absent` };
    });

    for (const policy of SEARCH_POLICIES) {
      await runStep(report, `search-${policy}`, `Direct ${policy} search finds the ALPHA marker`, async () => {
        if (!alpha || !alphaDoc) throw new SkipStep("ALPHA document missing");
        const found = await eventually(
          deps,
          async () => hasMarker(await deps.search({ question: PROBE, libraryIds: [alpha!], policy }), MARKER),
          signal,
        );
        if (!found) throw new Error(`no ${policy} hit carries '${MARKER}' after ${INDEX_WAIT_MS / 1000} s`);
        return { value: undefined, detail: "marker found" };
      });
    }
    await runStep(
      report,
      "search-isolation",
      "Direct search scoped to BETA never returns the ALPHA marker",
      async () => {
        if (!beta || !alphaDoc) throw new SkipStep("fixtures missing");
        const hits = await deps.search({ question: PROBE, libraryIds: [beta], policy: "hybrid" });
        if (!hasMarker(hits, BETA_MARKER))
          throw new Error("BETA search returned no BETA content; isolation is unproven");
        if (hasMarker(hits, MARKER)) throw new Error(`'${MARKER}' leaked into a BETA-scoped search`);
        return { value: undefined, detail: `${hits.length} hit(s), all from BETA` };
      },
    );

    const linked = await runStep(
      report,
      "link-document",
      "A document linked into BETA becomes retrievable there",
      async () => {
        if (!beta || !alphaDoc) throw new SkipStep("fixtures missing");
        await deps.linkDocument(beta, alphaDoc);
        const found = await eventually(
          deps,
          async () => hasMarker(await deps.search({ question: PROBE, libraryIds: [beta!], policy: "hybrid" }), MARKER),
          signal,
        );
        if (!found) throw new Error("the linked document is not retrievable from BETA");
        return { value: true, detail: `${alphaDoc} linked` };
      },
    );
    await runStep(report, "unlink-document", "Once unlinked, it is no longer retrievable from BETA", async () => {
      if (!linked) throw new SkipStep("linking into BETA was not proven");
      if (!beta || !alphaDoc) throw new SkipStep("fixtures missing");
      await deps.unlinkDocument(beta, alphaDoc);
      const hits = await deps.search({ question: PROBE, libraryIds: [beta], policy: "hybrid" });
      if (hasMarker(hits, MARKER)) throw new Error("the unlinked document is still retrievable from BETA");
      return { value: undefined, detail: "not returned right after the unlink" };
    });

    const hidden = await runStep(
      report,
      "retrievable-off",
      "A document marked non-retrievable is not returned",
      async () => {
        if (!alpha || !alphaDoc) throw new SkipStep("ALPHA document missing");
        await deps.setRetrievable(alphaDoc, false);
        const hits = await deps.search({ question: PROBE, libraryIds: [alpha], policy: "hybrid" });
        if (hasMarker(hits, MARKER)) throw new Error("a non-retrievable document was returned");
        return { value: true, detail: "not returned" };
      },
    );
    await runStep(report, "retrievable-on", "Marked retrievable again, it comes back", async () => {
      if (!hidden) throw new SkipStep("non-retrievability was not proven");
      if (!alpha || !alphaDoc) throw new SkipStep("ALPHA document missing");
      await deps.setRetrievable(alphaDoc, true);
      const found = await eventually(
        deps,
        async () => hasMarker(await deps.search({ question: PROBE, libraryIds: [alpha!], policy: "hybrid" }), MARKER),
        signal,
      );
      if (!found) throw new Error("the document did not come back");
      return { value: undefined, detail: "returned again" };
    });
    await runStep(report, "document-tree", "The folder's document tree lists its document", async () => {
      if (!alpha) throw new SkipStep("ALPHA folder missing");
      const tree = await deps.documentTree(alpha);
      if (!tree.includes(alphaFile.name)) throw new Error(`${alphaFile.name} is missing from the tree`);
      return { value: undefined, detail: `${tree.split("\n").length} line(s)` };
    });

    formats = await runStep(report, "create-formats", "Create a folder for the format fixtures", async () => {
      const id = await deps.createLibrary(scope.name("fred-selftest-formats"));
      return { value: id, detail: id };
    });
    for (const fixture of formatFixtures(scope.token)) {
      await runStep(
        report,
        `format-${fixture.id}`,
        `A .${fixture.id} document is ingested and retrievable`,
        async () => {
          if (!formats) throw new SkipStep("formats folder missing");
          const uid = await ingest(formats, await fixture.build(scope.name(`fred-selftest`) + `.${fixture.id}`));
          const found = await eventually(
            deps,
            async () =>
              hasMarker(
                await deps.search({ question: fixture.marker, documentUids: [uid], policy: "hybrid" }),
                fixture.marker,
              ),
            signal,
          );
          if (!found) throw new Error(`no chunk of the .${fixture.id} document carries its marker`);
          return { value: undefined, detail: uid };
        },
      );
    }
    for (const fixture of tabularFixtures(scope.token)) {
      await runStep(report, `tabular-${fixture.id}`, `A .${fixture.id} document is queryable in SQL`, async () => {
        if (!formats) throw new SkipStep("formats folder missing");
        const uid = await ingest(formats, await fixture.build());
        const rows = await deps.tabularRows(formats, uid, (alias) => `SELECT label FROM "${alias}" WHERE code = 1`);
        if (!rows.some((row) => Object.values(row).includes(fixture.marker))) {
          throw new Error(`the query did not return the row carrying '${fixture.marker}'`);
        }
        return { value: undefined, detail: `${rows.length} row(s)` };
      });
    }
    // The audit spans the platform; only this run's documents are its to judge.
    await runStep(report, "corpus-audit", "This run's documents are consistent across stores", async () => {
      if (uids.length === 0) throw new SkipStep("no document was created");
      const own = new Set(uids);
      let found: AuditFinding[] = [];
      const clean = await eventually(
        deps,
        async () => {
          found = (await deps.audit()).filter((f) => own.has(f.uid));
          return found.length === 0;
        },
        signal,
      );
      if (!clean) throw new Error(`inconsistent: ${found.map((f) => `${f.uid} (${f.issues.join(", ")})`).join("; ")}`);
      return { value: undefined, detail: `${uids.length} document(s) consistent` };
    });
  } finally {
    await cleanup(
      report,
      "delete-agent",
      "Delete the self-test agent",
      agentInstanceId,
      deps.deleteAgentInstance,
      (id) => deps.verifyDeleted("agent", id),
    );
    await cleanup(report, "delete-alpha", "Delete folder ALPHA and its document", alpha, deps.deleteLibrary, (id) =>
      deps.verifyDeleted("library", id),
    );
    await cleanup(report, "delete-beta", "Delete folder BETA and its document", beta, deps.deleteLibrary, (id) =>
      deps.verifyDeleted("library", id),
    );
    await cleanup(
      report,
      "delete-formats",
      "Delete the formats folder and its documents",
      formats,
      deps.deleteLibrary,
      (id) => deps.verifyDeleted("library", id),
    );
    await runStep(
      report,
      "verify-deletion",
      "Verify the folders are gone",
      async () => {
        const created = [alpha, beta, formats].filter((id): id is string => id != null);
        if (created.length === 0) throw new SkipStep("nothing was created");
        const ids = new Set((await deps.listLibraries()).map((l) => l.id));
        const remaining = created.filter((id) => ids.has(id));
        if (remaining.length) throw new Error(`${remaining.length} folder(s) still present after delete`);
        return { value: undefined, detail: "all created folders removed" };
      },
      { optional: true },
    );
    await runStep(
      report,
      "no-residue",
      "No audited residue or searchable chunk remains after deletion",
      async () => {
        if (uids.length === 0) throw new SkipStep("no document was created");
        // Search already drops chunks without metadata, so only the audit sees what a delete left behind.
        const own = new Set(uids);
        let found: AuditFinding[] = [];
        const gone = await eventually(
          deps,
          async () => {
            found = (await deps.audit()).filter((f) => own.has(f.uid));
            return found.length === 0;
          },
          signal,
        );
        if (!gone) throw new Error(`left behind: ${found.map((f) => `${f.uid} (${f.issues.join(", ")})`).join("; ")}`);
        const hits = await deps.search({ question: PROBE, documentUids: uids, policy: "hybrid" });
        const searchable = hits.filter((hit) => own.has(hit.uid));
        if (searchable.length)
          throw new Error(`still searchable after deletion: ${searchable.map((hit) => hit.uid).join(", ")}`);
        return { value: undefined, detail: `no audit anomaly or search hit for ${uids.length} deleted document(s)` };
      },
      { optional: true },
    );
  }
};
