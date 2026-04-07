// NOT GENERATED. Safe to edit.
import { controlPlaneApi as api } from "./controlPlaneOpenApi";

export const enhancedControlPlaneApi = api.enhanceEndpoints({
  addTagTypes: ["ControlPlaneTeam", "ControlPlaneTeamMember", "ControlPlaneUser"],
  endpoints: {
    listUsersControlPlaneV1UsersGet: {
      providesTags: [{ type: "ControlPlaneUser", id: "LIST" }],
    },
    listTeamsControlPlaneV1TeamsGet: {
      providesTags: (result) =>
        result
          ? [
              ...result.map((team) => ({ type: "ControlPlaneTeam" as const, id: team.id })),
              { type: "ControlPlaneTeam" as const, id: "LIST" },
            ]
          : [{ type: "ControlPlaneTeam" as const, id: "LIST" }],
    },
    getTeamControlPlaneV1TeamsTeamIdGet: {
      providesTags: (_, __, arg) => [{ type: "ControlPlaneTeam", id: arg.teamId }],
    },
    updateTeamControlPlaneV1TeamsTeamIdPatch: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeam", id: arg.teamId },
        { type: "ControlPlaneTeam", id: "LIST" },
      ],
    },
    uploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeam", id: arg.teamId },
        { type: "ControlPlaneTeam", id: "LIST" },
      ],
    },
    listTeamMembersControlPlaneV1TeamsTeamIdMembersGet: {
      providesTags: (result, _, arg) =>
        result
          ? [
              ...result.map((member) => ({
                type: "ControlPlaneTeamMember" as const,
                id: `${arg.teamId}-${member.user.id}`,
              })),
              { type: "ControlPlaneTeamMember" as const, id: `LIST-${arg.teamId}` },
            ]
          : [{ type: "ControlPlaneTeamMember" as const, id: `LIST-${arg.teamId}` }],
    },
    addTeamMemberControlPlaneV1TeamsTeamIdMembersPost: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    },
    updateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatch: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `${arg.teamId}-${arg.userId}` },
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    },
    removeTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDelete: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `${arg.teamId}-${arg.userId}` },
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    },
  },
});

export const {
  useListUsersControlPlaneV1UsersGetQuery: useListUsersQuery,
  useListTeamsControlPlaneV1TeamsGetQuery: useListTeamsQuery,
  useGetTeamControlPlaneV1TeamsTeamIdGetQuery: useGetTeamQuery,
  useUpdateTeamControlPlaneV1TeamsTeamIdPatchMutation: useUpdateTeamMutation,
  useUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostMutation: useUploadTeamBannerMutation,
  useListTeamMembersControlPlaneV1TeamsTeamIdMembersGetQuery: useListTeamMembersQuery,
  useAddTeamMemberControlPlaneV1TeamsTeamIdMembersPostMutation: useAddTeamMemberMutation,
  useUpdateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatchMutation: useUpdateTeamMemberMutation,
  useRemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteMutation: useRemoveTeamMemberMutation,
} = enhancedControlPlaneApi;
