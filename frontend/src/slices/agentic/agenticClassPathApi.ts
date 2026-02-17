import { agenticApi as api } from "./agenticOpenApi";

export const agenticClassPathApi = api.injectEndpoints({
  endpoints: (build) => ({
    listDeclaredAgentClassPaths: build.query<string[], void>({
      query: () => ({ url: `/agentic/v1/agents/class-paths` }),
    }),
  }),
  overrideExisting: false,
});

export const {
  useListDeclaredAgentClassPathsQuery,
  useLazyListDeclaredAgentClassPathsQuery,
} = agenticClassPathApi;
