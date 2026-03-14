import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

export type TeamPermission =
  | "can_read"
  | "can_update_info"
  | "can_update_resources"
  | "can_update_agents"
  | "can_read_members"
  | "can_administer_members"
  | "can_administer_managers"
  | "can_administer_owners";

export type UserTeamRelation = "owner" | "manager" | "member";

export interface UserSummary {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  username?: string | null;
}

export interface Team {
  id: string;
  name: string;
  member_count?: number | null;
  owners?: UserSummary[];
  is_member?: boolean;
  description?: string | null;
  is_private?: boolean;
  banner_image_url?: string | null;
}

export interface TeamWithPermissions extends Team {
  permissions?: TeamPermission[];
}

export interface TeamMember {
  type: "user";
  relation: UserTeamRelation;
  user: UserSummary;
}

export interface UpdateTeamRequest {
  description?: string | null;
  is_private?: boolean | null;
  banner_image_url?: string | null;
}

export interface RemoveTeamMemberResponse {
  status: "accepted";
  team_id: string;
  user_id: string;
  sessions_enqueued: number;
  scheduled_delete_at: string;
  policy_mode: string;
  retention_seconds: number;
  matched_rule_id?: string | null;
}

export const controlPlaneApi = createApi({
  reducerPath: "controlPlaneApi",
  baseQuery: createDynamicBaseQuery({ backend: "controlPlane" }),
  keepUnusedDataFor: 0,
  refetchOnMountOrArgChange: true,
  refetchOnFocus: true,
  refetchOnReconnect: true,
  tagTypes: ["ControlPlaneTeam", "ControlPlaneTeamMember", "ControlPlaneUser"],
  endpoints: (build) => ({
    listUsers: build.query<UserSummary[], void>({
      query: () => ({ url: "/control-plane/v1/users" }),
      providesTags: [{ type: "ControlPlaneUser", id: "LIST" }],
    }),
    listTeams: build.query<Team[], void>({
      query: () => ({ url: "/control-plane/v1/teams" }),
      providesTags: (result) =>
        result
          ? [
              ...result.map((team) => ({
                type: "ControlPlaneTeam" as const,
                id: team.id,
              })),
              { type: "ControlPlaneTeam" as const, id: "LIST" },
            ]
          : [{ type: "ControlPlaneTeam" as const, id: "LIST" }],
    }),
    getTeam: build.query<TeamWithPermissions, { teamId: string }>({
      query: ({ teamId }) => ({ url: `/control-plane/v1/teams/${teamId}` }),
      providesTags: (_, __, arg) => [{ type: "ControlPlaneTeam", id: arg.teamId }],
    }),
    updateTeam: build.mutation<TeamWithPermissions, { teamId: string; updateTeamRequest: UpdateTeamRequest }>({
      query: ({ teamId, updateTeamRequest }) => ({
        url: `/control-plane/v1/teams/${teamId}`,
        method: "PATCH",
        body: updateTeamRequest,
      }),
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeam", id: arg.teamId },
        { type: "ControlPlaneTeam", id: "LIST" },
      ],
    }),
    uploadTeamBanner: build.mutation<void, { teamId: string; file: File }>({
      query: ({ teamId, file }) => {
        const formData = new FormData();
        formData.append("file", file);
        return {
          url: `/control-plane/v1/teams/${teamId}/banner`,
          method: "POST",
          body: formData,
        };
      },
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeam", id: arg.teamId },
        { type: "ControlPlaneTeam", id: "LIST" },
      ],
    }),
    listTeamMembers: build.query<TeamMember[], { teamId: string }>({
      query: ({ teamId }) => ({
        url: `/control-plane/v1/teams/${teamId}/members`,
      }),
      providesTags: (result, _, arg) =>
        result
          ? [
              ...result.map((member) => ({
                type: "ControlPlaneTeamMember" as const,
                id: `${arg.teamId}-${member.user.id}`,
              })),
              {
                type: "ControlPlaneTeamMember" as const,
                id: `LIST-${arg.teamId}`,
              },
            ]
          : [{ type: "ControlPlaneTeamMember" as const, id: `LIST-${arg.teamId}` }],
    }),
    addTeamMember: build.mutation<
      void,
      { teamId: string; addTeamMemberRequest: { user_id: string; relation: UserTeamRelation } }
    >({
      query: ({ teamId, addTeamMemberRequest }) => ({
        url: `/control-plane/v1/teams/${teamId}/members`,
        method: "POST",
        body: addTeamMemberRequest,
      }),
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    }),
    updateTeamMember: build.mutation<
      void,
      { teamId: string; userId: string; updateTeamMemberRequest: { relation: UserTeamRelation } }
    >({
      query: ({ teamId, userId, updateTeamMemberRequest }) => ({
        url: `/control-plane/v1/teams/${teamId}/members/${userId}`,
        method: "PATCH",
        body: updateTeamMemberRequest,
      }),
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `${arg.teamId}-${arg.userId}` },
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    }),
    removeTeamMember: build.mutation<RemoveTeamMemberResponse, { teamId: string; userId: string }>({
      query: ({ teamId, userId }) => ({
        url: `/control-plane/v1/teams/${teamId}/members/${userId}`,
        method: "DELETE",
      }),
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `${arg.teamId}-${arg.userId}` },
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    }),
  }),
});

export const {
  useListUsersQuery,
  useListTeamsQuery,
  useGetTeamQuery,
  useUpdateTeamMutation,
  useUploadTeamBannerMutation,
  useListTeamMembersQuery,
  useAddTeamMemberMutation,
  useUpdateTeamMemberMutation,
  useRemoveTeamMemberMutation,
} = controlPlaneApi;
