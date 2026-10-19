// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createApi, defaultSerializeQueryArgs } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

import { KeyCloakService } from "../../security/KeycloakService";

export const fredManagerApi = createApi({
  reducerPath: "fredManagerApi",
  baseQuery: createDynamicBaseQuery(),
  serializeQueryArgs: (args) =>
    defaultSerializeQueryArgs({
      ...args,
      queryArgs: {
        actor: KeyCloakService.GetSessionIdentity?.() ?? null,
        args: args.queryArgs,
      },
    }),
  endpoints: () => ({}),
});
