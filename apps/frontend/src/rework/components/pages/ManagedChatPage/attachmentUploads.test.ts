// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from "@reduxjs/toolkit";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import type { UploadReceipt } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  attachmentUploadScope,
  uploadAttachments,
  refreshAttachmentUploads,
  retryAttachmentUpload,
} from "./attachmentUploads";
const identity = vi.hoisted(() => ({ actor: "" }));
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
const NativeRequest = globalThis.Request;
function makeStore() {
  return configureStore({ reducer: { [api.reducerPath]: api.reducer }, middleware: (d) => d().concat(api.middleware) });
}
let store: ReturnType<typeof makeStore>;
let fetcher: ReturnType<typeof vi.fn<(request: Request) => Promise<Response>>>;
const reply = (value: unknown, status = 200, headers = {}) =>
  new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json", ...headers } });
const file = () => new File(["bytes"], "a.csv", { type: "text/csv" });
const scope = () => attachmentUploadScope(identity.actor, "personal", "session");
function receipt(key: string, status: UploadReceipt["status"] = "stored"): UploadReceipt {
  return {
    request_key: key,
    status,
    document_id: status === "stored" ? "doc" : null,
    space_id: "personal",
    session_id: "session",
    folder_id: null,
    name: "a.csv",
    mime: "text/csv",
    size: 5,
    sha256: "a".repeat(64),
    created_at: "2026-10-29T10:00:00Z",
  };
}
beforeEach(() => {
  identity.actor = crypto.randomUUID();
  localStorage.clear();
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  fetcher = vi.fn(async () => reply({ code: "not_found" }, 404));
  vi.stubGlobal("fetch", fetcher);
  store = makeStore();
});
afterEach(() => {
  store.dispatch(api.util.resetApiState());
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("recovers a lost response from the receipt without another POST", async () => {
  let key = "";
  fetcher.mockImplementation(async (r) => {
    if (r.method === "POST") {
      key = r.headers.get("Idempotency-Key")!;
      throw new TypeError("lost response");
    }
    return reply(receipt(key));
  });
  await uploadAttachments(store.dispatch, scope(), [file()]);
  expect(scope().entries[0]).toMatchObject({ key, phase: "stored" });
  expect(fetcher.mock.calls.filter(([r]) => r.method === "POST")).toHaveLength(1);
});
it("keeps an unknown upload through missing, pending and stored receipts without resending", async () => {
  let key = "";
  let checks = 0;
  fetcher.mockImplementation(async (request) => {
    if (request.method === "POST") {
      key = request.headers.get("Idempotency-Key")!;
      throw new TypeError("network outcome unknown");
    }
    checks += 1;
    return checks === 1 ? reply({}, 404) : reply(receipt(key, checks === 2 ? "pending" : "stored"));
  });
  await uploadAttachments(store.dispatch, scope(), [file()]);
  expect(scope().entries).toEqual([expect.objectContaining({ key, phase: "uncertain" })]);
  await refreshAttachmentUploads(store.dispatch, scope());
  expect(scope().entries[0]).toMatchObject({ key, phase: "uncertain", receipt: { status: "pending" } });
  await refreshAttachmentUploads(store.dispatch, scope());
  expect(scope().entries).toEqual([expect.objectContaining({ key, phase: "stored" })]);
  expect(fetcher.mock.calls.filter(([request]) => request.method === "POST")).toHaveLength(1);
  expect(fetcher.mock.calls.filter(([request]) => request.method === "GET")).toHaveLength(3);
});
it("replays the same key after a confirmed missing receipt and explicit retry", async () => {
  await uploadAttachments(store.dispatch, scope(), [file()]);
  const key = scope().entries[0].key;
  fetcher.mockImplementation(async (r) =>
    r.method === "GET" ? reply({}, 404) : reply(receipt(r.headers.get("Idempotency-Key")!)),
  );
  await retryAttachmentUpload(store.dispatch, scope(), key, file());
  const posts = fetcher.mock.calls.map(([r]) => r).filter((r) => r.method === "POST");
  expect(posts.map((r) => r.headers.get("Idempotency-Key"))).toEqual([key, key]);
});
it("uses retry_of only for an explicitly retried failed upload", async () => {
  let failed = "";
  fetcher.mockImplementation(async (r) => {
    if (r.method === "POST") {
      const key = r.headers.get("Idempotency-Key")!;
      if (!failed) {
        failed = key;
        return reply({ code: "upload_failed" }, 409);
      }
      return reply(receipt(key));
    }
    return reply(receipt(failed, "failed"));
  });
  await uploadAttachments(store.dispatch, scope(), [file()]);
  expect(scope().entries[0].phase).toBe("failed");
  await retryAttachmentUpload(store.dispatch, scope(), failed, file());
  const post = fetcher.mock.calls.map(([r]) => r).filter((r) => r.method === "POST")[1];
  expect(post.headers.get("Idempotency-Key")).not.toBe(failed);
  expect(new URL(post.url).searchParams.get("retry_of")).toBe(failed);
});
it("honours Retry-After for receipt checks and user retries", async () => {
  const now = Date.now();
  vi.spyOn(Date, "now").mockReturnValue(now);
  fetcher.mockResolvedValue(reply({ code: "upload_in_progress" }, 409, { "Retry-After": "20" }));
  await uploadAttachments(store.dispatch, scope(), [file()]);
  const key = scope().entries[0].key;
  await refreshAttachmentUploads(store.dispatch, scope());
  await retryAttachmentUpload(store.dispatch, scope(), key, file());
  expect(fetcher).toHaveBeenCalledTimes(1);
  vi.spyOn(Date, "now").mockReturnValue(now + 20_001);
  fetcher.mockResolvedValue(reply(receipt(key, "pending")));
  await refreshAttachmentUploads(store.dispatch, scope());
  expect(scope().entries[0].phase).toBe("uncertain");
});
it.each([
  ["name_conflict", 409],
  ["quota_exceeded", 422],
  ["conversation_files_exceeded", 422],
  ["conversation_bytes_exceeded", 422],
  ["file_too_large", 413],
] as const)("keeps explicit rejection %s terminal without polling or resending", async (code, status) => {
  fetcher.mockImplementation(async (r) => (r.method === "POST" ? reply({ code }, status) : reply({}, 404)));
  await uploadAttachments(store.dispatch, scope(), [file()]);
  expect(scope().entries[0]).toMatchObject({ phase: "failed", error: code });
  await refreshAttachmentUploads(store.dispatch, scope());
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it("follows retry_superseded to its successor without sending new bytes", async () => {
  fetcher.mockImplementation(async (r) => {
    if (r.method === "POST") return reply({ code: "retry_superseded" }, 409);
    const key = new URL(r.url).pathname.split("/").pop()!;
    return reply(key === "successor" ? receipt(key) : { ...receipt(key, "failed"), successor_key: "successor" });
  });
  await uploadAttachments(store.dispatch, scope(), [file()]);
  expect(scope().entries[0].receipt?.request_key).toBe("successor");
  expect(scope().entries[0].phase).toBe("stored");
  expect(fetcher.mock.calls.filter(([r]) => r.method === "POST")).toHaveLength(1);
});
it("rehydrates only the actor, space and conversation hints, without File bytes", async () => {
  const saved = [{ key: "lost", name: "a.csv", size: 5, mime: "text/csv", phase: "uploading" }];
  localStorage.setItem(
    `fred.conversation.uploads:${JSON.stringify([identity.actor, "personal", "session"])}`,
    JSON.stringify(saved),
  );
  expect(scope().entries[0].phase).toBe("uncertain");
  expect(attachmentUploadScope(identity.actor, "other", "session").entries).toEqual([]);
  expect(attachmentUploadScope("other-actor", "personal", "session").entries).toEqual([]);
  expect(attachmentUploadScope(identity.actor, "personal", "other").entries).toEqual([]);
  fetcher.mockResolvedValue(reply(receipt("lost")));
  await refreshAttachmentUploads(store.dispatch, scope());
  expect(scope().entries[0].phase).toBe("stored");
  expect(fetcher.mock.calls.every(([r]) => r.method === "GET")).toBe(true);
});
it("never routes a processing retry through drive", async () => {
  fetcher.mockImplementation(async (r) => reply(receipt(r.headers.get("Idempotency-Key") ?? scope().entries[0].key)));
  await uploadAttachments(store.dispatch, scope(), [file()]);
  fetcher.mockClear();
  await retryAttachmentUpload(store.dispatch, scope(), scope().entries[0].key, file());
  expect(fetcher.mock.calls.every(([r]) => r.method === "GET" && r.url.includes("/document-uploads/"))).toBe(true);
});
