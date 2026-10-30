// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Attachment, UploadReceipt } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useChatAttachments } from "./useChatAttachments";
import { attachmentUploadScope } from "./attachmentUploads";
import { managerImportsSnapshot } from "../../../features/imports/managerImportRun";

const identity = vi.hoisted(() => ({ actor: "" }));
const notify = vi.hoisted(() => vi.fn());
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetSessionIdentity: () => identity.actor,
    GetUserId: () => identity.actor,
    GetToken: () => identity.actor,
    ensureFreshToken: async () => true,
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useApiErrorToast.ts", () => ({ useApiErrorToast: () => ({ notifyApiError: notify }) }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const NativeRequest = globalThis.Request;
const reply = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const file = () => new File(["bytes"], "table.csv", { type: "text/csv" });
function document(ready = false, status: "running" | "succeeded" | "failed" = "running"): Attachment {
  return {
    document_id: "doc",
    name: "table.csv",
    mime: "text/csv",
    size: 5,
    ready,
    created_at: "2026-10-29T10:00:00Z",
    processing: {
      id: "process",
      document_id: "doc",
      status,
      profile: "fast",
      stage: status === "running" ? "extraction" : "done",
      chunks: 0,
      vectors: 0,
      revision: 1,
      created_at: "2026-10-29T10:00:00Z",
    },
  };
}
function receipt(key: string): UploadReceipt {
  return {
    request_key: key,
    document_id: "doc",
    name: "table.csv",
    mime: "text/csv",
    size: 5,
    status: "stored",
    folder_id: null,
    session_id: "conversation",
    space_id: "personal-space",
    sha256: "a".repeat(64),
    created_at: "2026-10-29T10:00:00Z",
  };
}
type Hook = ReturnType<typeof useChatAttachments>;
function Host({
  onRender,
  sessionId,
  enabled,
  canUpload,
}: {
  onRender: (value: Hook) => void;
  sessionId: string;
  enabled: boolean;
  canUpload: boolean;
}) {
  onRender(useChatAttachments({ spaceId: "personal-space", sessionId, enabled, canUpload }));
  return null;
}
function makeStore() {
  return configureStore({ reducer: { [api.reducerPath]: api.reducer }, middleware: (d) => d().concat(api.middleware) });
}

describe("conversation attachment transport and server state", () => {
  let root: Root;
  let container: HTMLDivElement;
  let store: ReturnType<typeof makeStore>;
  let latest: Hook;
  let documents: Attachment[];
  let fetcher: ReturnType<typeof vi.fn<(request: Request) => Promise<Response>>>;
  const render = async (sessionId = "conversation", enabled = true, canUpload = true) => {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <Host
            canUpload={canUpload}
            sessionId={sessionId}
            enabled={enabled}
            onRender={(h) => {
              latest = h;
            }}
          />
        </Provider>,
      );
    });
  };
  const refresh = async () => {
    await act(async () => {
      await latest.refreshAttachments();
    });
  };
  beforeEach(() => {
    identity.actor = crypto.randomUUID();
    localStorage.clear();
    notify.mockClear();
    documents = [];
    vi.stubGlobal(
      "Request",
      class extends NativeRequest {
        constructor(input: RequestInfo | URL, init?: RequestInit) {
          super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
        }
      },
    );
    fetcher = vi.fn(async (request) =>
      request.method === "GET" ? reply(documents) : reply(receipt(request.headers.get("Idempotency-Key") ?? ""), 201),
    );
    vi.stubGlobal("fetch", fetcher);
    store = makeStore();
    container = window.document.createElement("div");
    root = createRoot(container);
  });
  afterEach(async () => {
    await act(async () => {
      root.unmount();
      store.dispatch(api.util.resetApiState());
    });
    vi.unstubAllGlobals();
    vi.useRealTimers();
    container.remove();
  });
  it("keeps a stored receipt and chip when refetch joins a list started before upload", async () => {
    vi.useFakeTimers();
    let finishList!: (response: Response) => void;
    fetcher.mockImplementation(async (request) =>
      request.method === "GET"
        ? new Promise((resolve) => {
            finishList = resolve;
          })
        : reply(receipt(request.headers.get("Idempotency-Key")!), 201),
    );
    await render();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher.mock.calls.filter(([request]) => request.method === "GET")).toHaveLength(1);
    await act(async () => {
      await latest.addFiles([file()], "picker");
    });
    const scope = attachmentUploadScope(identity.actor, "personal-space", "conversation");
    expect(scope.entries[0].phase).toBe("stored");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetcher.mock.calls.filter(([request]) => request.method === "GET")).toHaveLength(1);
    await act(async () => {
      finishList(reply([]));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(scope.entries[0]?.phase).toBe("stored");
    expect(latest.attachments).toEqual([expect.objectContaining({ status: "ingesting" })]);
    expect(latest.hasUploadingAttachments).toBe(true);
    fetcher.mockImplementation(async () => reply([document(true, "succeeded")]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(scope.entries).toEqual([]);
    expect(latest.attachments).toEqual([expect.objectContaining({ id: "doc", status: "ready" })]);
    expect(latest.hasUploadingAttachments).toBe(false);
    const calls = fetcher.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(fetcher).toHaveBeenCalledTimes(calls);
  });
  it("posts multipart in the personal space and waits for ready, without drive events or duplicate chips", async () => {
    await render();
    await act(async () => {
      await latest.addFiles([file()], "picker");
    });
    const post = fetcher.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(new URL(post.url).pathname).toBe(
      "/control-plane/v1/spaces/personal-space/sessions/conversation/attachments",
    );
    expect(post.headers.get("content-type")).toContain("multipart/form-data");
    expect(post.headers.get("idempotency-key")).toBeTruthy();
    expect(latest.hasReadyAttachments).toBe(false);
    expect(latest.hasUploadingAttachments).toBe(true);
    documents = [document()];
    await refresh();
    expect(latest.attachments).toHaveLength(1);
    expect(latest.attachments[0].status).toBe("ingesting");
    documents = [document(true, "succeeded")];
    await refresh();
    expect(latest.hasReadyAttachments).toBe(true);
    expect(latest.hasUploadingAttachments).toBe(false);
    expect(managerImportsSnapshot()).toEqual([]);
    expect(fetcher.mock.calls.every(([r]) => !/knowledge-flow|\/teams\//.test(r.url))).toBe(true);
  });
  it.each(["succeeded", "failed"] as const)(
    "does not wait forever or mark a %s non-ready document usable",
    async (status) => {
      documents = [document(false, status)];
      await render();
      await refresh();
      expect(latest.attachments[0].status).toBe("error");
      expect(latest.hasUploadingAttachments).toBe(false);
      expect(latest.hasReadyAttachments).toBe(false);
    },
  );
  it("rehydrates running and completed documents from the server after remount", async () => {
    documents = [document()];
    await render();
    await refresh();
    await act(async () => root.unmount());
    root = createRoot(container);
    await render();
    await refresh();
    expect(latest.hasUploadingAttachments).toBe(true);
    documents = [document(true, "succeeded")];
    await refresh();
    await act(async () => root.unmount());
    root = createRoot(container);
    await render();
    await refresh();
    expect(latest.attachments).toHaveLength(1);
    expect(latest.hasReadyAttachments).toBe(true);
  });
  it.each(["processing_active", "network"])("retains the document when deletion fails: %s", async (failure) => {
    documents = [document(true, "succeeded")];
    await render();
    await refresh();
    fetcher.mockImplementation(async (r) => {
      if (r.method === "DELETE") {
        if (failure === "network") throw new TypeError("offline");
        return reply({ code: failure }, 409);
      }
      return reply(documents);
    });
    await act(async () => {
      await latest.deletePersistedAttachment("doc");
    });
    expect(latest.attachments).toHaveLength(1);
    expect(notify).toHaveBeenCalled();
  });
  it("removes a document after accepted deletion even while physical purge continues", async () => {
    documents = [document(true, "succeeded")];
    await render();
    await refresh();
    fetcher.mockImplementation(async (r) => {
      if (r.method === "DELETE") {
        documents = [];
        return reply({ status: "pending", id: "deletion" }, 202);
      }
      return reply(documents);
    });
    await act(async () => {
      await latest.deletePersistedAttachment("doc");
    });
    await refresh();
    expect(latest.attachments).toEqual([]);
  });
  it("ignores a late upload in the current conversation after navigation", async () => {
    let finish!: (response: Response) => void;
    fetcher.mockImplementation(async (r) =>
      r.method === "POST"
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : reply([]),
    );
    await render();
    let upload!: Promise<void>;
    await act(async () => {
      upload = latest.addFiles([file()], "drop");
    });
    const post = fetcher.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    await render("other");
    await refresh();
    await act(async () => {
      finish(reply(receipt(post.headers.get("Idempotency-Key")!)));
      await upload;
    });
    expect(latest.attachments).toEqual([]);
    await render("conversation");
    expect(latest.attachments[0].status).toBe("ingesting");
  });
  it("does not send or fetch attachments when disabled", async () => {
    await render("conversation", false);
    await act(async () => {
      await latest.addFiles([file()], "paste");
    });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("keeps files readable but neither uploads nor blocks sending when attachments=false", async () => {
    documents = [document()];
    await render("conversation", true, false);
    await refresh();
    await act(async () => {
      await latest.addFiles([file()], "picker");
    });
    expect(latest.persistedAttachments).toHaveLength(1);
    expect(latest.hasUploadingAttachments).toBe(false);
    expect(fetcher.mock.calls.every(([request]) => request.method === "GET")).toBe(true);
  });
  it("ignores an old actor's late upload response", async () => {
    let finish!: (response: Response) => void;
    fetcher.mockImplementation(async (r) =>
      r.method === "POST"
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : reply([]),
    );
    await render();
    let uploading!: Promise<void>;
    await act(async () => {
      uploading = latest.addFiles([file()], "picker");
    });
    const post = fetcher.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    identity.actor = crypto.randomUUID();
    await render();
    await act(async () => {
      finish(reply(receipt(post.headers.get("Idempotency-Key")!)));
      await uploading;
    });
    expect(latest.attachments).toEqual([]);
    expect(notify).not.toHaveBeenCalled();
  });
});
