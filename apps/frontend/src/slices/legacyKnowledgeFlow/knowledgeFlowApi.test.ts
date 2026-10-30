// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from "@reduxjs/toolkit";
import { expect, it, vi } from "vitest";
import { knowledgeFlowApi } from "./knowledgeFlowApi";
import "./knowledgeFlowOpenApi";

it("refuses preserved Swift requests outside preview mode without using fetch", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  const api = knowledgeFlowApi.injectEndpoints({
    endpoints: (build) => ({
      probe: build.query<unknown, void>({ query: () => "/knowledge-flow/v1/documents/audit" }),
    }),
  });
  const store = configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
  });
  const request = store.dispatch(api.endpoints.probe.initiate());
  try {
    expect((await request).error).toMatchObject({ status: "CUSTOM_ERROR" });
    expect(fetch).not.toHaveBeenCalled();
  } finally {
    request.unsubscribe();
    store.dispatch(api.util.resetApiState());
    fetch.mockRestore();
  }
});
