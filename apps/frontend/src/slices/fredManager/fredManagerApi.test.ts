// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { afterEach, describe, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import type { ImportBlueprintApiResponse, MeApiResponse, MySpacesApiResponse } from "./fredManagerOpenApi";

vi.mock("../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "operator-token",
    GetUserId: vi.fn(() => "operator" as string | null),
    GetSessionIdentity: vi.fn(() => "fixture/operator"),
    ensureFreshToken: vi.fn().mockResolvedValue(true),
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));

import { KeyCloakService } from "../../security/KeycloakService";

import * as managerApi from "./fredManagerApiEnhancements";
import { enhancedFredManagerApi as api } from "./fredManagerApiEnhancements";

const NativeRequest = globalThis.Request;
const report: ImportBlueprintApiResponse = {
  identities_resolved: 15,
  identities_created: 15,
  spaces_reconciled: 4,
  grants_acknowledged: 44,
};

function setup(reply: unknown, status = 200) {
  // Browser Request resolves same-origin paths; Node's implementation needs a base.
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  const fetch = vi.fn(
    async (_request: Request) =>
      new Response(JSON.stringify(reply), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetch);
  const store = configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) => defaults().concat(api.middleware),
  });
  return { store, fetch };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("generated fred-manager client", () => {
  it("sends the binary ZIP as one multipart field with the operator bearer and returns the completed report", async () => {
    const { store, fetch } = setup(report);
    const bytes = new Uint8Array([0x50, 0x4b, 3, 4, 0, 255]);
    const result = await store
      .dispatch(
        api.endpoints.importBlueprint.initiate({
          provisioningUpload: { file: new File([bytes], "demo.zip", { type: "application/zip" }) },
        }),
      )
      .unwrap();
    expect(result).toEqual(report);
    expect(fetch).toHaveBeenCalledTimes(1);
    const request = fetch.mock.calls[0][0];
    expect(request.url).toBe("http://localhost/fred-manager/v1/import-export/import");
    expect(request.method).toBe("POST");
    expect(request.headers.get("authorization")).toBe("Bearer operator-token");
    expect(request.headers.get("content-type")).toMatch(/^multipart\/form-data; boundary=/);
    const form = await request.formData();
    expect([...form.keys()]).toEqual(["file"]);
    const file = form.get("file") as File;
    expect(file.name).toBe("demo.zip");
    expect(new Uint8Array(await file.arrayBuffer())).toEqual(bytes);
    store.dispatch(api.util.resetApiState());
  });

  it("preserves a failed import's safe detail without inventing success or retrying", async () => {
    const { store, fetch } = setup({ detail: "not_yet_supported" }, 422);
    const result = await store.dispatch(
      api.endpoints.importBlueprint.initiate({
        provisioningUpload: { file: new File(["legacy"], "old.zip") },
      }),
    );
    expect(result).toEqual({ error: { status: 422, data: { detail: "not_yet_supported" } } });
    expect(fetch).toHaveBeenCalledTimes(1);
    store.dispatch(api.util.resetApiState());
  });

  it("does not refresh and replay an import that expires after partial effects", async () => {
    const detail =
      "provisioning identities failed: invalid or expired operator bearer; identities_created=2; correct the cause and replay";
    const { store, fetch } = setup({ detail }, 401);
    const result = await store.dispatch(
      api.endpoints.importBlueprint.initiate({
        provisioningUpload: { file: new File(["zip"], "demo.zip") },
      }),
    );
    expect(result).toEqual({ error: { status: 401, data: { detail } } });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
    expect(KeyCloakService.CallLogout).not.toHaveBeenCalled();
    store.dispatch(api.util.resetApiState());
  });

  it("does not replay personal-space creation on 401", async () => {
    const { store, fetch } = setup(null);
    fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
    const result = await store.dispatch(
      api.endpoints.createPersonalSpace.initiate({ createPersonalSpace: { organization_id: "org" } }),
    );
    expect(result).toEqual({ error: { status: 401, data: { detail: "expired" } } });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
    store.dispatch(api.util.resetApiState());
  });

  it("exposes no document metadata routes or provisional document mutations", () => {
    for (const operation of [
      "createDocument",
      "renameDocument",
      "deleteDocument",
      "ingestDocument",
      "getDocument",
      "listDocuments",
    ]) {
      expect(api.endpoints).not.toHaveProperty(operation);
    }
    expect(managerApi).not.toHaveProperty("useIngestDocumentMutation");
    expect(api.endpoints).toHaveProperty("entries");
  });

  it("retains the standard token retry for ordinary queries", async () => {
    const { store, fetch } = setup({ user_id: "u", username: "U", platform_roles: [] });
    fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
    const query = store.dispatch(api.endpoints.me.initiate());
    await query.unwrap();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledWith(0);
    query.unsubscribe();
    store.dispatch(api.util.resetApiState());
  });

  it("reads manager authority and flat nullable spaces through generated query contracts", async () => {
    const me: MeApiResponse = { user_id: "alice", username: "Alice", platform_roles: ["platform_owner"] };
    const { store, fetch } = setup(me);
    const actor = store.dispatch(api.endpoints.me.initiate());
    expect(await actor.unwrap()).toEqual(me);
    expect(fetch.mock.calls[0][0].url).toBe("http://localhost/fred-manager/v1/me");
    const spaces: MySpacesApiResponse = [
      {
        id: "org-id",
        kind: "organization",
        organization_id: "org",
        name: "Demo",
        parent_id: null,
        personal_owner: null,
        path: ["org-id"],
        roles: ["admin", "analyst"],
        inherited_roles: [],
      },
    ];
    fetch.mockImplementationOnce(
      async () =>
        new Response(JSON.stringify(spaces), {
          headers: { "Content-Type": "application/json" },
        }),
    );
    const query = store.dispatch(api.endpoints.mySpaces.initiate());
    expect(await query.unwrap()).toEqual(spaces);
    expect(fetch.mock.calls[1][0].url).toBe("http://localhost/fred-manager/v1/me/spaces");
    actor.unsubscribe();
    query.unsubscribe();
    store.dispatch(api.util.resetApiState());
  });
});

it("allows same-account token refresh and refuses a late response after account change", async () => {
  const { store, fetch } = setup({ user_id: "operator", username: "Operator", platform_roles: [] });
  vi.mocked(KeyCloakService.GetUserId).mockReturnValueOnce(null);
  const same = store.dispatch(api.endpoints.me.initiate(undefined, { subscribe: false, forceRefetch: true }));
  expect((await same.unwrap()).user_id).toBe("operator");
  expect(fetch).toHaveBeenCalledTimes(1);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  fetch.mockImplementationOnce(async () => {
    await held;
    return new Response(JSON.stringify({ user_id: "operator" }));
  });
  const late = store.dispatch(api.endpoints.me.initiate(undefined, { subscribe: false, forceRefetch: true }));
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  vi.mocked(KeyCloakService.GetSessionIdentity).mockReturnValue("fixture/other");
  release();
  expect((await late).error).toEqual({ status: "CUSTOM_ERROR", error: "Account changed during request" });
  fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ user_id: "other" })));
  const other = await store.dispatch(api.endpoints.me.initiate(undefined, { subscribe: false })).unwrap();
  expect(other.user_id).toBe("other");
  expect(fetch).toHaveBeenCalledTimes(3);
  vi.mocked(KeyCloakService.GetSessionIdentity).mockReturnValue("fixture/operator");
  store.dispatch(api.util.resetApiState());
});
