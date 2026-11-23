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

// Base RTK Query slice for the word_template capability's OWN router.
//
// The generated `wordTemplateCapabilityOpenApi.ts` injects endpoints into this
// slice (session state, .docx download, PDF preview). Its base query
// resolves the capability's ingress-relative base URL from
// `capabilityRoutingSlice`, so calls reach the pod directly (no proxy).
// This slice's reducer + middleware are registered once in `common/store.tsx`.

import { createApi } from "@reduxjs/toolkit/query/react";
import { createCapabilityBaseQuery } from "../../../../../common/capabilityBaseQuery";

export const CAPABILITY_ID = "word_template";

export const wordTemplateCapabilityApi = createApi({
  reducerPath: "wordTemplateCapabilityApi",
  baseQuery: createCapabilityBaseQuery(CAPABILITY_ID),
  refetchOnFocus: false,
  refetchOnReconnect: false,
  keepUnusedDataFor: 0,
  endpoints: () => ({}),
});
