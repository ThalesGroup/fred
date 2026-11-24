// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { FetchArgs, FetchBaseQueryMeta, FetchBaseQueryError, QueryReturnValue } from "@reduxjs/toolkit/query";
import {
  controlPlaneApi,
  type PromptSummary,
  type HomeAgent,
  type OrganizationHomeCandidatesApiArg,
  type MarketplaceEntrySummary,
  type MarketplaceEntriesApiArg,
  type ProposalSummary,
  type MarketplaceProposalsApiArg,
  type Marketplace,
  type ProposalSpace,
  type MarketplaceProposalSpacesApiArg,
  type MarketplacesApiArg,
  type ListPromptsApiArg,
  type ListPromptCategoriesApiArg,
  type ManagedAgentInstanceSummary,
  type PromptCategory,
  type OrganizationDetail,
  type Allowed,
  type SpaceCheck,
} from "./controlPlaneOpenApi";

import { KeyCloakService } from "../../security/KeycloakService";

async function readAvatar(response: Response) {
  if (!response.ok) return response.json();
  if (response.status === 204) return "";
  const blob = await response.blob();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

// All avatar owners use the same authenticated binary transport and serializable cache.
function avatarQuery<Arg>(query: (arg: Arg) => string | FetchArgs) {
  return (arg: Arg): FetchArgs => {
    const request = query(arg);
    return { ...(typeof request === "string" ? { url: request } : request), responseHandler: readAvatar };
  };
}

type CatalogDefinition = typeof controlPlaneApi.endpoints.listPrompts.Types.QueryDefinition;
type CatalogPage<Item> = { items: Item[]; next_cursor: string | null };

// One bounded traversal for space resource catalogs. No partial success.
function catalogQuery<Item, Args extends { after?: string } = ListPromptsApiArg>(
  query: (args: Args) => ReturnType<NonNullable<CatalogDefinition["query"]>>,
  key: (item: Item) => string,
): (
  args: Args,
  api: Parameters<NonNullable<CatalogDefinition["queryFn"]>>[1],
  extra: Parameters<NonNullable<CatalogDefinition["queryFn"]>>[2],
  baseQuery: Parameters<NonNullable<CatalogDefinition["queryFn"]>>[3],
) => Promise<QueryReturnValue<CatalogPage<Item>, FetchBaseQueryError>> {
  return async (args, api, _extra, baseQuery) => {
    const items = new Map<string, Item>();
    let after = args.after;
    const deadline = Date.now() + 60_000;
    // Bound both work and memory, including a catalog growing during traversal.
    // Reaching the bound is an error, never a supposedly complete catalog.
    for (let page = 0; page < 100; page++) {
      if (api.signal.aborted) return { error: { status: "CUSTOM_ERROR", error: "aborted" } };
      const remaining = deadline - Date.now();
      if (remaining <= 0) return { error: { status: "TIMEOUT_ERROR", error: "resource_catalog_timeout" } };
      const request = query({ ...args, after });
      // One budget for the page, including token refresh and its HTTP retry.
      const controller = new AbortController();
      let timer: ReturnType<typeof setTimeout> | undefined;
      const timeout = new Promise<Awaited<ReturnType<typeof baseQuery>>>((resolve) => {
        timer = setTimeout(
          () => {
            controller.abort(new DOMException("resource_catalog_timeout", "TimeoutError"));
            resolve({ error: { status: "TIMEOUT_ERROR", error: "resource_catalog_timeout" } });
          },
          Math.min(15_000, remaining),
        );
      });
      try {
        const result = await Promise.race([
          baseQuery({
            ...(typeof request === "string" ? { url: request } : request),
            signal: AbortSignal.any([api.signal, controller.signal]),
          }),
          timeout,
        ]);
        if (Date.now() >= deadline) return { error: { status: "TIMEOUT_ERROR", error: "resource_catalog_timeout" } };
        if (result.error) return { error: result.error };
        const data = result.data as CatalogPage<Item>;
        for (const prompt of data.items) items.set(key(prompt), prompt);
        if (data.next_cursor === null) return { data: { items: [...items.values()], next_cursor: null } };
        if (after !== undefined && data.next_cursor <= after) break;
        after = data.next_cursor;
      } finally {
        clearTimeout(timer);
      }
    }
    return { error: { status: "CUSTOM_ERROR", error: "resource_catalog_incomplete" } };
  };
}

const wikiTags = (_result: unknown, _error: unknown, { spaceId }: { spaceId: string }) => [
  { type: "Wiki" as const, id: spaceId },
];

const marketplaceTags = (_result: unknown, _error: unknown, { marketplaceSpaceId }: { marketplaceSpaceId: string }) => [
  { type: "MarketplaceContent" as const, id: marketplaceSpaceId },
];

type MarketplaceMutationContext = Pick<
  Parameters<
    NonNullable<(typeof controlPlaneApi.endpoints.decideMarketplaceProposal.Types.MutationDefinition)["onQueryStarted"]>
  >[1],
  "dispatch" | "getState"
> & { queryFulfilled: Promise<unknown> };

// RTK's delayed tag invalidation can wait behind unrelated long-running requests.
// Refresh the visible catalogue after the command, and after any older read finishes.
async function refreshMarketplace(
  { marketplaceSpaceId }: { marketplaceSpaceId: string },
  { dispatch, getState, queryFulfilled }: MarketplaceMutationContext,
) {
  const actor = KeyCloakService.GetSessionIdentity();
  try {
    await queryFulfilled;
  } catch {
    /* A lost response can still have committed. */
  }
  if (actor !== KeyCloakService.GetSessionIdentity()) return;
  const state = getState() as Parameters<typeof controlPlaneApi.util.selectCachedArgsForQuery>[0];
  await Promise.all([
    ...controlPlaneApi.util
      .selectCachedArgsForQuery(state, "marketplaceEntries")
      .filter(
        (args) =>
          args.marketplaceSpaceId === marketplaceSpaceId &&
          (!("__cpSessionIdentity" in args) || args.__cpSessionIdentity === actor),
      )
      .map(async (args) => {
        await dispatch(controlPlaneApi.util.getRunningQueryThunk("marketplaceEntries", args));
        if (actor === KeyCloakService.GetSessionIdentity())
          await dispatch(
            controlPlaneApi.endpoints.marketplaceEntries.initiate(args, { subscribe: false, forceRefetch: true }),
          );
      }),
    ...controlPlaneApi.util
      .selectCachedArgsForQuery(state, "marketplaceProposals")
      .filter(
        (args) =>
          args.marketplaceSpaceId === marketplaceSpaceId &&
          (!("__cpSessionIdentity" in args) || args.__cpSessionIdentity === actor),
      )
      .map(async (args) => {
        await dispatch(controlPlaneApi.util.getRunningQueryThunk("marketplaceProposals", args));
        if (actor === KeyCloakService.GetSessionIdentity())
          await dispatch(
            controlPlaneApi.endpoints.marketplaceProposals.initiate(args, { subscribe: false, forceRefetch: true }),
          );
      }),
  ]);
}

function invalidateTraceConsentChange(_result: unknown, error: unknown, { sessionId }: { sessionId: string }) {
  const consent = { type: "ConversationTraceConsent" as const, id: sessionId };
  // The server may have committed the change before its response was lost.
  return error ? [consent] : [consent, "ConversationTraceCatalog" as const];
}

const mcpInvalidates = (_result: unknown, _error: unknown, { spaceId }: { spaceId: string }) =>
  [
    { type: "McpConnections", id: spaceId },
    { type: "OrganizationCapabilities", id: spaceId },
    { type: "OrganizationAgents", id: spaceId },
    "AgentTemplates",
    "SpaceCapabilityPolicies",
  ] as const;

// The generator types binary fields as Blob, but sends the enclosing object as
// JSON. Adapt only the transport; URL, method, arguments and result stay generated.
export const enhancedControlPlaneApi = controlPlaneApi.enhanceEndpoints({
  addTagTypes: [
    "ConversationTraceConsent",
    "ConversationTraceCatalog",
    "OrganizationHome",
    "Applications",
    "UserAvatar",
    "TeamAvatar",
    "TeamDirectory",
    "SpaceMembers",
    "MySpaces",
    "SpaceAccess",
    "Folders",
    "Documents",
    "DocumentUploads",
    "OrganizationAgents",
    "OrganizationCapabilities",
    "OrganizationModels",
    "OrganizationPrompts",
    "AgentInstances",
    "Prompts",
    "MarketplaceContent",
    "Skills",
    "Marketplaces",
    "PromptCategories",
    "AgentTemplates",
    "Sessions",
    "Attachments",
    "Wiki",
    "McpConnections",
    "SpaceCapabilityPolicies",
  ],
  endpoints: {
    getTraceConsent: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    setTraceConsent: {
      invalidatesTags: (_result, error, { sessionId }) =>
        error ? [] : [{ type: "ConversationTraceConsent", id: sessionId }, "ConversationTraceCatalog"],
    },
    revokeTraceConsent: {
      invalidatesTags: invalidateTraceConsentChange,
    },
    getTraceIncidentOffer: {
      keepUnusedDataFor: 30,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    shareTraceIncident: {
      invalidatesTags: invalidateTraceConsentChange,
    },
    listConversationTraces: {
      providesTags: ["ConversationTraceCatalog"],
    },
    deleteConversationTraces: {
      invalidatesTags: (_result, error, { deleteConversationTracesRequest }) =>
        error
          ? []
          : [
              "ConversationTraceCatalog",
              ...deleteConversationTracesRequest.session_ids.map((id) => ({
                type: "ConversationTraceConsent" as const,
                id,
              })),
            ],
    },
    flushConversationTraceCaptures: {
      invalidatesTags: (_result, error) => (error ? [] : ["ConversationTraceCatalog", "ConversationTraceConsent"]),
    },
    getConversationTrace: {
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    getConversationTraceHistory: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    getConversationTraceHttpEvidence: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    getConversationTraceSseFrame: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    getConversationTraceSseFramePage: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    getConversationTraceSseHeaders: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    getConversationTraceToolEvidence: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },
    getConversationTraceModelEvidence: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { sessionId }) => [{ type: "ConversationTraceConsent", id: sessionId }],
    },

    organizationResources: { keepUnusedDataFor: 0, providesTags: ["TeamDirectory"] },
    organizationHome: {
      providesTags: (_r, _e, { organizationId }) => [
        { type: "OrganizationHome", id: organizationId },
        "AgentInstances",
        "MySpaces",
        "OrganizationAgents",
      ],
      keepUnusedDataFor: 0,
    },
    organizationHomeSettings: {
      providesTags: (_r, _e, { organizationId }) => [
        { type: "OrganizationHome", id: organizationId },
        "AgentInstances",
        "MySpaces",
        "OrganizationAgents",
      ],
      keepUnusedDataFor: 0,
    },
    organizationHomeCandidates(endpoint) {
      const query = endpoint.query!;
      endpoint.query = undefined;
      endpoint.queryFn = catalogQuery<HomeAgent, OrganizationHomeCandidatesApiArg>(
        query,
        (agent) => agent.agent_instance_id,
      );
      endpoint.providesTags = ["AgentInstances", "MySpaces", "OrganizationAgents"];
      endpoint.keepUnusedDataFor = 0;
    },
    setOrganizationHome: {
      invalidatesTags: (_r, _e, { organizationId }) => [{ type: "OrganizationHome", id: organizationId }],
      extraOptions: { retryUnauthorized: false },
    },
    platformApplications: { providesTags: ["Applications"] },
    spaceApplications: { providesTags: ["Applications"], keepUnusedDataFor: 0 },
    createApplication: {
      invalidatesTags: ["Applications", "OrganizationCapabilities", "SpaceCapabilityPolicies"],
      extraOptions: { retryUnauthorized: false },
    },
    updateApplication: {
      invalidatesTags: ["Applications", "OrganizationCapabilities", "SpaceCapabilityPolicies"],
      extraOptions: { retryUnauthorized: false },
    },
    teamDocumentActivity(endpoint) {
      // A hung poll must not prevent reconnect convergence; retain no old pages
      // once their team/view is left. URL and contract remain generated.
      endpoint.keepUnusedDataFor = 0;
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        return { ...(typeof request === "string" ? { url: request } : request), timeout: 15_000 };
      };
    },
    getMyAvatar(endpoint) {
      endpoint.providesTags = ["UserAvatar"];
      endpoint.keepUnusedDataFor = 0;
      endpoint.query = avatarQuery(endpoint.query!);
    },
    getUserAvatar(endpoint) {
      endpoint.providesTags = ["UserAvatar"];
      endpoint.keepUnusedDataFor = 0;
      endpoint.query = avatarQuery(endpoint.query!);
    },
    putMyAvatar(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      endpoint.invalidatesTags = ["UserAvatar"];
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 120_000 };
      };
    },
    deleteMyAvatar: { invalidatesTags: ["UserAvatar"], extraOptions: { retryUnauthorized: false } },
    getTeamAvatar(endpoint) {
      endpoint.providesTags = (_result, _error, { id }) => [{ type: "TeamAvatar", id }];
      endpoint.keepUnusedDataFor = 0;
      endpoint.query = avatarQuery(endpoint.query!);
    },
    putTeamAvatar(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      endpoint.invalidatesTags = (_result, _error, { id }) => [{ type: "TeamAvatar", id }];
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 120_000 };
      };
    },
    deleteTeamAvatar: {
      invalidatesTags: (_result, _error, { id }) => [{ type: "TeamAvatar", id }],
      extraOptions: { retryUnauthorized: false },
    },
    spaceCapabilityPolicies: {
      providesTags: (_result, _error, { spaceId }) => [{ type: "SpaceCapabilityPolicies", id: spaceId }],
    },
    mcpConnections: { providesTags: (_result, _error, { spaceId }) => [{ type: "McpConnections", id: spaceId }] },
    createMcpConnection: {
      invalidatesTags: mcpInvalidates,
      extraOptions: { retryUnauthorized: false },
    },
    updateMcpConnection: {
      invalidatesTags: mcpInvalidates,
      extraOptions: { retryUnauthorized: false },
    },
    testMcpConnection: {
      invalidatesTags: mcpInvalidates,
      extraOptions: { retryUnauthorized: false },
    },
    publishMcpConnection: {
      invalidatesTags: mcpInvalidates,
      extraOptions: { retryUnauthorized: false },
    },
    wikiAvailability: { providesTags: ["Wiki", "OrganizationCapabilities", "AgentTemplates"] },
    replaceSpaceCapabilityPolicy: {
      invalidatesTags: ["Wiki", "Applications", "SpaceCapabilityPolicies"],
      extraOptions: { retryUnauthorized: false },
    },
    wikiPages: { providesTags: wikiTags },
    proposeWikiFile: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    wikiPage: { providesTags: wikiTags },
    wikiRules: { providesTags: wikiTags },
    wikiRevisions: { providesTags: wikiTags },
    wikiProposal: { providesTags: wikiTags, keepUnusedDataFor: 0 },
    createWikiPage: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    writeWikiPage: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    writeWikiRules: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    patchWikiPage: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    deleteWikiPage: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    restoreWikiRevision: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    submitWikiProposal: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    withdrawWikiProposal: { invalidatesTags: wikiTags, extraOptions: { retryUnauthorized: false } },
    organizationTeams: { providesTags: ["TeamDirectory"], keepUnusedDataFor: 0 },
    teamMetadata: { providesTags: ["TeamDirectory"], keepUnusedDataFor: 0 },
    joinTeam: {
      invalidatesTags: ["TeamDirectory", "MySpaces", "SpaceMembers", "SpaceAccess", "Marketplaces"],
      extraOptions: { retryUnauthorized: false },
    },
    mySpaces: { providesTags: ["MySpaces"] },
    teamJoinLink: { keepUnusedDataFor: 0, providesTags: (_r, _e, { id }) => [{ type: "SpaceMembers", id }] },
    createTeamJoinLink: {
      invalidatesTags: (_r, _e, { id }) => [{ type: "SpaceMembers", id }],
      extraOptions: { retryUnauthorized: false },
    },
    revokeTeamJoinLink: {
      invalidatesTags: (_r, _e, { id }) => [{ type: "SpaceMembers", id }],
      extraOptions: { retryUnauthorized: false },
    },
    previewTeamJoinLink: { keepUnusedDataFor: 0 },
    redeemTeamJoinLink: {
      invalidatesTags: ["MySpaces", "SpaceMembers", "SpaceAccess", "TeamDirectory"],
      extraOptions: { retryUnauthorized: false },
    },
    updateTeamParameters: {
      invalidatesTags: ["MySpaces", "TeamDirectory", "TeamAvatar"],
      extraOptions: { retryUnauthorized: false },
    },
    spaceMembers: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { id }) => [{ type: "SpaceMembers", id }],
    },
    spaceMemberCandidates: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { id }) => [{ type: "SpaceMembers", id }],
    },
    grant: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: [
        "SpaceMembers",
        "MySpaces",
        "SpaceAccess",
        "Marketplaces",
        "MarketplaceContent",
        "TeamAvatar",
        "TeamDirectory",
      ],
    },
    removeSpaceMember: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: [
        "SpaceMembers",
        "MySpaces",
        "SpaceAccess",
        "Marketplaces",
        "MarketplaceContent",
        "TeamAvatar",
        "TeamDirectory",
      ],
    },
    revoke: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: [
        "SpaceMembers",
        "MySpaces",
        "SpaceAccess",
        "Marketplaces",
        "MarketplaceContent",
        "TeamAvatar",
        "TeamDirectory",
      ],
    },
    // All three consumers need the complete catalog. Keep its pages in one RTK
    // result, never a component store. A failed page publishes no partial list.
    marketplaces(endpoint) {
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = ["Marketplaces"];
      endpoint.queryFn = catalogQuery<Marketplace, MarketplacesApiArg>(
        endpoint.query!,
        (marketplace) => marketplace.space_id,
      );
      Object.assign(endpoint, { query: undefined });
    },
    marketplaceProposalSpaces(endpoint) {
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = ["Marketplaces", "SpaceAccess"];
      endpoint.queryFn = catalogQuery<ProposalSpace, MarketplaceProposalSpacesApiArg>(
        endpoint.query!,
        (space) => space.id,
      );
      Object.assign(endpoint, { query: undefined });
    },
    marketplaceEntries(endpoint) {
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = marketplaceTags;
      endpoint.queryFn = catalogQuery<MarketplaceEntrySummary, MarketplaceEntriesApiArg>(
        endpoint.query!,
        (entry) => entry.entry_id,
      );
      Object.assign(endpoint, { query: undefined });
    },
    marketplaceProposals(endpoint) {
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = marketplaceTags;
      endpoint.queryFn = catalogQuery<ProposalSummary, MarketplaceProposalsApiArg>(
        endpoint.query!,
        (proposal) => proposal.proposal_id,
      );
      Object.assign(endpoint, { query: undefined });
    },
    marketplaceEntry: { keepUnusedDataFor: 0, providesTags: marketplaceTags },
    marketplaceProposal: { keepUnusedDataFor: 0, providesTags: marketplaceTags },
    submitMarketplaceProposal: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: marketplaceTags,
      onQueryStarted: refreshMarketplace,
    },
    decideMarketplaceProposal: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: marketplaceTags,
      onQueryStarted: refreshMarketplace,
    },
    cancelMarketplaceProposal: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: marketplaceTags,
      onQueryStarted: refreshMarketplace,
    },
    withdrawMarketplaceEntry: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: marketplaceTags,
      onQueryStarted: refreshMarketplace,
    },
    installMarketplaceEntry: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, _error, { installRequest }) => [
        { type: "Prompts", id: installRequest.destination_space_id },
        { type: "Skills", id: installRequest.destination_space_id },
        { type: "AgentInstances", id: installRequest.destination_space_id },
      ],
    },
    marketplaceInstallation: { keepUnusedDataFor: 0, providesTags: ["Prompts", "Skills", "AgentInstances"] },
    skillScope: { providesTags: ["Skills"] },
    listSkills: { providesTags: (_result, _error, { spaceId }) => [{ type: "Skills", id: spaceId }] },
    getSkill: { providesTags: (_result, _error, { spaceId }) => [{ type: "Skills", id: spaceId }] },
    putSkill: { invalidatesTags: (_result, _error, { spaceId }) => [{ type: "Skills", id: spaceId }, "TeamDirectory"] },
    deleteSkill: {
      invalidatesTags: (_result, _error, { spaceId }) => [{ type: "Skills", id: spaceId }, "TeamDirectory"],
    },
    createSkill: { invalidatesTags: (_result, _error, { spaceId }) => [{ type: "Skills", id: spaceId }] },
    listPrompts(endpoint) {
      const query = endpoint.query!;
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = (_result, _error, { spaceId }) => [{ type: "Prompts", id: spaceId }];
      endpoint.queryFn = catalogQuery<PromptSummary, ListPromptsApiArg>(query, (prompt) => prompt.prompt_id);
      // RTK must use queryFn; every page still uses the generated request builder.
      Object.assign(endpoint, { query: undefined });
      endpoint.onCacheEntryAdded = async (args, { cacheEntryRemoved, dispatch, getCacheEntry }) => {
        await cacheEntryRemoved;
        const request = dispatch(controlPlaneApi.util.getRunningQueryThunk("listPrompts", args));
        if (getCacheEntry().isUninitialized) request?.abort();
      };
    },
    listPromptCategories(endpoint) {
      const query = catalogQuery<PromptCategory, ListPromptCategoriesApiArg>(
        endpoint.query!,
        (category) => category.id,
      );
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = (_result, _error, { spaceId }) => [{ type: "PromptCategories", id: spaceId }];
      endpoint.queryFn = async (...args) => {
        const result = await query(...args);
        result.data?.items.sort((a, b) => a.name.localeCompare(b.name));
        return result;
      };
      Object.assign(endpoint, { query: undefined });
      endpoint.onCacheEntryAdded = async (args, { cacheEntryRemoved, dispatch, getCacheEntry }) => {
        await cacheEntryRemoved;
        const request = dispatch(controlPlaneApi.util.getRunningQueryThunk("listPromptCategories", args));
        if (getCacheEntry().isUninitialized) request?.abort();
      };
    },
    createPromptCategory: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, _error, { spaceId }) => [{ type: "PromptCategories", id: spaceId }],
    },
    renamePromptCategory: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, _error, { spaceId }) => [{ type: "PromptCategories", id: spaceId }],
    },
    deletePromptCategory: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, _error, { spaceId }) => [
        { type: "PromptCategories", id: spaceId },
        { type: "Prompts", id: spaceId },
      ],
    },
    getPrompt(endpoint) {
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        return { ...(typeof request === "string" ? { url: request } : request), timeout: 30_000 };
      };
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = (_result, _error, { spaceId, promptId }) => [
        { type: "Prompts", id: `${spaceId}:${promptId}` },
      ];
    },
    addPromptFavorite: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, promptId }) =>
        error
          ? []
          : [
              { type: "Prompts", id: spaceId },
              { type: "Prompts", id: `${spaceId}:${promptId}` },
            ],
    },
    removePromptFavorite: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, promptId }) =>
        error
          ? []
          : [
              { type: "Prompts", id: spaceId },
              { type: "Prompts", id: `${spaceId}:${promptId}` },
            ],
    },
    createPrompt: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId }) => (error ? [] : [{ type: "Prompts", id: spaceId }]),
    },
    updatePrompt: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, promptId }) =>
        error
          ? []
          : ["TeamDirectory", { type: "Prompts", id: spaceId }, { type: "Prompts", id: `${spaceId}:${promptId}` }],
    },
    deletePrompt: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, promptId }) =>
        error
          ? []
          : ["TeamDirectory", { type: "Prompts", id: spaceId }, { type: "Prompts", id: `${spaceId}:${promptId}` }],
    },
    listAttachments: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { spaceId, sessionId }) => [
        { type: "Attachments", id: `${spaceId}:${sessionId}` },
      ],
    },
    uploadPowerpointTemplate(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 120_000 };
      };
    },
    uploadWordTemplate(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 120_000 };
      };
    },
    uploadAttachment(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 2_000_000 };
      };
      endpoint.transformErrorResponse = (error, meta) => ({
        ...error,
        retryAfter: (meta as FetchBaseQueryMeta | undefined)?.response?.headers.get("Retry-After"),
      });
    },
    deleteAttachment: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, sessionId }) =>
        error ? [] : [{ type: "Attachments", id: `${spaceId}:${sessionId}` }],
    },
    listSessions: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { spaceId }) => [{ type: "Sessions", id: spaceId }],
    },
    getSession: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { spaceId, sessionId }) => [{ type: "Sessions", id: `${spaceId}:${sessionId}` }],
    },
    createSession: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId }) => (error ? [] : [{ type: "Sessions", id: spaceId }]),
    },
    updateSession: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, sessionId }) =>
        error
          ? []
          : [
              { type: "Sessions", id: spaceId },
              { type: "Sessions", id: `${spaceId}:${sessionId}` },
            ],
    },
    deleteSession: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, sessionId }) =>
        error
          ? []
          : [
              { type: "Sessions", id: spaceId },
              { type: "Wiki", id: spaceId },
              { type: "ConversationTraceConsent", id: sessionId },
              "ConversationTraceCatalog",
            ],
    },

    listAgentInstances(endpoint) {
      endpoint.keepUnusedDataFor = 0;
      endpoint.providesTags = (_result, _error, { spaceId }) => [{ type: "AgentInstances", id: spaceId }];
      endpoint.queryFn = catalogQuery<ManagedAgentInstanceSummary>(
        endpoint.query!,
        (instance) => instance.agent_instance_id,
      );
      Object.assign(endpoint, { query: undefined });
      endpoint.onCacheEntryAdded = async (args, { cacheEntryRemoved, dispatch, getCacheEntry }) => {
        await cacheEntryRemoved;
        const request = dispatch(controlPlaneApi.util.getRunningQueryThunk("listAgentInstances", args));
        if (getCacheEntry().isUninitialized) request?.abort();
      };
    },
    getAgentInstance: {
      providesTags: (_result, _error, { spaceId, agentInstanceId }) => [
        { type: "AgentInstances", id: `${spaceId}:${agentInstanceId}` },
      ],
    },
    spaceAgentTemplates: {
      providesTags: (_result, _error, { spaceId }) => [{ type: "AgentTemplates", id: spaceId }],
    },
    createAgentInstance: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId }) => (error ? [] : [{ type: "AgentInstances", id: spaceId }]),
    },
    updateAgentInstance: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, agentInstanceId }) =>
        error
          ? []
          : [
              "TeamDirectory",
              { type: "AgentInstances", id: spaceId },
              { type: "AgentInstances", id: `${spaceId}:${agentInstanceId}` },
            ],
    },
    deleteAgentInstance: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, agentInstanceId }) =>
        error
          ? []
          : [
              "TeamDirectory",
              { type: "AgentInstances", id: spaceId },
              { type: "AgentInstances", id: `${spaceId}:${agentInstanceId}` },
            ],
    },
    getCommonPromptSettings: {
      providesTags: (_result, _error, { organizationId }) => [{ type: "OrganizationPrompts", id: organizationId }],
    },
    putCommonPromptSettings: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { organizationId }) =>
        error ? [] : [{ type: "OrganizationPrompts", id: organizationId }],
    },
    getCreationAssistantSettings: {
      providesTags: (_result, _error, { organizationId }) => [
        { type: "OrganizationPrompts", id: organizationId },
        { type: "OrganizationModels", id: organizationId },
      ],
    },
    patchCreationAssistantSettings: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { organizationId }) =>
        error ? [] : [{ type: "OrganizationPrompts", id: organizationId }],
    },
    resetCreationAssistantPrompt: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { organizationId }) =>
        error ? [] : [{ type: "OrganizationPrompts", id: organizationId }],
    },
    draftAgent: { extraOptions: { retryUnauthorized: false } },
    organizationModels: {
      providesTags: (_result, _error, { organizationId }) => [{ type: "OrganizationModels", id: organizationId }],
    },
    organizationModelPolicy: {
      providesTags: (_result, _error, { organizationId }) => [{ type: "OrganizationModels", id: organizationId }],
    },
    replaceOrganizationModelPolicy: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, _error, { organizationId }) => [{ type: "OrganizationModels", id: organizationId }],
    },
    refreshModelSource: {
      extraOptions: { retryUnauthorized: false },
      // A failed discovery also updates its observation; inventories share sources.
      invalidatesTags: ["OrganizationModels"],
    },
    organizationAgents: {
      providesTags: (_result, _error, arg) => [{ type: "OrganizationAgents", id: arg.organizationId }],
    },
    setOrganizationAgentDefault: {
      invalidatesTags: (_result, _error, arg) => [{ type: "OrganizationAgents", id: arg.organizationId }],
      extraOptions: { retryUnauthorized: false },
    },
    organizationCapabilities: {
      providesTags: (_result, _error, arg) => [{ type: "OrganizationCapabilities", id: arg.organizationId }],
    },
    refreshOrganizationCapabilities: {
      extraOptions: { retryUnauthorized: false },
      // A failed refresh also records the pod as unavailable; pods are shared by organizations.
      invalidatesTags: ["OrganizationCapabilities"],
    },
    setOrganizationCapabilityDefault: {
      invalidatesTags: (_result, _error, arg) => [
        { type: "OrganizationCapabilities", id: arg.organizationId },
        "Applications",
        "SpaceCapabilityPolicies",
      ],
      extraOptions: { retryUnauthorized: false },
    },
    entries: { providesTags: ["Folders", "Documents"] },
    summary: { providesTags: ["Documents"] },
    receipts: { providesTags: ["DocumentUploads"] },
    receipt: { providesTags: ["DocumentUploads"] },
    acknowledge: { invalidatesTags: ["DocumentUploads"], extraOptions: { retryUnauthorized: false } },
    setRetrievable(endpoint) {
      endpoint.invalidatesTags = ["Documents"];
      endpoint.extraOptions = { retryUnauthorized: false };
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        return { ...(typeof request === "string" ? { url: request } : request), timeout: 90_000 };
      };
    },
    start: { invalidatesTags: ["Documents", "DocumentUploads"], extraOptions: { retryUnauthorized: false } },
    preview(endpoint) {
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        return {
          ...(typeof request === "string" ? { url: request } : request),
          responseHandler: "text",
          timeout: 30_000,
        };
      };
    },
    upload(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      endpoint.invalidatesTags = ["Documents", "DocumentUploads"];
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 2_000_000 };
      };
    },
    createOrganization: { extraOptions: { retryUnauthorized: false } },
    updateOrganization: {
      extraOptions: { retryUnauthorized: false },
      // Patch the cached registry pages in place: a refetch would replace the rows, and the
      // edit button that opened the dialog with them, so focus could not return to it.
      async onQueryStarted({ id }, { dispatch, getState, queryFulfilled }) {
        let detail: OrganizationDetail;
        try {
          detail = (await queryFulfilled).data;
        } catch {
          return;
        }
        // The returned detail is what was committed: a reopened edit must not start from an older copy.
        void dispatch(controlPlaneApi.util.upsertQueryData("getOrganization", { id }, detail));
        const saved = detail.organization;
        const state = getState() as Parameters<typeof controlPlaneApi.util.selectCachedArgsForQuery>[0];
        for (const args of controlPlaneApi.util.selectCachedArgsForQuery(state, "organizationRegistry")) {
          dispatch(
            controlPlaneApi.util.updateQueryData("organizationRegistry", args, (draft) => {
              const index = draft.items.findIndex((item) => item.id === saved.id);
              if (index >= 0) draft.items[index] = saved;
            }),
          );
        }
      },
    },
    createFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
    renameFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
    deleteDocument: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Documents"] },
    deleteFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
    createPersonalSpace: {
      extraOptions: { retryUnauthorized: false },
    },
    bootstrapPlatformAdmin: { extraOptions: { retryUnauthorized: false } },
    importBlueprint(endpoint) {
      // Bearer expiry can follow committed provisioning writes: replay is explicit.
      endpoint.extraOptions = { retryUnauthorized: false };
      const generatedQuery = endpoint.query!;
      endpoint.query = (args) => {
        const request = generatedQuery(args);
        const body = new FormData();
        body.append("file", args.provisioningUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body };
      };
    },
  },
});

export const {
  useGetConversationTraceHistoryQuery,
  useGetTraceConsentQuery,
  useRevokeTraceConsentMutation,
  useSetTraceConsentMutation,
  useShareTraceIncidentMutation,

  useOrganizationResourcesQuery,
  useOrganizationHomeQuery,
  useOrganizationHomeSettingsQuery,
  useOrganizationHomeCandidatesQuery,
  useSetOrganizationHomeMutation,
  useWikiAvailabilityQuery,
  useWikiPagesQuery,
  useProposeWikiFileMutation,
  useWikiPageQuery,
  useLazyWikiPageQuery,
  useWikiRulesQuery,
  useWikiRevisionsQuery,
  useWikiProposalQuery,
  useCreateWikiPageMutation,
  useWriteWikiPageMutation,
  useWriteWikiRulesMutation,
  usePatchWikiPageMutation,
  usePrepareWikiDocumentMutation,
  useDeleteWikiPageMutation,
  useSubmitWikiProposalMutation,
  useWithdrawWikiProposalMutation,
  useRestoreWikiRevisionMutation,
  useUploadWordTemplateMutation,
  useResolveWordTemplateLibraryQuery,
  useSaveWordTemplateLibraryMutation,
  useUploadPowerpointTemplateMutation,
  useRemovePowerpointTemplateMutation,
  useResolvePowerpointTemplateQuery,
  useSpaceMembersQuery,
  useSpaceMemberCandidatesQuery,
  useGrantMutation,
  useRevokeMutation,
  useMarketplacesQuery,
  useMarketplaceProposalSpacesQuery,
  useMarketplaceEntriesQuery,
  useMarketplaceEntryQuery,
  useMarketplaceProposalsQuery,
  useMarketplaceProposalQuery,
  useSubmitMarketplaceProposalMutation,
  useDecideMarketplaceProposalMutation,
  useCancelMarketplaceProposalMutation,
  useWithdrawMarketplaceEntryMutation,
  useInstallMarketplaceEntryMutation,
  useMarketplaceInstallationQuery,
  useListPromptsQuery: usePromptCatalogQuery,
  useListPromptCategoriesQuery,
  useCreatePromptCategoryMutation,
  useRenamePromptCategoryMutation,
  useDeletePromptCategoryMutation,
  useGetPromptQuery,
  useLazyGetPromptQuery,
  useCreatePromptMutation,
  useAddPromptFavoriteMutation,
  useRemovePromptFavoriteMutation,
  useUpdatePromptMutation,
  useDeletePromptMutation,
  useListAttachmentsQuery,
  useDeleteAttachmentMutation,
  usePlatformApplicationsQuery,
  useSpaceApplicationsQuery,
  useCreateApplicationMutation,
  useUpdateApplicationMutation,
  useLazyListSessionsQuery,
  useLazyListAgentInstancesQuery,
  useListSessionsQuery,
  useGetSessionQuery,
  useCreateSessionMutation,
  useUpdateSessionMutation,
  useDeleteSessionMutation,
  usePrepareExecutionMutation,
  useListAgentInstancesQuery,
  useGetAgentInstanceQuery,
  useCreateAgentInstanceMutation,
  useUpdateAgentInstanceMutation,
  useDeleteAgentInstanceMutation,
  useSpaceAgentTemplatesQuery,
  useOrganizationSupervisionQuery,
  useTeamSupervisionQuery,
  useGetCreationAssistantSettingsQuery,
  usePatchCreationAssistantSettingsMutation,
  useResetCreationAssistantPromptMutation,
  useDraftAgentMutation,
  useGetCommonPromptSettingsQuery,
  usePutCommonPromptSettingsMutation,
  useOrganizationModelsQuery,
  useOrganizationModelPolicyQuery,
  useReplaceOrganizationModelPolicyMutation,
  useRefreshModelSourceMutation,
  useOrganizationAgentsQuery,
  useSetOrganizationAgentDefaultMutation,
  useOrganizationCapabilitiesQuery,
  useMcpConnectionsQuery,
  useMcpCredentialsQuery,
  useCreateMcpConnectionMutation,
  useUpdateMcpConnectionMutation,
  useTestMcpConnectionMutation,
  usePublishMcpConnectionMutation,
  useRefreshOrganizationCapabilitiesMutation,
  useSetOrganizationCapabilityDefaultMutation,
  useLazyOrganizationCapabilityRevokeImpactQuery,
  useStartMutation,
  useSetRetrievableMutation,
  useLazyPreviewQuery,
  useEntriesQuery,
  useLazyEntriesQuery,
  useSummaryQuery,
  usePreflightMutation,
  useImportBlueprintMutation,
  useOrganizationRegistryQuery,
  useSearchOrganizationCandidatesQuery,
  useCreateOrganizationMutation,
  useGetOrganizationQuery,
  useUpdateOrganizationMutation,
  useCreateFolderMutation,
  useRenameFolderMutation,
  useDeleteFolderMutation,
  useDeleteDocumentMutation,
  useMeQuery,
  useGetTeamAvatarQuery,
  usePutTeamAvatarMutation,
  useDeleteTeamAvatarMutation,
  useRemoveSpaceMemberMutation,

  useTeamDocumentActivityQuery,
  useGetMyAvatarQuery,
  useGetUserAvatarQuery,
  usePutMyAvatarMutation,
  useDeleteMyAvatarMutation,
  useOrganizationTeamsQuery,
  useTeamMetadataQuery,
  useJoinTeamMutation,
  useMySpacesQuery,
  useUpdateTeamParametersMutation,
  useTeamJoinLinkQuery,
  useCreateTeamJoinLinkMutation,
  useRevokeTeamJoinLinkMutation,
  usePreviewTeamJoinLinkQuery,
  useRedeemTeamJoinLinkMutation,
  useCreatePersonalSpaceMutation,
  useOnboardingStatusQuery,
  useAcceptTermsMutation,
  useBootstrapPlatformAdminMutation,
} = enhancedControlPlaneApi;

// authorizeSpace as a query: the last answer stays cached through rechecks and page changes.
export const { useSpaceAccessQuery } = enhancedControlPlaneApi.injectEndpoints({
  endpoints: (build) => ({
    spaceAccess: build.query<Allowed, SpaceCheck>({
      keepUnusedDataFor: 600,
      providesTags: ["SpaceAccess"],
      queryFn: async (spaceCheck, { dispatch }) => {
        const answer = await dispatch(
          enhancedControlPlaneApi.endpoints.authorizeSpace.initiate({ spaceCheck }, { track: false }),
        );
        return "error" in answer ? { error: answer.error as FetchBaseQueryError } : { data: answer.data };
      },
    }),
  }),
});
