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

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatAttachment, SessionAttachment } from "@rework/types/attachments";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const hookMocks = vi.hoisted(() => ({
  deleteMutation: vi.fn(),
  fastIngestMutation: vi.fn(),
  notifyApiError: vi.fn(),
  persistMutation: vi.fn(),
}));

vi.mock("react-redux", () => ({ useDispatch: () => vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useApiErrorToast.ts", () => ({
  useApiErrorToast: () => ({ notifyApiError: hookMocks.notifyApiError }),
}));
vi.mock("../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useFastIngestKnowledgeFlowV1FastIngestPostMutation: () => [hookMocks.fastIngestMutation],
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery: () => ({
    data: [{ attachment_id: "attachment-1", name: "report.pdf", summary_md: "summary" }],
    isFetching: false,
  }),
  usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation: () => [
    hookMocks.persistMutation,
  ],
  useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation: () => [
    hookMocks.deleteMutation,
  ],
}));
vi.mock("../../../features/tasks/taskSlice", () => ({
  taskEventReceived: (payload: unknown) => payload,
  taskRegistered: (payload: unknown) => payload,
}));

import {
  buildAttachmentsMarkdown,
  excludeDeletedAttachments,
  mergeRestoredReadyAttachments,
  useChatAttachments,
} from "./useChatAttachments";

describe("buildAttachmentsMarkdown", () => {
  it("announces persisted attachments to the runtime", () => {
    const attachment = {
      attachmentId: "attachment-1",
      name: "report.pdf",
    } as SessionAttachment;

    expect(buildAttachmentsMarkdown([attachment], [])).toContain("- report.pdf: conversation document");
  });

  it("carries the internal document uid so document tools can resolve the file", () => {
    const attachment = {
      attachmentId: "attachment-1",
      name: "report.pdf",
      documentUid: "554ab873903c40fdad52f36e2cffb501",
    } as SessionAttachment;

    expect(buildAttachmentsMarkdown([attachment], [])).toContain(
      "- report.pdf [554ab873903c40fdad52f36e2cffb501]: conversation document",
    );
  });

  it("returns null once the last attachment has been deleted", () => {
    const attachment = {
      attachmentId: "attachment-1",
      name: "report.pdf",
    } as SessionAttachment;
    const remaining = excludeDeletedAttachments([attachment], new Set(["attachment-1"]));

    expect(buildAttachmentsMarkdown(remaining, [])).toBeNull();
  });

  it("announces a ready transient document until the persisted attachment query catches up", () => {
    const transient = {
      id: "attachment-2",
      name: "late-report.pdf",
      size: 10,
      mime: "application/pdf",
      status: "ready",
      isImage: false,
      documentUid: "document-2",
      taskIds: [],
    } satisfies ChatAttachment;

    expect(buildAttachmentsMarkdown([], [transient])).toContain(
      "- late-report.pdf [document-2]: conversation document",
    );

    const persisted = {
      attachmentId: transient.id,
      name: transient.name,
      documentUid: transient.documentUid,
    } as SessionAttachment;
    const caughtUp = buildAttachmentsMarkdown([persisted], [transient]) ?? "";
    expect(caughtUp.match(/late-report\.pdf/g)).toHaveLength(1);
  });
});

describe("mergeRestoredReadyAttachments", () => {
  it("restores missing ready attachments with inline-image context without duplicating existing ids", () => {
    const existing = {
      id: "existing",
      name: "existing.pdf",
      size: 10,
      mime: "application/pdf",
      status: "ready",
      isImage: false,
      taskIds: [],
    } satisfies ChatAttachment;
    const image = {
      id: "image",
      name: "diagram.png",
      size: 42,
      mime: "image/png",
      status: "ready",
      isImage: true,
      imageContext: {
        name: "diagram.png",
        mime: "image/png",
        size: 42,
        dataUrl: "data:image/png;base64,cGl4ZWxz",
      },
      taskIds: ["task-1"],
    } satisfies ChatAttachment;

    const merged = mergeRestoredReadyAttachments([existing], [existing, image]);

    expect(merged).toEqual([existing, image]);
    expect(merged[1]?.imageContext?.dataUrl).toBe(image.imageContext.dataUrl);
  });

  it("does not resurrect an attachment deleted while the rejected turn was in flight", () => {
    const deleted = {
      id: "deleted",
      name: "deleted.pdf",
      size: 10,
      mime: "application/pdf",
      status: "ready",
      isImage: false,
      taskIds: [],
    } satisfies ChatAttachment;

    expect(mergeRestoredReadyAttachments([], [deleted], new Set([deleted.id]))).toEqual([]);
  });
});

describe("useChatAttachments deletion ownership", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useChatAttachments>;
  const requests: Array<ReturnType<typeof deferred<void>>> = [];

  function deferred<T>() {
    let resolve!: (value: T | PromiseLike<T>) => void;
    let reject!: (reason?: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  function Host({ sessionId }: { sessionId: string }) {
    latest = useChatAttachments({ teamId: "team-1", sessionId });
    return null;
  }

  const render = (sessionId: string) => {
    act(() => root.render(createElement(Host, { sessionId })));
  };

  beforeEach(() => {
    hookMocks.notifyApiError.mockClear();
    hookMocks.deleteMutation.mockReset();
    requests.length = 0;
    hookMocks.deleteMutation.mockImplementation(() => {
      const request = deferred<void>();
      requests.push(request);
      return { unwrap: () => request.promise };
    });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("does not let an old deletion failure clear a newer tombstone for the same session and id", async () => {
    render("session-a");
    let firstAttempt!: Promise<void>;
    await act(async () => {
      firstAttempt = latest.deletePersistedAttachment("attachment-1");
      await Promise.resolve();
    });
    expect(latest.persistedAttachments).toEqual([]);

    render("session-b");
    render("session-a");
    let secondAttempt!: Promise<void>;
    await act(async () => {
      secondAttempt = latest.deletePersistedAttachment("attachment-1");
      await Promise.resolve();
    });
    expect(latest.persistedAttachments).toEqual([]);

    await act(async () => {
      requests[0]?.reject(new Error("old delete failed"));
      await firstAttempt;
    });
    expect(latest.persistedAttachments).toEqual([]);

    await act(async () => {
      requests[1]?.reject(new Error("current delete failed"));
      await secondAttempt;
    });
    expect(latest.persistedAttachments.map((attachment) => attachment.attachmentId)).toEqual(["attachment-1"]);
  });
});

describe("useChatAttachments rejection rollback", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useChatAttachments>;

  function Host() {
    latest = useChatAttachments({ teamId: "team-1", sessionId: "session-a" });
    return null;
  }

  beforeEach(() => {
    hookMocks.deleteMutation.mockReset();
    hookMocks.deleteMutation.mockReturnValue({ unwrap: async () => undefined });
    hookMocks.fastIngestMutation.mockReset();
    hookMocks.fastIngestMutation.mockReturnValue({
      unwrap: async () => ({ document_uid: "document-1", summary_md: "summary" }),
    });
    hookMocks.persistMutation.mockReset();
    hookMocks.persistMutation.mockReturnValue({ unwrap: async () => undefined });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root.render(createElement(Host)));
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("clears only captured ready attachments and preserves later-ready files for the next turn", async () => {
    const submittedImage = new File(["pixels"], "diagram.png", { type: "image/png" });
    const nextTurnImage = new File(["later"], "later.png", { type: "image/png" });
    let cleared: readonly ChatAttachment[] = [];

    await act(async () => {
      await latest.addFiles([submittedImage], "picker", "session-a");
    });
    const submittedId = latest.attachments[0]?.id;
    expect(submittedId).toBeDefined();

    await act(async () => {
      await latest.addFiles([nextTurnImage], "picker", "session-a");
      cleared = latest.clearReadyAttachments([submittedId!]);
    });

    expect(cleared).toHaveLength(1);
    expect(cleared[0]?.name).toBe("diagram.png");
    expect(cleared[0]?.imageContext?.dataUrl).toContain("data:image/png");
    expect(latest.attachments.map((attachment) => attachment.name)).toEqual(["later.png"]);

    act(() => latest.restoreReadyAttachments(cleared));
    expect(latest.attachments.map((attachment) => attachment.name)).toEqual(["later.png", "diagram.png"]);
    expect(latest.attachments[1]?.imageContext?.dataUrl).toBe(cleared[0]?.imageContext?.dataUrl);
  });

  it("reads ready attachment ids and context from the synchronous turn-start snapshot", async () => {
    const document = new File(["content"], "late-report.pdf", { type: "application/pdf" });

    await act(async () => {
      await latest.addFiles([document], "picker", "session-a");
    });

    const snapshot = latest.getReadyAttachmentSnapshot();
    expect(snapshot.attachmentIds).toEqual([latest.attachments[0]?.id]);
    expect(snapshot.attachmentsMarkdown).toContain("- late-report.pdf [document-1]: conversation document");
  });

  it("keeps failed attachment chips outside a submitted turn's ready snapshot", async () => {
    hookMocks.fastIngestMutation.mockReturnValueOnce({
      unwrap: async () => {
        throw new Error("ingestion failed");
      },
    });
    const failed = new File(["content"], "failed.pdf", { type: "application/pdf" });

    await act(async () => {
      await latest.addFiles([failed], "picker", "session-a");
    });
    const failedId = latest.attachments[0]?.id;
    expect(latest.attachments[0]?.status).toBe("error");

    const cleared = latest.clearReadyAttachments([failedId!]);
    expect(cleared).toEqual([]);
    expect(latest.attachments.map((attachment) => attachment.id)).toEqual([failedId]);
  });

  it("does not restore a persisted attachment deleted in the same render window", async () => {
    const deleted = {
      id: "attachment-1",
      name: "report.pdf",
      size: 10,
      mime: "application/pdf",
      status: "ready",
      isImage: false,
      taskIds: [],
    } satisfies ChatAttachment;

    await act(async () => {
      const deletion = latest.deletePersistedAttachment(deleted.id);
      latest.restoreReadyAttachments([deleted]);
      await deletion;
    });

    expect(latest.attachments).toEqual([]);
  });
});
