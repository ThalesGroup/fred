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
import { historicalDocumentTreeText, parseDocumentTreeTrace } from "./documentTreeTrace";

function leaf(uid: string, name: string, added: string | null, extra: Record<string, unknown> = {}) {
  return JSON.stringify({ uid, name, added_to_kb: added, created: null, modified: null, ...extra });
}

describe("document tree trace", () => {
  it("keeps nested folder membership and counts repeated documents once", () => {
    const text = [
      "Sales [folder:sales]/",
      "  HR [folder:hr]/",
      "    " + leaf("hr-doc", "HR.pdf", "2026-10-12T09:00:00+02:00"),
      "  " + leaf("shared", "Overview.pdf", "2026-10-12T08:00:00Z"),
      "Other [folder:other]/",
      "  " + leaf("shared", "Overview.pdf", "2026-10-12T08:00:00Z"),
    ].join("\n");
    const data = parseDocumentTreeTrace(text)!;
    expect(data.documentCount).toBe(2);
    expect(data.latestUid).toBe("shared");
    expect(data.folders.map((folder) => [folder.path, folder.documents.map((document) => document.name)])).toEqual([
      ["Sales", ["Overview.pdf"]],
      ["Sales/HR", ["HR.pdf"]],
      ["Other", ["Overview.pdf"]],
    ]);
  });

  it("compares submillisecond arrival precision without using creation dates", () => {
    const text = [
      leaf("later", "Later.pdf", "2026-10-12T08:00:00.123457Z", { created: "2020-01-01T00:00:00Z" }),
      leaf("earlier", "Earlier.pdf", "2026-10-12T10:00:00.123456+02:00", { created: "2026-10-12T00:00:00Z" }),
      leaf("unknown", "Unknown.pdf", null),
    ].join("\n");
    expect(parseDocumentTreeTrace(text)?.latestUid).toBe("later");
  });

  it("decodes punctuation and newlines as document data", () => {
    const name = "Report [draft]/\nOther.pdf";
    const data = parseDocumentTreeTrace(
      "Docs/\n  " +
        leaf("doc", name, null, { title: "<script>unsafe</script>", page_count: 0, labels: ["[folder:fake]", 42] }),
    )!;
    expect(data.documentCount).toBe(1);
    expect(data.folders[0].documents[0]).toMatchObject({
      name,
      title: "<script>unsafe</script>",
      pageCount: 0,
      labels: ["[folder:fake]"],
    });
  });

  it("recognizes explicit and historical pruning warnings", () => {
    expect(
      parseDocumentTreeTrace(
        "Listing incomplete: omitted documents may be more recent.\nDocs/\n  " + leaf("doc", "Report.pdf", null),
      )?.truncated,
    ).toBe(true);
    expect(parseDocumentTreeTrace("Docs/\n  ... 42 more item(s) below, use search")?.truncated).toBe(true);
  });

  it("does not treat historical uploaded dates as Fred arrivals", () => {
    const data = parseDocumentTreeTrace("Sales [folder:secret]/\n  Report.pdf [private-doc] (uploaded 2026-01-01)")!;
    expect(data.latestUid).toBeNull();
    expect(data.folders[0].documents[0]).toMatchObject({
      name: "Report.pdf",
      legacyUploaded: "2026-01-01",
      addedToKb: null,
    });
  });

  it("rejects malformed payloads and tool failures and accepts empty results", () => {
    expect(parseDocumentTreeTrace('Docs/\n  {"uid":"private","name":')).toBeNull();
    expect(parseDocumentTreeTrace('{"uid":"private"}')).toBeNull();
    expect(parseDocumentTreeTrace("Could not list the document tree: service failed.")).toBeNull();
    expect(parseDocumentTreeTrace("(empty)")).toMatchObject({ documentCount: 0, folders: [], latestUid: null });
  });
});

it("reads JSON folders including allowed control characters and preserves old brace-prefixed folders", () => {
  const folder = "{Drafts}\n[copy]";
  const tree =
    JSON.stringify({ folder, folder_id: "private-folder" }) + "\n  " + leaf("private-document", "Report.pdf", null);
  expect(parseDocumentTreeTrace(tree)?.folders[0].path).toBe(folder);
  expect(
    parseDocumentTreeTrace("{Drafts} [folder:private-folder]/\n  Old.pdf [private-document] (uploaded 2026-01-01)")
      ?.documentCount,
  ).toBe(1);
});

it("reads actual Graph ToolInvocationResult envelopes without exposing other blocks", () => {
  const tree =
    JSON.stringify({ folder: "Docs", folder_id: "private-folder" }) +
    "\n  " +
    leaf("private-document", "Report.pdf", "2026-10-12T08:00:00Z");
  const envelope = JSON.stringify({
    tool_ref: "list_document_tree",
    blocks: [
      { kind: "text", text: "Listing incomplete: omitted documents may be more recent.\n" + tree },
      { kind: "json", data: { private: "do not render" } },
    ],
    is_error: false,
    sources: [],
    ui_parts: [],
  });
  expect(parseDocumentTreeTrace(envelope)).toMatchObject({
    documentCount: 1,
    latestUid: "private-document",
    truncated: true,
  });
  expect(
    parseDocumentTreeTrace(JSON.stringify({ tool_ref: "unknown", blocks: [{ kind: "text", text: tree }] })),
  ).toBeNull();
});

it("keeps otherwise unsupported legacy text readable without leaking ids or malformed JSON", () => {
  const old = "Drafts\n(copy) [folder:hidden-folder]/\n  Report.pdf [hidden-doc] (uploaded 2026-01-01)";
  expect(parseDocumentTreeTrace(old)).toBeNull();
  expect(historicalDocumentTreeText(old)).toBe("Drafts\n(copy)/\n  Report.pdf (uploaded 2026-01-01)");
  expect(historicalDocumentTreeText('Docs/\n  {"uid":"hidden-doc","name":"Report.pdf"')).toBeNull();
});

it("hides pre-prefix folder ids in parsed and fallback histories including Graph envelopes", () => {
  const tree = "Sales [private-tag-id]/\n  Report.pdf [private-doc] (uploaded 2026-01-01)";
  const envelope = JSON.stringify({ tool_ref: "list_document_tree", blocks: [{ kind: "text", text: tree }] });
  for (const text of [tree, envelope]) {
    expect(parseDocumentTreeTrace(text)?.folders[0].path).toBe("Sales");
  }
  const multiline = "Sales\n(copy) [private-tag-id]/\n  Report.pdf [private-doc] (uploaded 2026-01-01)";
  expect(historicalDocumentTreeText(multiline)).toBe("Sales\n(copy)/\n  Report.pdf (uploaded 2026-01-01)");
});

it("omits redundant empty ancestor groups while preserving empty leaf folders", () => {
  const tree = [
    JSON.stringify({ folder: "Sales" }),
    "  " + JSON.stringify({ folder: "HR" }),
    "    " + leaf("doc", "Report.pdf", null),
    JSON.stringify({ folder: "Empty" }),
  ].join("\n");
  expect(parseDocumentTreeTrace(tree)?.folders.map((folder) => folder.path)).toEqual(["Sales/HR", "Empty"]);
});

it("recognizes continuation without displaying cursors or treating paging as truncation", () => {
  const parsed = parseDocumentTreeTrace('(empty)\n{"page":{"next_cursor":"opaque","has_unknown_arrivals":true}}');
  expect(parsed?.hasMore).toBe(true);
  expect(parsed?.truncated).toBe(false);
  expect(JSON.stringify(parsed)).not.toContain("opaque");
});

it("keeps continuation metadata out of the malformed historical fallback", () => {
  const text = 'Docs/\ninvalid extra line\n  Report.pdf [uid] (uploaded 2026-10-12)\n{"page":{"next_cursor":"opaque"}}';
  expect(parseDocumentTreeTrace(text)).toBeNull();
  expect(historicalDocumentTreeText(text)).toBeNull();
});
