// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createApi, defaultSerializeQueryArgs } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";
import { managerFetch } from "./managerFetch";

import { KeyCloakService } from "../../security/KeycloakService";

export const controlPlaneApi = createApi({
  reducerPath: "controlPlaneApi",
  baseQuery: createDynamicBaseQuery(managerFetch),
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
