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
import type { CreateSessionAttachmentRequest } from "../../../../slices/controlPlane/controlPlaneOpenApi";

const { showWarn, translate } = vi.hoisted(() => ({
  showWarn: vi.fn(),
  translate: vi.fn((key: string) => key),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showWarn }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));
vi.mock("../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Assistant X" }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn(), useStore: () => ({ getState: () => ({}) }) }));
// No capability is active unless a test sets one; keep the plugin index (and
// its API slices) out of the import graph.
const capabilities = vi.hoisted(() => ({
  handlers: [] as Array<{ capabilityId: string; handle: (file: File) => Promise<unknown> }>,
}));
vi.mock("../../../features/capabilities/chatAttachmentRegistry", () => ({
  chatAttachmentHandlersForCapabilities: () => capabilities.handlers,
}));
vi.mock("../../../../common/capabilityRoutingSlice", () => ({
  selectCapabilityBaseUrl: () => (capabilities.handlers.length > 0 ? "/cap" : undefined),
}));
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
const persisted: CreateSessionAttachmentRequest[] = [];
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery: () => ({
    currentData: persisted,
    isFetching: false,
  }),
  usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation: () => [
    ({
      createSessionAttachmentRequest: attachment,
    }: {
      createSessionAttachmentRequest: CreateSessionAttachmentRequest;
    }) => {
      if (persistAttachmentBehavior.rejectNext) {
        return mockMutationResult(Promise.reject(new Error("simulated control-plane persist failure")));
      }
      persisted.push(attachment);
      return mockMutationResult(Promise.resolve({}));
    },
  ],
  useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation: () => [
    () => mockMutationResult(Promise.resolve({})),
  ],
}));

type Hook = ReturnType<typeof useChatAttachments>;

function TestHost({ onRender, sessionId = "session-1" }: { onRender: (hook: Hook) => void; sessionId?: string }) {
  onRender(useChatAttachments({ teamId: "team-1", sessionId }));
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
    capabilities.handlers = [];
    persistAttachmentBehavior.rejectNext = false;
    persisted.length = 0;
    showWarn.mockClear();
    translate.mockClear();
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

  it.each([
    ["truncated text", true, true, false, "documentTruncated"],
    ["short preview", false, true, false, "previewTruncated"],
    ["CSV preview clipped during conversion", true, false, true, "previewTruncated"],
    ["Excel roadmap preview", false, true, true, "previewTruncated"],
    ["complete text", false, false, false, null],
    ["legacy response without flags", undefined, undefined, undefined, null],
  ])(
    "preserves the correct notice after reload: %s",
    async (_, truncated, summary_truncated, tabular_available, key) => {
      await act(async () => {
        void latest.addFiles([pdf("a.pdf")], "paste", "session-1");
      });
      await act(async () => {
        pendingIngests[0].resolve({
          document_uid: "doc-a",
          summary_md: "Preview text",
          truncated,
          summary_truncated,
          tabular_available,
        });
      });

      const preview = key ? `> chatbot.attachments.${key}\n\nPreview text` : "Preview text";
      expect(persisted[0].summary_md).toBe(preview);
      if (key === "documentTruncated") {
        expect(translate).toHaveBeenCalledWith("chatbot.attachments.documentTruncated", {
          agentsNicknameSingular: "Assistant X",
        });
      }
      if (key) {
        expect(showWarn).toHaveBeenCalledWith({
          summary: "chatbot.attachments.notice",
          detail: `chatbot.attachments.${key}`,
        });
      } else {
        expect(showWarn).not.toHaveBeenCalled();
      }

      // Re-mount from the persisted API response, without the transient ingestion result.
      act(() => root.unmount());
      root = createRoot(container);
      act(() => root.render(<TestHost onRender={(hook) => (latest = hook)} />));
      expect(latest.persistedAttachments[0].summaryMd).toBe(preview);
    },
  );

  it("cleans up the Knowledge Flow artifact when the control-plane persist fails", async () => {
    persistAttachmentBehavior.rejectNext = true;

    await act(async () => {
      void latest.addFiles([pdf("a.pdf")], "paste", "session-1");
    });

    await act(async () => {
      pendingIngests[0].resolve({ document_uid: "doc-a", summary_md: "a" });
    });

    expect(statuses()).toEqual([["a.pdf", "error"]]);
    expect(showWarn).not.toHaveBeenCalled();
    expect(deleteFastArtifactsCalls).toEqual([{ documentUid: "doc-a", sessionId: "session-1" }]);
  });
});

describe("useChatAttachments - a capability's copy follows the chat", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: Hook;

  beforeEach(() => {
    pendingIngests.length = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<TestHost onRender={(hook) => (latest = hook)} />);
    });
  });

  afterEach(() => {
    capabilities.handlers = [];
    act(() => root.unmount());
    container.remove();
  });

  it("asks the capability to forget a file the user removes", async () => {
    const forget = vi.fn(() => Promise.resolve());
    capabilities.handlers = [{ capabilityId: "word_template", handle: () => Promise.resolve(forget) }];

    await act(async () => {
      void latest.addFiles([pdf("a.pdf")], "paste", "session-1");
    });
    await act(async () => {
      pendingIngests[0].resolve({ document_uid: "doc-a", summary_md: "" });
    });
    const id = latest.attachments[0].id;
    act(() => latest.removeAttachment(id));

    expect(forget).toHaveBeenCalledTimes(1);
  });

  it("forgets it too when the removal lands before the capability answered", async () => {
    const forget = vi.fn(() => Promise.resolve());
    let answer!: (value: unknown) => void;
    capabilities.handlers = [
      { capabilityId: "word_template", handle: () => new Promise((resolve) => (answer = resolve)) },
    ];

    await act(async () => {
      void latest.addFiles([pdf("a.pdf")], "paste", "session-1");
    });
    const id = latest.attachments[0].id;
    act(() => latest.removeAttachment(id));
    expect(forget).not.toHaveBeenCalled();

    await act(async () => {
      answer(forget);
    });
    expect(forget).toHaveBeenCalledTimes(1);
  });

  it("forgets a file whose upload failed: it is never sent", async () => {
    const forget = vi.fn(() => Promise.resolve());
    capabilities.handlers = [{ capabilityId: "word_template", handle: () => Promise.resolve(forget) }];
    persistAttachmentBehavior.rejectNext = true;

    await act(async () => {
      void latest.addFiles([pdf("a.pdf")], "paste", "session-1");
    });
    await act(async () => {
      pendingIngests[0].resolve({ document_uid: "doc-a", summary_md: "" });
    });

    expect(latest.attachments.map((attachment) => attachment.status)).toEqual(["error"]);
    expect(forget).toHaveBeenCalledTimes(1);
  });
});

describe("useChatAttachments — composer files stay in their conversation", () => {
  it("hides a file dropped in another conversation and shows it again on return", async () => {
    pendingIngests.length = 0;
    const container = document.createElement("div");
    const root = createRoot(container);
    let latest!: Hook;
    const render = (sessionId: string) =>
      act(() => root.render(<TestHost sessionId={sessionId} onRender={(hook) => (latest = hook)} />));

    render("session-1");
    await act(async () => {
      void latest.addFiles([pdf("a.pdf")], "drop", "session-1");
    });
    await act(async () => {
      pendingIngests[0].resolve({ document_uid: "doc-a", summary_md: "a" });
    });

    render("session-2");
    expect(latest.attachments).toEqual([]);
    // A send in session-2 clears its own ready chips only.
    act(() => latest.clearReadyAttachments());

    render("session-1");
    expect(latest.attachments.map((attachment) => attachment.name)).toEqual(["a.pdf"]);
    act(() => root.unmount());
  });
});
