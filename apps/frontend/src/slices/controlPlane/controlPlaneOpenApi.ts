import { controlPlaneApi as api } from "./controlPlaneApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    organizationRegistry: build.query<OrganizationRegistryApiResponse, OrganizationRegistryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/organizations`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    createOrganization: build.mutation<CreateOrganizationApiResponse, CreateOrganizationApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/organizations`,
        method: "POST",
        body: queryArg.createOrganization,
      }),
    }),
    searchOrganizationCandidates: build.query<
      SearchOrganizationCandidatesApiResponse,
      SearchOrganizationCandidatesApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/organizations/candidates`,
        params: {
          query: queryArg.query,
        },
      }),
    }),
    teamRegistry: build.query<TeamRegistryApiResponse, TeamRegistryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/teams`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    executeStream: build.mutation<ExecuteStreamApiResponse, ExecuteStreamApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/agents/execute/stream`,
        method: "POST",
        body: queryArg.executeRequest,
      }),
    }),
    authorizeDocument: build.mutation<AuthorizeDocumentApiResponse, AuthorizeDocumentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/document`,
        method: "POST",
        body: queryArg.authorizeDocument,
      }),
    }),
    authorizePlatform: build.mutation<AuthorizePlatformApiResponse, AuthorizePlatformApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/platform`,
        method: "POST",
        body: queryArg.platformCheck,
      }),
    }),
    authorizeScope: build.mutation<AuthorizeScopeApiResponse, AuthorizeScopeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/scope`,
        method: "POST",
        body: queryArg.authorizeScope,
      }),
    }),
    authorizeSpace: build.mutation<AuthorizeSpaceApiResponse, AuthorizeSpaceApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/authorize/space`, method: "POST", body: queryArg.spaceCheck }),
    }),
    bootstrapPlatformAdmin: build.mutation<BootstrapPlatformAdminApiResponse, BootstrapPlatformAdminApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/bootstrap/platform-admin`,
        method: "POST",
        body: queryArg.bootstrapRequest,
      }),
    }),
    deletionStatus: build.query<DeletionStatusApiResponse, DeletionStatusApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/deletions/${queryArg.operationId}` }),
    }),
    cleanup: build.query<CleanupApiResponse, CleanupApiArg>({
      query: () => ({ url: `/control-plane/v1/document-processing/cleanup` }),
    }),
    cleaned: build.mutation<CleanedApiResponse, CleanedApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/cleanup`,
        method: "POST",
        body: queryArg.cleaned,
      }),
    }),
    retrievalWork: build.query<RetrievalWorkApiResponse, RetrievalWorkApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/retrievable/${queryArg.id}`,
        params: {
          operation_id: queryArg.operationId,
        },
      }),
    }),
    confirmRetrievable: build.mutation<ConfirmRetrievableApiResponse, ConfirmRetrievableApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/retrievable/${queryArg.id}`,
        method: "POST",
        body: queryArg.retrievalConfirmation,
      }),
    }),
    abandon: build.mutation<AbandonApiResponse, AbandonApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/abandon`,
        method: "POST",
        body: queryArg.failure,
      }),
    }),
    claim: build.mutation<ClaimApiResponse, ClaimApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/claim`,
        method: "POST",
        body: queryArg.claim,
      }),
    }),
    commit: build.mutation<CommitApiResponse, CommitApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/commit`,
        method: "POST",
        body: queryArg.commit,
      }),
    }),
    original: build.query<OriginalApiResponse, OriginalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/original`,
        params: {
          generation: queryArg.generation,
        },
      }),
    }),
    vectors: build.mutation<VectorsApiResponse, VectorsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/vectors`,
        method: "POST",
        body: queryArg.vectorPlan,
      }),
    }),
    work: build.query<WorkApiResponse, WorkApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-processing/${queryArg.id}/work` }),
    }),
    receipt: build.query<ReceiptApiResponse, ReceiptApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-uploads/${queryArg.id}` }),
    }),
    acknowledge: build.mutation<AcknowledgeApiResponse, AcknowledgeApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-uploads/${queryArg.id}/acknowledgment`, method: "PUT" }),
    }),
    deleteDocument: build.mutation<DeleteDocumentApiResponse, DeleteDocumentApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/documents/${queryArg.id}`, method: "DELETE" }),
    }),
    content: build.query<ContentApiResponse, ContentApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/documents/${queryArg.id}/content` }),
    }),
    preview: build.query<PreviewApiResponse, PreviewApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/preview`,
        params: {
          artifact: queryArg.artifact,
        },
      }),
    }),
    history: build.query<HistoryApiResponse, HistoryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/processing`,
        params: {
          before: queryArg.before,
        },
      }),
    }),
    start: build.mutation<StartApiResponse, StartApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/processing`,
        method: "POST",
        body: queryArg.start,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
      }),
    }),
    setRetrievable: build.mutation<SetRetrievableApiResponse, SetRetrievableApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/retrievable`,
        method: "PUT",
        body: queryArg.setRetrievable,
      }),
    }),
    createFolder: build.mutation<CreateFolderApiResponse, CreateFolderApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/folders`, method: "POST", body: queryArg.createFolder }),
    }),
    deleteFolder: build.mutation<DeleteFolderApiResponse, DeleteFolderApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/folders/${queryArg.id}`, method: "DELETE" }),
    }),
    renameFolder: build.mutation<RenameFolderApiResponse, RenameFolderApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/folders/${queryArg.id}`,
        method: "PATCH",
        body: queryArg.rename,
      }),
    }),
    upload: build.mutation<UploadApiResponse, UploadApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/folders/${queryArg.id}/documents`,
        method: "POST",
        body: queryArg.fileUpload,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
        params: {
          retry_of: queryArg.retryOf,
          profile: queryArg.profile,
        },
      }),
    }),
    preflight: build.mutation<PreflightApiResponse, PreflightApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/folders/${queryArg.id}/documents/preflight`,
        method: "POST",
        body: queryArg.preflight,
      }),
    }),
    frontendConfig: build.query<FrontendConfigApiResponse, FrontendConfigApiArg>({
      query: () => ({ url: `/control-plane/v1/frontend/config` }),
    }),
    acceptTerms: build.mutation<AcceptTermsApiResponse, AcceptTermsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/gcu`, method: "POST", body: queryArg.termsRequest }),
    }),
    health: build.query<HealthApiResponse, HealthApiArg>({
      query: () => ({ url: `/control-plane/v1/healthz` }),
    }),
    importBlueprint: build.mutation<ImportBlueprintApiResponse, ImportBlueprintApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/import-export/import`,
        method: "POST",
        body: queryArg.provisioningUpload,
      }),
    }),
    me: build.query<MeApiResponse, MeApiArg>({
      query: () => ({ url: `/control-plane/v1/me` }),
    }),
    onboardingStatus: build.query<OnboardingStatusApiResponse, OnboardingStatusApiArg>({
      query: () => ({ url: `/control-plane/v1/me/onboarding` }),
    }),
    createPersonalSpace: build.mutation<CreatePersonalSpaceApiResponse, CreatePersonalSpaceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/me/personal-space`,
        method: "POST",
        body: queryArg.createPersonalSpace,
      }),
    }),
    mySpaces: build.query<MySpacesApiResponse, MySpacesApiArg>({
      query: () => ({ url: `/control-plane/v1/me/spaces` }),
    }),
    organizationAgents: build.query<OrganizationAgentsApiResponse, OrganizationAgentsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/organizations/${queryArg.organizationId}/agents` }),
    }),
    setOrganizationAgentDefault: build.mutation<
      SetOrganizationAgentDefaultApiResponse,
      SetOrganizationAgentDefaultApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/agents/${queryArg.agentId}/default-on`,
        method: "PUT",
        body: queryArg.setAgentDefaultOnRequest,
      }),
    }),
    createSpace: build.mutation<CreateSpaceApiResponse, CreateSpaceApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces`, method: "POST", body: queryArg.createSpace }),
    }),
    deleteSpace: build.mutation<DeleteSpaceApiResponse, DeleteSpaceApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}`, method: "DELETE" }),
    }),
    receipts: build.query<ReceiptsApiResponse, ReceiptsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/document-uploads`,
        params: {
          before: queryArg.before,
          before_key: queryArg.beforeKey,
          limit: queryArg.limit,
        },
      }),
    }),
    entries: build.query<EntriesApiResponse, EntriesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/entries`,
        params: {
          parent_id: queryArg.parentId,
          search: queryArg.search,
          order: queryArg.order,
          offset: queryArg.offset,
          limit: queryArg.limit,
        },
      }),
    }),
    grant: build.mutation<GrantApiResponse, GrantApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/roles/${queryArg.role}/${queryArg.user}`,
        method: "PUT",
      }),
    }),
    revoke: build.mutation<RevokeApiResponse, RevokeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/roles/${queryArg.role}/${queryArg.user}`,
        method: "DELETE",
      }),
    }),
    summary: build.query<SummaryApiResponse, SummaryApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/storage` }),
    }),
    listPlatformRoles: build.query<ListPlatformRolesApiResponse, ListPlatformRolesApiArg>({
      query: () => ({ url: `/control-plane/v1/users/platform-roles` }),
    }),
    grantPlatformRole: build.mutation<GrantPlatformRoleApiResponse, GrantPlatformRoleApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/${queryArg.user}/platform-roles/${queryArg.role}`,
        method: "PUT",
      }),
    }),
    revokePlatformRole: build.mutation<RevokePlatformRoleApiResponse, RevokePlatformRoleApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/${queryArg.user}/platform-roles/${queryArg.role}`,
        method: "DELETE",
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as controlPlaneApi };
export type OrganizationRegistryApiResponse = /** status 200 undefined */ OrganizationPage;
export type OrganizationRegistryApiArg = {
  /** Exclusive UUID cursor; at most 100 active organizations. */
  after?: string;
};
export type CreateOrganizationApiResponse = /** status 201 undefined */ Space;
export type CreateOrganizationApiArg = {
  createOrganization: CreateOrganization;
};
export type SearchOrganizationCandidatesApiResponse = /** status 200 undefined */ UserSummary[];
export type SearchOrganizationCandidatesApiArg = {
  query: string;
};
export type TeamRegistryApiResponse = /** status 200 Success */ Space[];
export type TeamRegistryApiArg = {
  /** Exclusive UUID cursor; at most 100 non-personal teams, ordered by ID. */
  after?: string;
};
export type ExecuteStreamApiResponse =
  /** status 200 SSE data frames containing RuntimeEvent JSON; final closes the stream without a sentinel */ RuntimeEvent;
export type ExecuteStreamApiArg = {
  executeRequest: ExecuteRequest;
};
export type AuthorizeDocumentApiResponse = /** status 200 Success */ Allowed;
export type AuthorizeDocumentApiArg = {
  authorizeDocument: AuthorizeDocument;
};
export type AuthorizePlatformApiResponse = /** status 200 Success */ Allowed;
export type AuthorizePlatformApiArg = {
  platformCheck: PlatformCheck;
};
export type AuthorizeScopeApiResponse = /** status 200 Success */ Scope;
export type AuthorizeScopeApiArg = {
  authorizeScope: AuthorizeScope;
};
export type AuthorizeSpaceApiResponse = /** status 200 Success */ Allowed;
export type AuthorizeSpaceApiArg = {
  spaceCheck: SpaceCheck;
};
export type BootstrapPlatformAdminApiResponse = /** status 200 Success */ BootstrapResponse;
export type BootstrapPlatformAdminApiArg = {
  bootstrapRequest: BootstrapRequest;
};
export type DeletionStatusApiResponse = /** status 200 undefined */ Receipt;
export type DeletionStatusApiArg = {
  operationId: string;
};
export type CleanupApiResponse = /** status 200 undefined */ Cleanup[];
export type CleanupApiArg = void;
export type CleanedApiResponse = unknown;
export type CleanedApiArg = {
  cleaned: Cleaned;
};
export type RetrievalWorkApiResponse = /** status 200 undefined */ RetrievalWork;
export type RetrievalWorkApiArg = {
  id: string;
  operationId: string;
};
export type ConfirmRetrievableApiResponse = unknown;
export type ConfirmRetrievableApiArg = {
  id: string;
  retrievalConfirmation: RetrievalConfirmation;
};
export type AbandonApiResponse = /** status 200 undefined */ Summary;
export type AbandonApiArg = {
  id: string;
  failure: Failure;
};
export type ClaimApiResponse = /** status 200 undefined */ Descriptor;
export type ClaimApiArg = {
  id: string;
  claim: Claim;
};
export type CommitApiResponse = /** status 200 undefined */ Summary;
export type CommitApiArg = {
  id: string;
  commit: Commit;
};
export type OriginalApiResponse = /** status 200 undefined */ string;
export type OriginalApiArg = {
  id: string;
  generation: string;
};
export type VectorsApiResponse = unknown;
export type VectorsApiArg = {
  id: string;
  vectorPlan: VectorPlan;
};
export type WorkApiResponse = /** status 200 undefined */ Work;
export type WorkApiArg = {
  id: string;
};
export type ReceiptApiResponse = /** status 200 undefined */ UploadReceipt;
export type ReceiptApiArg = {
  id: string;
};
export type AcknowledgeApiResponse = unknown;
export type AcknowledgeApiArg = {
  id: string;
};
export type DeleteDocumentApiResponse = /** status 200 undefined */ Receipt | /** status 202 undefined */ Receipt;
export type DeleteDocumentApiArg = {
  id: string;
};
export type ContentApiResponse = /** status 200 undefined */ string;
export type ContentApiArg = {
  id: string;
};
export type PreviewApiResponse = /** status 200 undefined */ string | /** status 206 undefined */ string;
export type PreviewApiArg = {
  id: string;
  /** native, raw, metadata, or a relative path from the published manifest. */
  artifact?: string;
};
export type HistoryApiResponse = /** status 200 undefined */ Summary[];
export type HistoryApiArg = {
  id: string;
  before?: string | null;
};
export type StartApiResponse = /** status 200 undefined */ Summary;
export type StartApiArg = {
  id: string;
  "Idempotency-Key": string;
  start: Start;
};
export type SetRetrievableApiResponse = /** status 200 undefined */ Document;
export type SetRetrievableApiArg = {
  id: string;
  setRetrievable: SetRetrievable;
};
export type CreateFolderApiResponse = /** status 201 Success */ Folder;
export type CreateFolderApiArg = {
  createFolder: CreateFolder;
};
export type DeleteFolderApiResponse = unknown;
export type DeleteFolderApiArg = {
  id: string;
};
export type RenameFolderApiResponse = unknown;
export type RenameFolderApiArg = {
  id: string;
  rename: Rename;
};
export type UploadApiResponse = /** status 200 undefined */ UploadReceipt | /** status 201 undefined */ UploadReceipt;
export type UploadApiArg = {
  id: string;
  /** Required request UUID */
  "Idempotency-Key": string;
  retryOf?: string;
  /** Omit for upload only */
  profile?: Profile;
  fileUpload: FileUpload;
};
export type PreflightApiResponse = /** status 200 undefined */ PreflightResult;
export type PreflightApiArg = {
  id: string;
  preflight: Preflight;
};
export type FrontendConfigApiResponse = /** status 200 undefined */ FrontendConfig;
export type FrontendConfigApiArg = void;
export type AcceptTermsApiResponse = unknown;
export type AcceptTermsApiArg = {
  termsRequest: TermsRequest;
};
export type HealthApiResponse = /** status 200 undefined */ Health;
export type HealthApiArg = void;
export type ImportBlueprintApiResponse = /** status 200 Success */ Report;
export type ImportBlueprintApiArg = {
  provisioningUpload: ProvisioningUpload;
};
export type MeApiResponse = /** status 200 Success */ Me;
export type MeApiArg = void;
export type OnboardingStatusApiResponse = /** status 200 undefined */ OnboardingStatus;
export type OnboardingStatusApiArg = void;
export type CreatePersonalSpaceApiResponse = /** status 200 Existing personal space */
  | Space
  | /** status 201 Created personal space */ Space;
export type CreatePersonalSpaceApiArg = {
  createPersonalSpace: CreatePersonalSpace;
};
export type MySpacesApiResponse = /** status 200 Success */ MySpace[];
export type MySpacesApiArg = void;
export type OrganizationAgentsApiResponse = /** status 200 undefined */ AgentEnablement[];
export type OrganizationAgentsApiArg = {
  organizationId: string;
};
export type SetOrganizationAgentDefaultApiResponse = /** status 200 undefined */ AgentDefaultOnResult;
export type SetOrganizationAgentDefaultApiArg = {
  organizationId: string;
  agentId: string;
  setAgentDefaultOnRequest: SetAgentDefaultOnRequest;
};
export type CreateSpaceApiResponse = /** status 201 Success */ Space;
export type CreateSpaceApiArg = {
  createSpace: CreateSpace;
};
export type DeleteSpaceApiResponse = /** status 200 Already completed */
  | Receipt
  | /** status 202 Durably accepted */ Receipt;
export type DeleteSpaceApiArg = {
  id: string;
};
export type ReceiptsApiResponse = /** status 200 undefined */ UploadReceipt[];
export type ReceiptsApiArg = {
  id: string;
  before?: string;
  beforeKey?: string;
  limit?: number;
};
export type EntriesApiResponse = /** status 200 undefined */ Directory;
export type EntriesApiArg = {
  id: string;
  parentId?: string;
  /** Literal case-insensitive substring; at most 255 characters. */
  search?: string;
  order?: EntryOrder;
  offset?: number;
  limit?: number;
};
export type GrantApiResponse = unknown;
export type GrantApiArg = {
  id: string;
  role: Role;
  user: string;
};
export type RevokeApiResponse = unknown;
export type RevokeApiArg = {
  id: string;
  role: Role;
  user: string;
};
export type SummaryApiResponse = /** status 200 undefined */ StorageSummary;
export type SummaryApiArg = {
  id: string;
};
export type ListPlatformRolesApiResponse = /** status 200 Success */ Grant[];
export type ListPlatformRolesApiArg = void;
export type GrantPlatformRoleApiResponse = unknown;
export type GrantPlatformRoleApiArg = {
  user: string;
  role: PlatformRole;
};
export type RevokePlatformRoleApiResponse = unknown;
export type RevokePlatformRoleApiArg = {
  user: string;
  role: PlatformRole;
};
export type SpaceKind = "organization" | "team" | "project" | "personal";
export type Space = {
  id: string;
  kind: SpaceKind;
  name: string;
  parent_id: string | null;
  /** Ancestors then self: the search scope. A personal space's path is itself. */
  path: string[];
  personal_owner: string | null;
};
export type OrganizationPage = {
  items: Space[];
  next_cursor?: string | null;
};
export type ErrorBody = {
  code: string;
  detail: string;
};
export type CreateOrganization = {
  admin_username: string;
  name: string;
  owner_username: string;
};
export type UserSummary = {
  avatar_image_url?: string | null;
  email?: string | null;
  first_name?: string | null;
  id: string;
  last_name?: string | null;
  username?: string | null;
};
export type RuntimeEvent =
  | {
      kind: "status";
      sequence: number;
      status: string;
    }
  | {
      delta: string;
      kind: "assistant_delta";
      sequence: number;
    }
  | {
      content: string;
      finish_reason: string;
      kind: "final";
      sequence: number;
    };
export type ExecuteRequest = {
  agent_id?: string | null;
  agent_instance_id?: string | null;
  input?: string;
  runtime_context?:
    | {
        [key: string]: any;
      }
    | {
        [key: string]: any;
      };
  session_id?: string | null;
  [key: string]: any;
};
export type Allowed = {
  allowed: boolean;
};
export type Permission = "read" | "write" | "manage";
export type AuthorizeDocument = {
  document_id: string;
  permission: Permission;
};
export type PlatformPermission =
  | "list_all_teams"
  | "delete_team"
  | "delete_space"
  | "rescue_team_admin"
  | "edit_agent_class_path"
  | "observe_platform"
  | "administer_users"
  | "manage_platform"
  | "manage_capabilities"
  | "edit_platform_prompt";
export type PlatformCheck = {
  permission: PlatformPermission;
};
export type Scope = {
  /** Filter for chunks and metadata: `space_id` must be one of these. The space and its
    ancestors, never descendants: a team conversation never sees its projects' content.
    A personal space's scope is itself. */
  space_ids: string[];
};
export type AuthorizeScope = {
  /** Keep only spaces of these kinds; omitted keeps every level. Never adds a space. */
  levels?: SpaceKind[] | null;
  space_id: string;
};
export type SpacePermission =
  | "read"
  | "write"
  | "manage"
  | "run_evaluations"
  | "manage_evaluation_corpus"
  | "read_conversations_for_evaluation"
  | "own_organization"
  | "create_personal_space";
export type SpaceCheck = {
  permission: SpacePermission;
  space_id: string;
};
export type BootstrapResponse = {
  user_id: string;
  username: string;
};
export type BootstrapRequest = {
  token: string;
};
export type Status = "queued" | "running" | "retrying" | "blocked" | "completed";
export type TargetKind = "organization" | "team" | "project" | "document";
export type Receipt = {
  actor_subject: string;
  completed_at?: string | null;
  documents_deleted: number;
  due_at: string;
  error_code?: string | null;
  folders_deleted: number;
  id: string;
  organization_id: string;
  requested_at: string;
  rule_id?: string | null;
  spaces_deleted: number;
  status: Status;
  target_id: string;
  target_kind: TargetKind;
  target_parent_id?: string | null;
};
export type Profile = "fast" | "medium" | "rich";
export type Work = {
  contract_version: number;
  document_id: string;
  installation_id: string;
  original_sha256: string;
  processing_id: string;
  profile: Profile;
};
export type Cleanup = {
  batch: number;
  chunks: number;
  cursor: number;
  generation: string;
  output_prefix: string;
  preserve_objects: boolean;
  protected_ordinals: number[];
  purge_document: boolean;
  work: Work;
};
export type Cleaned = {
  cursor: number;
  generation: string;
  next_cursor: number;
  objects_empty: boolean;
  purge_document?: boolean;
  work: Work;
};
export type Artifact = {
  path: string;
  sha256: string;
  size: number;
};
export type Manifest = {
  artifacts: Artifact[];
  chunks: number;
  generation: string;
  rows?: number | null;
  vector_ordinals: number[];
  vectors: number;
};
export type ProjectionPhase = "uncertain" | "ready" | "writing" | "applied";
export type RetrievalWork = {
  confirmed: boolean;
  document_id: string;
  manifest: Manifest;
  operation_id: string;
  phase: ProjectionPhase;
  restore: boolean;
  retrievable: boolean;
};
export type RetrievalStep = "claim" | "applied" | "confirm";
export type RetrievalConfirmation = {
  operation_id: string;
  retrievable: boolean;
  step?: RetrievalStep;
};
export type Stage = "queued" | "preparation" | "extraction" | "indexing" | "done";
export type ProcessingStatus = "pending" | "running" | "succeeded" | "failed";
export type Summary = {
  chunks: number;
  completed_at?: string | null;
  created_at: string;
  document_id: string;
  error_code?: string | null;
  id: string;
  profile: Profile;
  retry_of?: string | null;
  revision: number;
  rows?: number | null;
  stage: Stage;
  status: ProcessingStatus;
  vectors: number;
};
export type FailureCode =
  | "unsupported_input"
  | "access_changed"
  | "integrity_failure"
  | "extraction_failed"
  | "preview_failed"
  | "indexing_failed"
  | "capacity_exceeded"
  | "worker_failed"
  | "deadline_exceeded"
  | "delivery_unknown";
export type Failure = {
  code: FailureCode;
  generation?: string | null;
  stage: Stage;
  work: Work;
};
export type Descriptor = {
  actor: string;
  committed?: Manifest | null;
  expires_at: string;
  file: any;
  folder_id: string;
  folder_path: string;
  generation: string;
  max_artifacts: number;
  max_chunks: number;
  max_output_bytes: number;
  mime: string;
  name: string;
  organization_id: string;
  output_prefix: string;
  predecessor?: Manifest | null;
  profile_settings: any;
  size: number;
  space_id: string;
  stage: Stage;
  work: Work;
};
export type Claim = {
  activity_id: string;
  attempt: number;
  execution_id: string;
  stage: Stage;
  work: Work;
};
export type Commit = {
  manifest: Manifest;
  stage: Stage;
  work: Work;
};
export type VectorPlan = {
  count: number;
  generation: string;
  work: Work;
};
export type UploadStatus = "pending" | "stored" | "failed";
export type UploadReceipt = {
  acknowledged_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  document_id?: string | null;
  error_code?: string | null;
  folder_id: string;
  mime: string;
  name: string;
  processing?: Summary | null;
  processing_profile?: Profile | null;
  request_key: string;
  sha256: string;
  size: number;
  space_id: string;
  status: UploadStatus;
  successor_key?: string | null;
};
export type Start = {
  profile: Profile;
  retry_of?: string | null;
};
export type Document = {
  created_at: string;
  created_by: string;
  folder_id: string | null;
  id: string;
  mime: string;
  name: string;
  retrievable: boolean;
  retrievable_pending: boolean;
  sha256: string;
  size: number;
  space_id: string;
};
export type SetRetrievable = {
  /** null restores an untouched legacy publication from its verified metadata and chunks. */
  retrievable: boolean | null;
};
export type Folder = {
  created_at: string;
  id: string;
  name: string;
  parent_id: string | null;
  path: string;
  space_id: string;
};
export type CreateFolder = {
  name: string;
  parent_id?: string | null;
  space_id: string;
};
export type Rename = {
  name: string;
};
export type FileUpload = {
  file: Blob;
};
export type TypeUsage = {
  bytes: number;
  documents: number;
  mime: string;
};
export type StorageSummary = {
  bytes: number;
  documents: number;
  max_file_bytes: number;
  processing_enabled: boolean;
  quota_bytes: number;
  reserved_bytes: number;
  types: TypeUsage[];
  uploads_enabled: boolean;
  used_bytes: number;
};
export type PreflightResult = {
  conflicts: string[];
  storage: StorageSummary;
};
export type Candidate = {
  name: string;
  size: number;
};
export type Preflight = {
  files: Candidate[];
};
export type PublicAuth = {
  client_id: string;
  enabled: boolean;
  provider: string;
  realm_url: string;
  roles_claim?: string[] | null;
  uid_claim: string;
};
export type FrontendConfig = {
  gcu_version?: string | null;
  root_bootstrap_completed: boolean;
  root_bootstrap_required: boolean;
  user_auth: PublicAuth;
};
export type TermsRequest = {
  version: string;
};
export type Health = {
  status: string;
};
export type Report = {
  grants_acknowledged: number;
  identities_created: number;
  identities_resolved: number;
  spaces_reconciled: number;
};
export type ProvisioningUpload = {
  file: Blob;
};
export type PlatformRole = "platform_owner" | "platform_observer" | "feature_manager" | "prompt_editor";
export type Me = {
  platform_roles: PlatformRole[];
  user_id: string;
  username: string;
};
export type Acceptance = {
  accepted_at: string;
  version: string;
};
export type OnboardingStatus = {
  acceptance?: Acceptance | null;
  gcu_version?: string | null;
  root_bootstrap_required: boolean;
  user_id: string;
  username: string;
};
export type CreatePersonalSpace = {
  organization_id: string;
};
export type Role = "member" | "editor" | "admin" | "analyst" | "organization_owner" | "personal_space_creator";
export type MySpace = Space & {
  /** The subset of `roles` held only through an ancestor. */
  inherited_roles: Role[];
  organization_id: string;
  /** Effective roles, including those descending from an ancestor. */
  roles: Role[];
};
export type AgentCapabilityKind = "agent";
export type AgentScopePolicy = "admin_gated";
export type AgentEnablement = {
  default_capability_ids: string[];
  default_on: boolean;
  description: string;
  icon: string;
  id: string;
  kind: AgentCapabilityKind;
  name: string;
  public_version?: string | null;
  runtime_id: string;
  source_id: string;
  team_scope: AgentScopePolicy;
  version: string;
};
export type AgentDefaultOnResult = {
  capability_id: string;
  default_on: boolean;
};
export type SetAgentDefaultOnRequest = {
  default_on: boolean;
};
export type CreateSpace = {
  /** Initial administrator; creation grants the caller nothing on the new space. */
  admin: string;
  kind: SpaceKind;
  name: string;
  parent_id: string;
};
export type Entry =
  | {
      data: Folder;
      kind: "folder";
    }
  | {
      data: Document;
      kind: "document";
    };
export type Directory = {
  ancestors: Folder[];
  can_write: boolean;
  items: Entry[];
  limit: number;
  offset: number;
  processing: {
    [key: string]: Summary;
  };
  processing_enabled: boolean;
  total: number;
};
export type EntryOrder = "name_asc" | "name_desc" | "created_asc" | "created_desc" | "size_asc" | "size_desc";
export type Grant = {
  role: PlatformRole;
  user_id: string;
};
export const {
  useOrganizationRegistryQuery,
  useLazyOrganizationRegistryQuery,
  useCreateOrganizationMutation,
  useSearchOrganizationCandidatesQuery,
  useLazySearchOrganizationCandidatesQuery,
  useTeamRegistryQuery,
  useLazyTeamRegistryQuery,
  useExecuteStreamMutation,
  useAuthorizeDocumentMutation,
  useAuthorizePlatformMutation,
  useAuthorizeScopeMutation,
  useAuthorizeSpaceMutation,
  useBootstrapPlatformAdminMutation,
  useDeletionStatusQuery,
  useLazyDeletionStatusQuery,
  useCleanupQuery,
  useLazyCleanupQuery,
  useCleanedMutation,
  useRetrievalWorkQuery,
  useLazyRetrievalWorkQuery,
  useConfirmRetrievableMutation,
  useAbandonMutation,
  useClaimMutation,
  useCommitMutation,
  useOriginalQuery,
  useLazyOriginalQuery,
  useVectorsMutation,
  useWorkQuery,
  useLazyWorkQuery,
  useReceiptQuery,
  useLazyReceiptQuery,
  useAcknowledgeMutation,
  useDeleteDocumentMutation,
  useContentQuery,
  useLazyContentQuery,
  usePreviewQuery,
  useLazyPreviewQuery,
  useHistoryQuery,
  useLazyHistoryQuery,
  useStartMutation,
  useSetRetrievableMutation,
  useCreateFolderMutation,
  useDeleteFolderMutation,
  useRenameFolderMutation,
  useUploadMutation,
  usePreflightMutation,
  useFrontendConfigQuery,
  useLazyFrontendConfigQuery,
  useAcceptTermsMutation,
  useHealthQuery,
  useLazyHealthQuery,
  useImportBlueprintMutation,
  useMeQuery,
  useLazyMeQuery,
  useOnboardingStatusQuery,
  useLazyOnboardingStatusQuery,
  useCreatePersonalSpaceMutation,
  useMySpacesQuery,
  useLazyMySpacesQuery,
  useOrganizationAgentsQuery,
  useLazyOrganizationAgentsQuery,
  useSetOrganizationAgentDefaultMutation,
  useCreateSpaceMutation,
  useDeleteSpaceMutation,
  useReceiptsQuery,
  useLazyReceiptsQuery,
  useEntriesQuery,
  useLazyEntriesQuery,
  useGrantMutation,
  useRevokeMutation,
  useSummaryQuery,
  useLazySummaryQuery,
  useListPlatformRolesQuery,
  useLazyListPlatformRolesQuery,
  useGrantPlatformRoleMutation,
  useRevokePlatformRoleMutation,
} = injectedRtkApi;
