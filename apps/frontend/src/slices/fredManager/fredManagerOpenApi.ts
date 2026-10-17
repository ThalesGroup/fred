import { fredManagerApi as api } from "./fredManagerApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    teamRegistry: build.query<TeamRegistryApiResponse, TeamRegistryApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/admin/teams`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    authorizeDocument: build.mutation<AuthorizeDocumentApiResponse, AuthorizeDocumentApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/authorize/document`,
        method: "POST",
        body: queryArg.authorizeDocument,
      }),
    }),
    authorizePlatform: build.mutation<AuthorizePlatformApiResponse, AuthorizePlatformApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/authorize/platform`,
        method: "POST",
        body: queryArg.platformCheck,
      }),
    }),
    authorizeScope: build.mutation<AuthorizeScopeApiResponse, AuthorizeScopeApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/authorize/scope`, method: "POST", body: queryArg.authorizeScope }),
    }),
    authorizeSpace: build.mutation<AuthorizeSpaceApiResponse, AuthorizeSpaceApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/authorize/space`, method: "POST", body: queryArg.spaceCheck }),
    }),
    bootstrapPlatformAdmin: build.mutation<BootstrapPlatformAdminApiResponse, BootstrapPlatformAdminApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/bootstrap/platform-admin`,
        method: "POST",
        body: queryArg.bootstrapRequest,
      }),
    }),
    deletionStatus: build.query<DeletionStatusApiResponse, DeletionStatusApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/deletions/${queryArg.operationId}` }),
    }),
    createDocument: build.mutation<CreateDocumentApiResponse, CreateDocumentApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/documents`, method: "POST", body: queryArg.createDocument }),
    }),
    getDocument: build.query<GetDocumentApiResponse, GetDocumentApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/documents/${queryArg.id}` }),
    }),
    deleteDocument: build.mutation<DeleteDocumentApiResponse, DeleteDocumentApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/documents/${queryArg.id}`, method: "DELETE" }),
    }),
    renameDocument: build.mutation<RenameDocumentApiResponse, RenameDocumentApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/documents/${queryArg.id}`,
        method: "PATCH",
        body: queryArg.rename,
      }),
    }),
    ingestDocument: build.mutation<IngestDocumentApiResponse, IngestDocumentApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/documents/${queryArg.id}/ingest`,
        method: "POST",
        body: queryArg.ingestRequest,
      }),
    }),
    createFolder: build.mutation<CreateFolderApiResponse, CreateFolderApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/folders`, method: "POST", body: queryArg.createFolder }),
    }),
    deleteFolder: build.mutation<DeleteFolderApiResponse, DeleteFolderApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/folders/${queryArg.id}`, method: "DELETE" }),
    }),
    renameFolder: build.mutation<RenameFolderApiResponse, RenameFolderApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/folders/${queryArg.id}`, method: "PATCH", body: queryArg.rename }),
    }),
    frontendConfig: build.query<FrontendConfigApiResponse, FrontendConfigApiArg>({
      query: () => ({ url: `/fred-manager/v1/frontend/config` }),
    }),
    acceptTerms: build.mutation<AcceptTermsApiResponse, AcceptTermsApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/gcu`, method: "POST", body: queryArg.termsRequest }),
    }),
    health: build.query<HealthApiResponse, HealthApiArg>({
      query: () => ({ url: `/fred-manager/v1/healthz` }),
    }),
    importBlueprint: build.mutation<ImportBlueprintApiResponse, ImportBlueprintApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/import-export/import`,
        method: "POST",
        body: queryArg.provisioningUpload,
      }),
    }),
    me: build.query<MeApiResponse, MeApiArg>({
      query: () => ({ url: `/fred-manager/v1/me` }),
    }),
    onboardingStatus: build.query<OnboardingStatusApiResponse, OnboardingStatusApiArg>({
      query: () => ({ url: `/fred-manager/v1/me/onboarding` }),
    }),
    createPersonalSpace: build.mutation<CreatePersonalSpaceApiResponse, CreatePersonalSpaceApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/me/personal-space`,
        method: "POST",
        body: queryArg.createPersonalSpace,
      }),
    }),
    mySpaces: build.query<MySpacesApiResponse, MySpacesApiArg>({
      query: () => ({ url: `/fred-manager/v1/me/spaces` }),
    }),
    createSpace: build.mutation<CreateSpaceApiResponse, CreateSpaceApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/spaces`, method: "POST", body: queryArg.createSpace }),
    }),
    deleteSpace: build.mutation<DeleteSpaceApiResponse, DeleteSpaceApiArg>({
      query: (queryArg) => ({ url: `/fred-manager/v1/spaces/${queryArg.id}`, method: "DELETE" }),
    }),
    listDocuments: build.query<ListDocumentsApiResponse, ListDocumentsApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/spaces/${queryArg.id}/documents`,
        params: {
          folder_id: queryArg.folderId,
          after_name: queryArg.afterName,
          after_id: queryArg.afterId,
          limit: queryArg.limit,
        },
      }),
    }),
    listFolders: build.query<ListFoldersApiResponse, ListFoldersApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/spaces/${queryArg.id}/folders`,
        params: {
          parent_id: queryArg.parentId,
        },
      }),
    }),
    grant: build.mutation<GrantApiResponse, GrantApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/spaces/${queryArg.id}/roles/${queryArg.role}/${queryArg.user}`,
        method: "PUT",
      }),
    }),
    revoke: build.mutation<RevokeApiResponse, RevokeApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/spaces/${queryArg.id}/roles/${queryArg.role}/${queryArg.user}`,
        method: "DELETE",
      }),
    }),
    listPlatformRoles: build.query<ListPlatformRolesApiResponse, ListPlatformRolesApiArg>({
      query: () => ({ url: `/fred-manager/v1/users/platform-roles` }),
    }),
    grantPlatformRole: build.mutation<GrantPlatformRoleApiResponse, GrantPlatformRoleApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/users/${queryArg.user}/platform-roles/${queryArg.role}`,
        method: "PUT",
      }),
    }),
    revokePlatformRole: build.mutation<RevokePlatformRoleApiResponse, RevokePlatformRoleApiArg>({
      query: (queryArg) => ({
        url: `/fred-manager/v1/users/${queryArg.user}/platform-roles/${queryArg.role}`,
        method: "DELETE",
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as fredManagerApi };
export type TeamRegistryApiResponse = /** status 200 Success */ Space[];
export type TeamRegistryApiArg = {
  /** Exclusive UUID cursor; at most 100 non-personal teams, ordered by ID. */
  after?: string;
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
export type CreateDocumentApiResponse = /** status 201 Success */ CreatedDocument;
export type CreateDocumentApiArg = {
  createDocument: CreateDocument;
};
export type GetDocumentApiResponse = /** status 200 Success */ Document;
export type GetDocumentApiArg = {
  id: string;
};
export type DeleteDocumentApiResponse = unknown;
export type DeleteDocumentApiArg = {
  id: string;
};
export type RenameDocumentApiResponse = unknown;
export type RenameDocumentApiArg = {
  id: string;
  rename: Rename;
};
export type IngestDocumentApiResponse = unknown;
export type IngestDocumentApiArg = {
  id: string;
  ingestRequest?: IngestRequest;
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
export type ListDocumentsApiResponse = /** status 200 Success */ Document[];
export type ListDocumentsApiArg = {
  id: string;
  folderId?: string;
  afterName?: string;
  afterId?: string;
  /** Defaults to 50; clamped to 1..200. Both cursor fields must be supplied together. */
  limit?: number;
};
export type ListFoldersApiResponse = /** status 200 Success */ Folder[];
export type ListFoldersApiArg = {
  id: string;
  parentId?: string;
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
export type ListPlatformRolesApiResponse = /** status 200 Success */ Grant[];
export type ListPlatformRolesApiArg = void;
export type GrantPlatformRoleApiResponse = unknown;
export type GrantPlatformRoleApiArg = {
  user: string;
  /** Also accepts the owner and observer aliases. */
  role: PlatformRole;
};
export type RevokePlatformRoleApiResponse = unknown;
export type RevokePlatformRoleApiArg = {
  user: string;
  /** Also accepts the owner and observer aliases. */
  role: PlatformRole;
};
export type SpaceKind = "organization" | "team" | "project";
export type Space = {
  id: string;
  kind: SpaceKind;
  name: string;
  parent_id: string | null;
  /** Ancestors then self: the search scope. A personal space's path is itself. */
  path: string[];
  personal_owner: string | null;
};
export type ErrorBody = {
  detail: string;
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
  | "own"
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
export type Receipt = {
  actor_subject: string;
  completed_at?: string | null;
  due_at: string;
  error_code?: string | null;
  folders_deleted: number;
  id: string;
  mode: string;
  organization_id: string;
  requested_at: string;
  rule_id?: string | null;
  spaces_deleted: number;
  status: Status;
  target_id: string;
  target_kind: SpaceKind;
  target_parent_id?: string | null;
};
export type Document = {
  created_by: string;
  folder_id: string | null;
  id: string;
  mime: string;
  name: string;
  sha256: string;
  size: number;
  space_id: string;
};
export type CreatedDocument = Document & {
  source_key: string;
  storage_prefix: string;
};
export type CreateDocument = {
  folder_id?: string | null;
  mime: string;
  name: string;
  sha256: string;
  size: number;
  space_id: string;
};
export type Rename = {
  name: string;
};
export type IngestRequest = {
  profile?: string | null;
};
export type Folder = {
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
export type Role = "member" | "editor" | "admin" | "analyst" | "owner" | "personal_space_creator";
export type MySpace = Space & {
  /** The subset of `roles` held only through an ancestor. */
  inherited_roles: Role[];
  organization_id: string;
  /** Effective roles, including those descending from an ancestor. */
  roles: Role[];
};
export type CreateSpace = {
  /** Initial administrator; creation grants the caller nothing on the new space. */
  admin: string;
  kind: SpaceKind;
  name: string;
  parent_id: string;
};
export type Grant = {
  role: PlatformRole;
  user_id: string;
};
export const {
  useTeamRegistryQuery,
  useLazyTeamRegistryQuery,
  useAuthorizeDocumentMutation,
  useAuthorizePlatformMutation,
  useAuthorizeScopeMutation,
  useAuthorizeSpaceMutation,
  useBootstrapPlatformAdminMutation,
  useDeletionStatusQuery,
  useLazyDeletionStatusQuery,
  useCreateDocumentMutation,
  useGetDocumentQuery,
  useLazyGetDocumentQuery,
  useDeleteDocumentMutation,
  useRenameDocumentMutation,
  useIngestDocumentMutation,
  useCreateFolderMutation,
  useDeleteFolderMutation,
  useRenameFolderMutation,
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
  useCreateSpaceMutation,
  useDeleteSpaceMutation,
  useListDocumentsQuery,
  useLazyListDocumentsQuery,
  useListFoldersQuery,
  useLazyListFoldersQuery,
  useGrantMutation,
  useRevokeMutation,
  useListPlatformRolesQuery,
  useLazyListPlatformRolesQuery,
  useGrantPlatformRoleMutation,
  useRevokePlatformRoleMutation,
} = injectedRtkApi;
