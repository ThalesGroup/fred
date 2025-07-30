import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const agenticApi = createApi({
  baseQuery: createDynamicBaseQuery({ backend: "api" }),
  // todo: in future, use reverse proxy to avoid dynamic base query:
  // baseQuery: fetchBaseQuery({ baseUrl: "/" }),
  endpoints: () => ({}),
  reducerPath: "agenticApi",
});
