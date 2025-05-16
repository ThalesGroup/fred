import { combineReducers, configureStore, createReducer, isFulfilled, isPending, isRejected } from "@reduxjs/toolkit";
import { apiSlice } from "../slices/api.tsx";
import { chatApiSlice } from "../slices/chatApi"; // ✅ Import your chatApi slice
import { documentApiSlice } from "../slices/documentApi.tsx";
import { agentContextApiSlice } from "../slices/agentContextApi.tsx";

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
  pendingCount: createReducer(0, builder =>
    builder
      .addMatcher(isPending, state => state + 1)
      .addMatcher(isFulfilled, state => state ? state - 1 : state)
      .addMatcher(isRejected, state => state ? state - 1 : state)
  ),
  ignoredRefreshesCount: createReducer(0, builder =>
    builder
      .addCase("incrementIgnoredRefresh", state => state + 1)
      .addCase("decrementIgnoredRefresh", state => state - 1)
  ),
  api: apiSlice.reducer,
  documentApi: documentApiSlice.reducer,
  chatApi: chatApiSlice.reducer,
  agentContextApi: agentContextApiSlice.reducer 
});

// Configure store
export const store = configureStore({
  reducer: combinedReducer,
  middleware: getDefaultMiddleware =>
    getDefaultMiddleware()
      .concat(
        apiSlice.middleware,
        documentApiSlice.middleware,
        chatApiSlice.middleware,
        agentContextApiSlice.middleware,
        loggingMiddleware
      ),
  devTools: true,
});

// Export types
export type AppState = ReturnType<typeof store.getState>;
