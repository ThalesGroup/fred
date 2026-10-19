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
