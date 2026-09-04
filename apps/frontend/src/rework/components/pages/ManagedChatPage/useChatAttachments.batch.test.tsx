// @vitest-environment happy-dom
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

// Drives `useChatAttachments.addFiles` through a minimal host component (no
// @testing-library/react in this repo): a multi-file batch must show every
// file at once, not reveal file N only after file N-1 finished ingesting.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChatAttachments } from "./useChatAttachments";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn() }));
vi.mock("@core/hooks/useApiErrorToast.ts", () => ({
  useApiErrorToast: () => ({ notifyApiError: vi.fn() }),
}));

function mockMutationResult<T>(promise: Promise<T>): Promise<T> & { unwrap: () => Promise<T> } {
  const result = promise as Promise<T> & { unwrap: () => Promise<T> };
  result.unwrap = () => promise;
  return result;
}

// One deferred per fast-ingest call, settled by hand so the test controls
// which file finishes first.
const pendingIngests: Array<{ name: string; resolve: (value: unknown) => void }> = [];
// Calls made through the mocked delete-fast-artifacts mutation, so a test can
// assert Knowledge Flow cleanup fired (or didn't) without a real store.
const deleteFastArtifactsCalls: Array<{ documentUid: string; sessionId?: string | null }> = [];
vi.mock("../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useFastIngestKnowledgeFlowV1FastIngestPostMutation: () => [
    (args: { bodyFastIngestKnowledgeFlowV1FastIngestPost: FormData }) => {
      const name = (args.bodyFastIngestKnowledgeFlowV1FastIngestPost.get("file") as File).name;
      let resolve!: (value: unknown) => void;
      const promise = new Promise<unknown>((r) => (resolve = r));
      pendingIngests.push({ name, resolve });
      return mockMutationResult(promise);
    },
  ],
  useDeleteFastArtifactsKnowledgeFlowV1FastDeleteDocumentUidDeleteMutation: () => [
    (args: { documentUid: string; sessionId?: string | null }) => {
      deleteFastArtifactsCalls.push(args);
      return mockMutationResult(Promise.resolve({}));
    },
  ],
}));
const persistAttachmentBehavior = { rejectNext: false };
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery: () => ({
    data: [],
    isFetching: false,
  }),
  usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation: () => [
    () =>
      persistAttachmentBehavior.rejectNext
        ? mockMutationResult(Promise.reject(new Error("simulated control-plane persist failure")))
        : mockMutationResult(Promise.resolve({})),
  ],
  useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation: () => [
    () => mockMutationResult(Promise.resolve({})),
  ],
}));

type Hook = ReturnType<typeof useChatAttachments>;

function TestHost({ onRender }: { onRender: (hook: Hook) => void }) {
  onRender(useChatAttachments({ teamId: "team-1", sessionId: "session-1" }));
  return null;
}

function pdf(name: string): File {
  return new File(["%PDF"], name, { type: "application/pdf" });
}

describe("useChatAttachments.addFiles — multi-file batch", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: Hook;

  const statuses = () => latest.attachments.map((attachment) => [attachment.name, attachment.status]);

  beforeEach(() => {
    pendingIngests.length = 0;
    deleteFastArtifactsCalls.length = 0;
    persistAttachmentBehavior.rejectNext = false;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<TestHost onRender={(hook) => (latest = hook)} />);
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("shows every file of the batch as ingesting before any ingestion has finished", async () => {
    await act(async () => {
      void latest.addFiles([pdf("a.pdf"), pdf("b.pdf")], "paste", "session-1");
    });

    expect(statuses()).toEqual([
      ["a.pdf", "ingesting"],
      ["b.pdf", "ingesting"],
    ]);
    expect(pendingIngests.map((ingest) => ingest.name)).toEqual(["a.pdf", "b.pdf"]);
    expect(latest.hasUploadingAttachments).toBe(true);
  });

  it("lets each file settle on its own, in whichever order ingestion completes", async () => {
    await act(async () => {
      void latest.addFiles([pdf("a.pdf"), pdf("b.pdf")], "paste", "session-1");
    });

    await act(async () => {
      pendingIngests[1].resolve({ document_uid: "doc-b", summary_md: "b" });
    });
    expect(statuses()).toEqual([
      ["a.pdf", "ingesting"],
      ["b.pdf", "ready"],
    ]);
    expect(latest.hasUploadingAttachments).toBe(true);

    await act(async () => {
      pendingIngests[0].resolve({ document_uid: "doc-a", summary_md: "a" });
    });
    expect(statuses()).toEqual([
      ["a.pdf", "ready"],
      ["b.pdf", "ready"],
    ]);
    expect(latest.attachments.map((attachment) => attachment.documentUid)).toEqual(["doc-a", "doc-b"]);
    expect(latest.hasUploadingAttachments).toBe(false);
  });

  it("cleans up the Knowledge Flow artifact when the control-plane persist fails", async () => {
    persistAttachmentBehavior.rejectNext = true;

    await act(async () => {
      void latest.addFiles([pdf("a.pdf")], "paste", "session-1");
    });

    await act(async () => {
      pendingIngests[0].resolve({ document_uid: "doc-a", summary_md: "a" });
    });

    expect(statuses()).toEqual([["a.pdf", "error"]]);
    expect(deleteFastArtifactsCalls).toEqual([{ documentUid: "doc-a", sessionId: "session-1" }]);
  });
});
