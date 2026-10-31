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

// Base RTK Query slice for the ppt_builder capability's OWN router: the
// stateless template analysis and the built-in template inventory. The generated
// `pptBuilderCapabilityOpenApi.ts` injects the endpoints; the base query
// resolves the capability's base URL from `capabilityRoutingSlice`. Registered
// once in `common/store.tsx`.

import { createApi } from "@reduxjs/toolkit/query/react";
import { createCapabilityBaseQuery } from "../../../../../common/capabilityBaseQuery";

export const CAPABILITY_ID = "ppt_builder";

export const pptBuilderCapabilityApi = createApi({
  reducerPath: "pptBuilderCapabilityApi",
  baseQuery: createCapabilityBaseQuery(CAPABILITY_ID),
  refetchOnFocus: false,
  refetchOnReconnect: false,
  keepUnusedDataFor: 0,
  endpoints: () => ({}),
});
