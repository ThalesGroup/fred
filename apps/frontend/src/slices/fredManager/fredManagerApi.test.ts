// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { afterEach, describe, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import type { ImportBlueprintApiResponse, MeApiResponse, MySpacesApiResponse } from "./fredManagerOpenApi";

vi.mock("../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "operator-token",
    ensureFreshToken: vi.fn().mockResolvedValue(true),
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));

import { KeyCloakService } from "../../security/KeycloakService";

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

  it("allows an omitted ingestion body through the typed enhancement", async () => {
    const { store, fetch } = setup(null);
    fetch.mockImplementationOnce(async () => new Response(null, { status: 202 }));
    await store.dispatch(api.endpoints.ingestDocument.initiate({ id: "document-id" })).unwrap();
    const request = fetch.mock.calls[0][0];
    expect(request.url).toBe("http://localhost/fred-manager/v1/documents/document-id/ingest");
    expect(await request.text()).toBe("");
    expect(request.headers.has("content-type")).toBe(false);
    store.dispatch(api.util.resetApiState());
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
    const me: MeApiResponse = { user_id: "alice", username: "Alice", platform_roles: ["platform_admin"] };
    const { store, fetch } = setup(me);
    const actor = store.dispatch(api.endpoints.me.initiate());
    expect(await actor.unwrap()).toEqual(me);
    expect(fetch.mock.calls[0][0].url).toBe("http://localhost/fred-manager/v1/me");
    const spaces: MySpacesApiResponse = [
      {
        id: "org-id",
        kind: "organization",
        name: "Demo",
        parent_id: null,
        personal_owner: null,
        path: ["org-id"],
        roles: ["admin", "analyst"],
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
