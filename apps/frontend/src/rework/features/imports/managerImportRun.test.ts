// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import type { UploadReceipt } from "../../../slices/fredManager/fredManagerOpenApi";
const identity = vi.hoisted(() => ({ uid: "", expired: false }));
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetSessionIdentity: () => JSON.stringify(["fixture", identity.uid]),
    GetUserId: () => (identity.expired ? null : identity.uid),
    GetTokenParsed: () => ({ iss: "fixture" }),
    GetToken: () => identity.uid,
    ensureFreshToken: vi.fn().mockResolvedValue(true),
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
import { enhancedFredManagerApi as api } from "../../../slices/fredManager/fredManagerApiEnhancements";
import {
  runManagerImport,
  managerImportsSnapshot,
  managerFileHeld,
  retryManagerImport,
  dismissManagerImport,
  refreshManagerImports,
  cancelManagerImport,
} from "./managerImportRun";

const NativeRequest = globalThis.Request;
const reply = (value: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function receipt(key: string, status: UploadReceipt["status"] = "stored"): UploadReceipt {
  return {
    request_key: key,
    space_id: "space",
    folder_id: "folder",
    name: "original.txt",
    size: 5,
    sha256: "a".repeat(64),
    mime: "text/plain",
    status,
    created_at: new Date().toISOString(),
    completed_at: status === "pending" ? null : new Date().toISOString(),
    document_id: status === "stored" ? key : null,
    error_code: status === "failed" ? "storage_unavailable" : null,
    acknowledged_at: null,
    successor_key: null,
  };
}
let fetcher: ReturnType<typeof vi.fn<(request: Request) => Promise<Response>>>;
let store: ReturnType<typeof makeStore>;
const invalidated: unknown[] = [];
function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) =>
      defaults().concat(api.middleware, () => (next) => (action) => {
        if (api.util.invalidateTags.match(action)) invalidated.push(action.payload);
        return next(action);
      }),
  });
}
beforeEach(() => {
  identity.uid = crypto.randomUUID();
  identity.expired = false;
  localStorage.clear();
  invalidated.length = 0;
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
  managerImportsSnapshot();
});
afterEach(() => {
  store.dispatch(api.util.resetApiState());
  vi.unstubAllGlobals();
});
const selection = () => [{ file: new File(["bytes"], "original.txt"), folderId: "folder" }];

it("resolves a lost upload acknowledgement through its receipt without a second POST", async () => {
  let key = "";
  fetcher.mockImplementation(async (request) => {
    if (request.method === "POST") {
      key = request.headers.get("idempotency-key")!;
      throw new TypeError("connection reset");
    }
    return reply(receipt(key));
  });
  await runManagerImport(store.dispatch, "space", selection());
  expect(fetcher.mock.calls.filter(([r]) => r.method === "POST")).toHaveLength(1);
  expect(managerImportsSnapshot()).toEqual([expect.objectContaining({ key, phase: "stored" })]);
  expect(managerFileHeld(key)).toBe(false);
});

it("retries a terminal failure with one successor and durably acknowledges dismissal", async () => {
  let predecessor = "";
  let successor = "";
  let acknowledged = false;
  fetcher.mockImplementation(async (request) => {
    if (request.method === "POST") {
      const key = request.headers.get("idempotency-key")!;
      if (!predecessor) {
        predecessor = key;
        return reply({ code: "storage_unavailable" }, 503);
      }
      successor = key;
      expect(new URL(request.url).searchParams.get("retry_of")).toBe(predecessor);
      expect(key).not.toBe(predecessor);
      return reply(receipt(key));
    }
    if (request.method === "PUT") {
      acknowledged = true;
      return reply(null, 204);
    }
    return reply(
      receipt(
        request.url.includes(predecessor) ? predecessor : successor,
        request.url.includes(predecessor) ? "failed" : "stored",
      ),
    );
  });
  await runManagerImport(store.dispatch, "space", selection());
  expect(managerImportsSnapshot()[0].phase).toBe("failed");
  await Promise.all([retryManagerImport(store.dispatch, predecessor), retryManagerImport(store.dispatch, predecessor)]);
  expect(fetcher.mock.calls.filter(([r]) => r.method === "POST")).toHaveLength(2);
  expect(managerImportsSnapshot()).toEqual([expect.objectContaining({ key: successor, phase: "stored" })]);
  await dismissManagerImport(store.dispatch, successor);
  expect(acknowledged).toBe(true);
  expect(managerImportsSnapshot()).toEqual([]);
});

it("bounds uploads across batches, preserves queued cancellation and isolates an account change", async () => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  fetcher.mockImplementation(async (request) => {
    if (request.method !== "POST") return reply([]);
    await held;
    return reply(receipt(request.headers.get("idempotency-key")!));
  });
  const first = runManagerImport(store.dispatch, "space", [
    ...selection(),
    ...selection(),
    ...selection(),
    ...selection(),
  ]);
  const second = runManagerImport(store.dispatch, "space", selection());
  await vi.waitFor(() => expect(fetcher.mock.calls.filter(([r]) => r.method === "POST")).toHaveLength(3));
  await refreshManagerImports(store.dispatch, "space");
  const queued = managerImportsSnapshot().filter((e) => e.phase === "queued");
  expect(queued).toHaveLength(2);
  expect(cancelManagerImport(queued[0].key)).toBe(true);
  identity.uid = "other-account";
  expect(managerImportsSnapshot()).toEqual([]);
  release();
  await Promise.all([first, second]);
  expect(fetcher.mock.calls.filter(([r]) => r.method === "POST")).toHaveLength(3);
  expect(managerImportsSnapshot()).toEqual([]);
});

it("invalidates directory and quota when polling discovers publication after reload", async () => {
  const key = crypto.randomUUID();
  let status: UploadReceipt["status"] = "pending";
  fetcher.mockImplementation(async () => reply([receipt(key, status)]));
  await refreshManagerImports(store.dispatch, "space");
  expect(managerImportsSnapshot()[0].phase).toBe("uncertain");
  expect(invalidated).toHaveLength(0);
  status = "stored";
  await refreshManagerImports(store.dispatch, "space");
  expect(managerImportsSnapshot()[0].phase).toBe("stored");
  expect(invalidated).toEqual([["Documents"]]);
  await refreshManagerImports(store.dispatch, "space");
  expect(invalidated).toHaveLength(1);
});

it("recovers older server receipts after browser storage loss using a bounded cursor scan", async () => {
  const latest = Array.from({ length: 200 }, () => receipt(crypto.randomUUID(), "failed"));
  const old = receipt(crypto.randomUUID(), "failed");
  fetcher.mockImplementation(async (request) =>
    reply(new URL(request.url).searchParams.has("before") ? [old] : latest),
  );
  await refreshManagerImports(store.dispatch, "space");
  await refreshManagerImports(store.dispatch, "space");
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(managerImportsSnapshot()).toHaveLength(201);
  expect(managerImportsSnapshot().find((e) => e.key === old.request_key)?.phase).toBe("failed");
});

it("keeps retry bytes and queue identity while the same session renews an expired bearer", async () => {
  let key = "";
  fetcher.mockImplementation(async (request) => {
    if (request.method === "POST") {
      key = request.headers.get("idempotency-key")!;
      return reply({ code: "storage_unavailable" }, 503);
    }
    return reply(receipt(key, "failed"));
  });
  await runManagerImport(store.dispatch, "space", selection());
  identity.expired = true;
  expect(managerImportsSnapshot()[0].key).toBe(key);
  expect(managerFileHeld(key)).toBe(true);
  identity.expired = false;
  expect(managerFileHeld(key)).toBe(true);
  expect(managerImportsSnapshot()[0].phase).toBe("failed");
});

it("keeps active processing visible across stale acknowledged receipts and older revisions", async () => {
  const key = crypto.randomUUID();
  const processing = {
    id: "attempt",
    document_id: key,
    profile: "fast" as const,
    status: "running" as const,
    stage: "indexing" as const,
    revision: 5,
    created_at: new Date().toISOString(),
    completed_at: null,
    error_code: null,
    retry_of: null,
    chunks: 0,
    vectors: 0,
    rows: null,
  };
  let current = {
    ...receipt(key),
    processing_profile: "fast" as const,
    processing,
    acknowledged_at: new Date().toISOString(),
  };
  fetcher.mockImplementation(async () => reply([current]));
  await refreshManagerImports(store.dispatch, "space");
  expect(managerImportsSnapshot()[0].receipt?.processing?.stage).toBe("indexing");
  current = { ...current, processing: { ...processing, status: "failed" as never, revision: 3 } };
  await refreshManagerImports(store.dispatch, "space");
  expect(managerImportsSnapshot()[0].receipt?.processing?.revision).toBe(5);
});

it("submits the selected profile and retries failed processing from the retained original without a File", async () => {
  let stored: UploadReceipt | undefined;
  const operation = crypto.randomUUID();
  fetcher.mockImplementation(async (request) => {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname.endsWith("/documents")) {
      expect(url.searchParams.get("profile")).toBe("rich");
      stored = {
        ...receipt(request.headers.get("idempotency-key")!),
        processing_profile: "rich",
        processing: {
          id: operation,
          document_id: "document",
          profile: "rich",
          status: "failed",
          stage: "indexing",
          revision: 3,
          created_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          error_code: "indexing_failed",
          retry_of: null,
          chunks: 0,
          vectors: 0,
          rows: null,
        },
      };
      return reply(stored);
    }
    if (request.method === "POST") {
      expect(url.pathname.endsWith("/processing")).toBe(true);
      expect(await request.json()).toEqual({ profile: "rich", retry_of: operation });
      stored = {
        ...stored!,
        processing: {
          ...stored!.processing!,
          id: "retry",
          status: "pending",
          revision: 1,
          created_at: new Date(Date.now() + 1).toISOString(),
        },
      };
      return reply(stored.processing);
    }
    return reply(stored);
  });
  await runManagerImport(store.dispatch, "space", selection(), "rich");
  const key = managerImportsSnapshot()[0].key;
  expect(managerFileHeld(key)).toBe(false);
  await retryManagerImport(store.dispatch, key);
  expect(managerImportsSnapshot()[0].receipt?.processing?.id).toBe("retry");
  expect(fetcher.mock.calls.filter(([r]) => r.method === "POST")).toHaveLength(2);
});

it("binds ambiguous processing retry keys to their predecessor after a recovered successor also fails", async () => {
  const key = crypto.randomUUID();
  let stored: UploadReceipt = {
    ...receipt(key),
    processing: {
      id: "A",
      document_id: key,
      profile: "fast",
      status: "failed",
      stage: "extraction",
      revision: 4,
      created_at: "2026-10-19T10:00:00Z",
      completed_at: "2026-10-19T10:01:00Z",
      error_code: "worker_failed",
      retry_of: null,
      chunks: 0,
      vectors: 0,
      rows: null,
    },
  };
  const keys: string[] = [];
  fetcher.mockImplementation(async (request) => {
    if (request.method === "POST") {
      keys.push(request.headers.get("idempotency-key")!);
      const body = await request.json();
      expect(body.retry_of).toBe(keys.length === 1 ? "A" : "B");
      if (keys.length === 1) {
        stored = {
          ...stored,
          processing: { ...stored.processing!, id: "B", retry_of: "A", created_at: "2026-10-19T10:02:00Z" },
        };
        throw new TypeError("lost accepted response");
      }
      stored = {
        ...stored,
        processing: {
          ...stored.processing!,
          id: "C",
          retry_of: "B",
          status: "pending",
          created_at: "2026-10-19T10:03:00Z",
        },
      };
      return reply(stored.processing);
    }
    return reply(request.url.includes("/document-uploads/") ? stored : [stored]);
  });
  await refreshManagerImports(store.dispatch, "space");
  await expect(retryManagerImport(store.dispatch, key)).rejects.toBeDefined();
  await refreshManagerImports(store.dispatch, "space");
  await retryManagerImport(store.dispatch, key);
  expect(keys).toHaveLength(2);
  expect(keys[0]).not.toBe(keys[1]);
  expect(managerImportsSnapshot()[0].receipt?.processing?.id).toBe("C");
});
