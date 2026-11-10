// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
import { useCallback } from "react";
import { useDispatch, useStore } from "react-redux";
import type { ThunkAction, ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";

import type { AppState } from "../../../../common/store";

/** Dispatches generated-client endpoints with initiate, as the signed-in admin. */
export type ApiDispatch = ThunkDispatch<unknown, unknown, UnknownAction>;

export function useApiDispatch(): ApiDispatch {
  return useDispatch<ApiDispatch>();
}

/** A one-shot read: never served from cache, never kept subscribed. */
export const FRESH = { subscribe: false, forceRefetch: true } as const;

type ReadResult<T> = { isLoading: boolean; isSuccess: boolean; data?: T; error?: unknown };
type ReadRequest<T> = PromiseLike<ReadResult<T>> & { unsubscribe: () => void };
interface ReadEndpoint<Arg, Result> {
  initiate: (
    arg: Arg,
    options: { forceRefetch: true },
  ) => ThunkAction<ReadRequest<Result>, AppState, unknown, UnknownAction>;
  select: (arg: Arg) => (state: AppState) => ReadResult<Result>;
}

/** One-shot reads keep their subscription through any concurrent invalidation refresh. */
export function useApiRead(dispatch: ApiDispatch) {
  const store = useStore<AppState>();
  return useCallback(
    async <Arg, Result>(endpoint: ReadEndpoint<Arg, Result>, arg: Arg): Promise<Result> => {
      const request = dispatch(endpoint.initiate(arg, { forceRefetch: true }));
      try {
        let result = await request;
        // RTK may already have started a refresh when its first promise selects the cache.
        // Observe that request's completion without dispatching another read.
        if (result.isLoading)
          result = await new Promise<ReadResult<Result>>((resolve) => {
            const check = () => {
              const current = endpoint.select(arg)(store.getState());
              if (!current.isLoading) {
                unsubscribe();
                resolve(current);
              }
            };
            const unsubscribe = store.subscribe(check);
            check();
          });
        if (result.error) throw result.error;
        if (!result.isSuccess || result.data === undefined)
          throw new Error("The query was invalidated before its result could be read");
        return result.data;
      } finally {
        request.unsubscribe();
      }
    },
    [dispatch, store],
  );
}

export type ApiRead = ReturnType<typeof useApiRead>;
