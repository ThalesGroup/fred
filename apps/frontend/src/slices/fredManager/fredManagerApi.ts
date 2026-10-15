// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

export const fredManagerApi = createApi({
  reducerPath: "fredManagerApi",
  baseQuery: createDynamicBaseQuery(),
  endpoints: () => ({}),
});
