// common/dynamicBaseQuery.ts
// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import { fetchBaseQuery, FetchArgs, FetchBaseQueryError } from "@reduxjs/toolkit/query/react";
import type { BaseQueryFn } from "@reduxjs/toolkit/query";
import { getConfig } from "./config";
import { KeyCloakService } from "../security/KeycloakService";

interface DynamicBaseQueryOptions {
  backend: "api" | "knowledge";
}

export const createDynamicBaseQuery = (
  options: DynamicBaseQueryOptions,
): BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> => {
  // We resolve the baseUrl lazily (at call time), just like your original code.
  const pickBaseUrl = () => {
    if (options.backend === "knowledge") {
      return import.meta.env.VITE_BACKEND_URL_KNOWLEDGE || getConfig().backend_url_knowledge;
    }
    return import.meta.env.VITE_BACKEND_URL_API || getConfig().backend_url_api;
  };

  // A “raw” base query that only sets headers; token freshness is handled outside (so we can await it)
  const makeRaw = (baseUrl: string) =>
    fetchBaseQuery({
      baseUrl,
      prepareHeaders: (headers) => {
        const token = KeyCloakService.GetToken();
        if (token) headers.set("Authorization", `Bearer ${token}`);
        return headers;
      },
    });

  const normalizeArgs = (args: string | FetchArgs): FetchArgs => {
    if (typeof args === "string") {
      return { url: args, cache: "no-store" };
    }
    return { ...args, cache: "no-store" };
  };

  return async (args, api, extraOptions) => {
    const baseUrl = pickBaseUrl();
    if (!baseUrl) throw new Error(`Backend URL missing for ${options.backend} backend.`);
    const raw = makeRaw(baseUrl);
    const requestArgs = normalizeArgs(args);

    // 1) Proactively ensure token is still valid before making the request.
    await KeyCloakService.ensureFreshToken(30);

    // 2) First attempt
    let result = await raw(requestArgs, api, extraOptions);

    // 3) If unauthorized, try ONE refresh + retry
    if (result.error && result.error.status === 401) {
      const ok = await KeyCloakService.ensureFreshToken(0);
      if (ok) {
        result = await raw(requestArgs, api, extraOptions);
      }
      // 4) Still unauthorized? Clean logout to avoid a broken UI state.
      if (result.error && result.error.status === 401) {
        KeyCloakService.CallLogout();
      }
    }

    return result;
  };
};
