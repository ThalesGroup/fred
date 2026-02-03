# Knowledge Flow API - RTK Query

This directory contains the RTK Query API configuration for the Knowledge Flow backend.

## Files

- **knowledgeFlowApi.ts** - Base API configuration with tag types
- **knowledgeFlowOpenApi.ts** - Auto-generated endpoints from OpenAPI spec (DO NOT EDIT MANUALLY)
- **knowledgeFlowApiEnhancements.ts** - Manual enhancements for cache invalidation

## Auto-generated Endpoints

The `knowledgeFlowOpenApi.ts` file is automatically generated from the backend OpenAPI spec:

```bash
make update-knowledge-flow-api  # From frontend directory
```

**⚠️ Never edit knowledgeFlowOpenApi.ts manually** - your changes will be overwritten on next generation.

## Adding Cache Tags

To add cache invalidation for auto-generated endpoints:

1. Add the tag type to `knowledgeFlowApi.ts`:
   ```typescript
   tagTypes: ["BenchRun", "Team", "YourNewTag"]
   ```

2. Enhance endpoints in `knowledgeFlowApiEnhancements.ts`:

   **For a single resource:**
   ```typescript
   getYourResource: {
     providesTags: (_, __, arg) => [{ type: "YourNewTag", id: arg.id }],
   },
   updateYourResource: {
     invalidatesTags: (_, __, arg) => [{ type: "YourNewTag", id: arg.id }],
   },
   ```

   **For a list resource:**
   ```typescript
   listYourResources: {
     providesTags: (result) =>
       result
         ? [...result.map((item) => ({ type: "YourNewTag", id: item.id })), { type: "YourNewTag", id: "LIST" }]
         : [{ type: "YourNewTag", id: "LIST" }],
   },
   ```

   When updating a resource, invalidate both the specific item and the list:
   ```typescript
   updateYourResource: {
     invalidatesTags: (_, __, arg) => [
       { type: "YourNewTag", id: arg.id },
       { type: "YourNewTag", id: "LIST" },
     ],
   },
   ```

3. Re-export the hooks you need:
   ```typescript
   export const {
     useListYourResourcesQuery,
     useGetYourResourceQuery,
     useUpdateYourResourceMutation,
   } = enhancedKnowledgeFlowApi;
   ```

4. Import from the enhancements file in your components:
   ```typescript
   import { useGetYourResourceQuery } from "../../slices/knowledgeFlow/knowledgeFlowApiEnhancements";
   ```

## How It Works

- **providesTags**: Tags the cached data from a query
- **invalidatesTags**: When a mutation completes, RTK Query automatically refetches any queries with matching tags
- This eliminates manual `refetch()` calls and keeps data in sync across components
