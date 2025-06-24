// Copyright Thales 2025
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

import { combineReducers, configureStore, createReducer, isFulfilled, isPending, isRejected } from "@reduxjs/toolkit";
import { apiSlice } from "../frugalit/slices/api.tsx";
import { chatApiSlice } from "../slices/chatApi"; // ✅ Import your chatApi slice
import { documentApiSlice } from "../slices/documentApi.tsx";
import { chatProfileApiSlice } from "../slices/chatProfileApi.tsx";
import { monitoringApiMiddleware, monitoringApiReducer } from "../slices/monitoringApi.tsx";
import { knowledgeContextApiSlice } from "../slices/knowledgeContextApi.tsx";

// Optional: Logging middleware for debugging
const loggingMiddleware = () => (next) => (action) => {
  if (action?.payload) {
    const { start, end, cluster, namespace, region, precision } = action.payload;
    if (!start || !end || !cluster || !namespace || !region || !precision) {
      // console.warn("Undefined value detected:", action); // Uncomment if needed
    }
  }
  return next(action);
};

// Combine reducers
const combinedReducer = combineReducers({
  pendingCount: createReducer(0, (builder) =>
    builder
      .addMatcher(isPending, (state) => state + 1)
      .addMatcher(isFulfilled, (state) => (state ? state - 1 : state))
      .addMatcher(isRejected, (state) => (state ? state - 1 : state)),
  ),
  ignoredRefreshesCount: createReducer(0, (builder) =>
    builder
      .addCase("incrementIgnoredRefresh", (state) => state + 1)
      .addCase("decrementIgnoredRefresh", (state) => state - 1),
  ),
  api: apiSlice.reducer,
  documentApi: documentApiSlice.reducer,
  chatApi: chatApiSlice.reducer,
  chatProfileApi: chatProfileApiSlice.reducer,
  monitoringApi: monitoringApiReducer,
  knowledgeContextApi: knowledgeContextApiSlice.reducer
});

// Configure store
export const store = configureStore({
  reducer: combinedReducer,
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(
      apiSlice.middleware,
      documentApiSlice.middleware,
      chatApiSlice.middleware,
      monitoringApiMiddleware,
      chatProfileApiSlice.middleware,
      loggingMiddleware,
      knowledgeContextApiSlice.middleware
    ),
  devTools: true,
});

// Export types
export type AppState = ReturnType<typeof store.getState>;
