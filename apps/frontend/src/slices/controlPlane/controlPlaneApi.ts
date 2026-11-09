// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createApi, defaultSerializeQueryArgs } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";
import { managerFetch } from "./managerFetch";

import { KeyCloakService } from "../../security/KeycloakService";

/** Bind original RTK arguments to their session, including deferred cache cleanup.
 * The generated endpoint sends only its declared fields. Fresh subscriptions get
 * fresh arguments; callers that reuse ordinary args keep the default behavior. */
export function sessionQueryArgs<const Args extends object>(args: Args): Args {
  return { ...args, __cpSessionIdentity: KeyCloakService.GetSessionIdentity?.() ?? null };
}

function scopedQueryArgs(args: unknown) {
  if (args && typeof args === "object" && "__cpSessionIdentity" in args) {
    const { __cpSessionIdentity: actor, ...queryArgs } = args;
    return { actor, args: queryArgs };
  }
  return { actor: KeyCloakService.GetSessionIdentity?.() ?? null, args };
}

export const controlPlaneApi = createApi({
  reducerPath: "controlPlaneApi",
  baseQuery: createDynamicBaseQuery(managerFetch),
  serializeQueryArgs: (args) =>
    defaultSerializeQueryArgs({
      ...args,
      queryArgs: scopedQueryArgs(args.queryArgs),
    }),
  endpoints: () => ({}),
});
