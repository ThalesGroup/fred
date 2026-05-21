// common/dynamicBaseQuery.ts
// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import type { BaseQueryFn } from "@reduxjs/toolkit/query";
import { FetchArgs, fetchBaseQuery, FetchBaseQueryError } from "@reduxjs/toolkit/query/react";
import { KeyCloakService } from "../security/KeycloakService";

const RETRY_DELAY_MS = 2000;

/**
 * Returns true when RTK Query preserved an original HTTP status on the fetch error.
 * Use this before reading `error.originalStatus` in retry conditions.
 */
const hasOriginalStatus = (error: FetchBaseQueryError): error is FetchBaseQueryError & { originalStatus: number } => {
  return "originalStatus" in error && typeof error.originalStatus === "number";
};

/**
 * Returns true for transient backend errors that should be retried.
 * We currently retry `502` and `503`.
 */
const isRetryableBackendError = (error: FetchBaseQueryError): boolean => {
  return (
    error.status === 502 ||
    error.status === 503 ||
    (hasOriginalStatus(error) && (error.originalStatus === 502 || error.originalStatus === 503))
  );
};

const wait = (ms: number, signal?: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Request aborted", "AbortError"));
      return;
    }

    const timeout = window.setTimeout(resolve, ms);

    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(new DOMException("Request aborted", "AbortError"));
      },
      { once: true },
    );
  });

export const createDynamicBaseQuery = (): BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> => {
  const raw = fetchBaseQuery({
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
    const requestArgs = normalizeArgs(args);

    // 1) Proactively ensure token is still valid before making the request.
    await KeyCloakService.ensureFreshToken(30);

    // 2) First attempt
    let result = await raw(requestArgs, api, extraOptions);

    // Retry briefly when the backend is saturated or temporarily has no ready pod.
    while (result.error && isRetryableBackendError(result.error) && !api.signal.aborted) {
      try {
        await wait(RETRY_DELAY_MS, api.signal);
        result = await raw(requestArgs, api, extraOptions);
      } catch {
        break;
      }
    }

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
