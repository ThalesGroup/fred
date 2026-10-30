// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { createApi, type BaseQueryFn, type FetchArgs, type FetchBaseQueryError } from "@reduxjs/toolkit/query/react";

const baseQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (args, api) => {
  if (
    import.meta.env.DEV &&
    import.meta.env.MODE === "swift-preview" &&
    (api.getState() as { swiftPreview?: boolean }).swiftPreview === true
  ) {
    const { previewQuery } = await import("../../dev/swiftPreview/fixtures");
    return previewQuery(args);
  }
  return { error: { status: "CUSTOM_ERROR", error: "This Swift feature is not connected to Weaver." } };
};

/** Frozen Swift contract. Never forward its v1 requests to a Weaver backend. */
export const knowledgeFlowApi = createApi({
  reducerPath: "legacyKnowledgeFlowApi",
  baseQuery,
  tagTypes: ["Team", "TeamMember"],
  endpoints: () => ({}),
});
