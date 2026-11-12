import { configureStore } from "@reduxjs/toolkit";
import { describe, expect, it, vi } from "vitest";
import type { store as appStore } from "../../../../common/store";

const h = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../../../../common/capabilityBaseQuery", () => ({
  createCapabilityBaseQuery: () => h.request,
}));

import { pptBuilderCapabilityApi, type PlatformTemplateResponse } from "./api/pptBuilderCapabilityOpenApi";
import { updatePlatformCache } from "./updatePlatformCache";

describe("updatePlatformCache", () => {
  it("keeps a mutation response when an older platform poll finishes later", async () => {
    let finishOldRequest!: (value: { data: PlatformTemplateResponse }) => void;
    const oldRequest = new Promise<{ data: PlatformTemplateResponse }>((resolve) => {
      finishOldRequest = resolve;
    });
    let oldRequestSettled!: () => void;
    const settled = new Promise<void>((resolve) => {
      oldRequestSettled = resolve;
    });
    h.request.mockReset().mockImplementation(async () => {
      const result = await oldRequest;
      oldRequestSettled();
      return result;
    });
    const testStore = configureStore({
      reducer: { [pptBuilderCapabilityApi.reducerPath]: pptBuilderCapabilityApi.reducer },
      middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(pptBuilderCapabilityApi.middleware),
    });

    const first = testStore.dispatch(pptBuilderCapabilityApi.endpoints.getPptBuilderPlatform.initiate());
    await vi.waitFor(() => expect(h.request).toHaveBeenCalledTimes(1));
    const next: PlatformTemplateResponse = {
      analysis: null,
      replacement: {
        status: "pending",
        template_sha256: "new-sha",
        labelling_key: "rules",
        analysis_version: 1,
        current: false,
        updated_at: "now",
      },
    };
    updatePlatformCache(testStore.dispatch as typeof appStore.dispatch, next);
    await vi.waitFor(() =>
      expect(pptBuilderCapabilityApi.endpoints.getPptBuilderPlatform.select()(testStore.getState()).data).toEqual(next),
    );

    finishOldRequest({ data: { analysis: null, replacement: null } });
    await settled;
    await first;
    expect(pptBuilderCapabilityApi.endpoints.getPptBuilderPlatform.select()(testStore.getState()).data).toEqual(next);
  });
});
