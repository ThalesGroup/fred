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
import { describe, expect, it } from "vitest";
import { MARKER } from "./corpus";
import { collect, FakePlatform, signal } from "./fakePlatform";
import { formatFixtures, pdfBytes, tabularFixtures } from "./formats";
import { knowledgeScenario, SEARCH_POLICIES } from "./knowledgeScenario";

async function run(platform: FakePlatform, deps = platform.knowledgeDeps()) {
  const r = collect();
  await knowledgeScenario(deps, r.report, signal);
  return r;
}

describe("knowledgeScenario", () => {
  it("passes every check and removes every fixture", async () => {
    const platform = new FakePlatform();
    const r = await run(platform);
    expect(r.steps.filter((s) => s.status !== "passed").map((s) => `${s.id}:${s.status}`)).toEqual([]);
    for (const policy of SEARCH_POLICIES) expect(r.status(`search-${policy}`)).toBe("passed");
    for (const f of formatFixtures("x")) expect(r.status(`format-${f.id}`)).toBe("passed");
    for (const f of tabularFixtures("x")) expect(r.status(`tabular-${f.id}`)).toBe("passed");
    expect(platform.libraries.size).toBe(0);
    expect(platform.documents).toEqual([]);
    expect(platform.agents.size).toBe(0);
  });

  it("fails isolation when the ALPHA marker leaks into BETA", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    const ingest = deps.ingestDocument;
    deps.ingestDocument = async (libraryId, file, s) => {
      await ingest(libraryId, file, s);
      const doc = platform.documents[platform.documents.length - 1];
      for (const id of platform.libraries.keys()) doc.libraries.add(id);
    };
    const r = await run(platform, deps);
    expect(r.status("query-beta")).toBe("failed");
    expect(r.status("search-isolation")).toBe("failed");
  });

  it("fails when an unlink does not take effect, without waiting for it", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    deps.unlinkDocument = async () => {};
    let slept = 0;
    deps.sleep = async () => {
      slept += 1;
    };
    const before = slept;
    const r = await run(platform, deps);
    expect(r.status("unlink-document")).toBe("failed");
    expect(slept).toBe(before);
  });

  it("does not credit unlink when linking was never observed", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    deps.linkDocument = async () => {};
    const r = await run(platform, deps);
    expect(r.status("link-document")).toBe("failed");
    expect(r.status("unlink-document")).toBe("skipped");
  });

  it("fails one format and keeps checking the others", async () => {
    const platform = new FakePlatform();
    const pdf = formatFixtures("x").find((f) => f.id === "pdf")!;
    const deps = platform.knowledgeDeps();
    const ingest = deps.ingestDocument;
    deps.ingestDocument = async (libraryId, file, s) => {
      if (file.name.endsWith(".pdf")) throw new Error("no extractor for .pdf");
      await ingest(libraryId, file, s);
    };
    const r = await run(platform, deps);
    expect(r.status("format-pdf")).toBe("failed");
    expect(r.status("format-docx")).toBe("passed");
    expect(pdf.marker).toContain("pdf");
  });

  it("never looks for a spreadsheet in the search index", () => {
    expect(formatFixtures("x").map((f) => f.id)).not.toContain("xlsx");
  });

  it("fails a spreadsheet whose marker row the SQL query does not return", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    const rows = deps.tabularRows;
    deps.tabularRows = async (libraryId, uid, sql) =>
      platform.documents.find((d) => d.uid === uid)?.name.endsWith(".xlsx") ? [] : rows(libraryId, uid, sql);
    const r = await run(platform, deps);
    expect(r.status("tabular-xlsx")).toBe("failed");
    expect(r.status("tabular-csv")).toBe("passed");
  });

  it("fails when a non-retrievable document is still returned", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    deps.setRetrievable = async () => {};
    const r = await run(platform, deps);
    expect(r.status("retrievable-off")).toBe("failed");
    expect(r.status("retrievable-on")).toBe("skipped");
  });

  it("reports what a delete left behind even when search no longer returns it", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    const remove = deps.deleteLibrary;
    deps.deleteLibrary = async (id) => {
      platform.residue.push(...platform.documents.filter((d) => d.libraries.has(id)));
      await remove(id);
    };
    // Search drops chunks whose metadata is gone, as the platform does.
    const search = deps.search;
    deps.search = async (args) => (await search(args)).filter((h) => !platform.residue.some((d) => d.uid === h.uid));
    const residue = (await run(platform, deps)).steps.find((s) => s.id === "no-residue");
    expect(residue?.status).toBe("failed");
    expect(residue?.error).toContain("orphan_vectors");
  });

  it("fails deletion when a run document is still searchable without an audit anomaly", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    deps.deleteLibrary = async (id) => {
      platform.libraries.delete(id);
      for (const doc of platform.documents) doc.libraries.delete(id);
    };
    const residue = (await run(platform, deps)).steps.find((s) => s.id === "no-residue");
    expect(residue?.status).toBe("failed");
    expect(residue?.error).toContain("searchable");
  });

  it("fails when one of this run's documents is inconsistent", async () => {
    const platform = new FakePlatform();
    const deps = platform.knowledgeDeps();
    deps.audit = async () => platform.documents.slice(0, 1).map((d) => ({ uid: d.uid, issues: ["missing_vectors"] }));
    const audit = (await run(platform, deps)).steps.find((s) => s.id === "corpus-audit");
    expect(audit?.status).toBe("failed");
    expect(audit?.error).toContain("missing_vectors");
  });

  it("ignores inconsistencies of documents the run did not create", async () => {
    const platform = new FakePlatform();
    platform.auditFindings = [{ uid: "someone-else", issues: ["orphan_vectors"] }];
    expect((await run(platform)).status("corpus-audit")).toBe("passed");
  });

  it("writes a PDF with a valid cross-reference", () => {
    const text = new TextDecoder().decode(pdfBytes(`marker ${MARKER}`));
    const xref = Number(/startxref\n(\d+)/.exec(text)?.[1]);
    expect(text.slice(xref, xref + 4)).toBe("xref");
    for (const match of text.matchAll(/^(\d{10}) 00000 n /gm)) {
      expect(text.slice(Number(match[1])).match(/^\d+ 0 obj/)).not.toBeNull();
    }
  });
});
