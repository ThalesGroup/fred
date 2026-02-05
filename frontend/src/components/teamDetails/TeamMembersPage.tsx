import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  Autocomplete,
  Box,
  CircularProgress,
  IconButton,
  InputAdornment,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetQuery,
  useRemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteMutation,
  useUpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowApiEnhancements";
import {
  TeamPermission,
  useAddTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPostMutation,
  useListUsersKnowledgeFlowV1UsersGetQuery,
  UserSummary,
  UserTeamRelation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";

const TEAM_ROLES: UserTeamRelation[] = ["owner", "manager", "member"];

const ROLE_PRIORITY: Record<UserTeamRelation, number> = {
  owner: 0,
  manager: 1,
  member: 2,
};

export interface TeamMembersPageProps {
  teamId: string;
  permissions?: TeamPermission[];
}

export function TeamMembersPage({ teamId, permissions }: TeamMembersPageProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [inputValue, setInputValue] = useState("");

  const { data: members } = useListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetQuery({ teamId: teamId });
  // todo: handle loading
  // todo: handle error
  // todo: handle empty state

  const [updateTeamMember] = useUpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchMutation();
  const [removeTeamMember] = useRemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteMutation();
  const [addTeamMember, { isLoading: isAddingMember }] =
    useAddTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPostMutation();

  const { data: users } = useListUsersKnowledgeFlowV1UsersGetQuery();

  const membersId = members?.map((m) => m.user.id);
  const usersNotInTeam = membersId && users?.filter((u) => !membersId.includes(u.id));

  const sortedMembers = members?.slice().sort((a, b) => {
    const roleDiff = ROLE_PRIORITY[a.relation] - ROLE_PRIORITY[b.relation];
    if (roleDiff !== 0) return roleDiff;

    const compare = (valA: string | null | undefined, valB: string | null | undefined): number => {
      if (!valA && !valB) return 0;
      if (!valA) return 1;
      if (!valB) return -1;
      return valA.localeCompare(valB);
    };

    return (
      compare(a.user.last_name, b.user.last_name) ||
      compare(a.user.first_name, b.user.first_name) ||
      compare(a.user.username, b.user.username)
    );
  });

  const handleRoleChange = async (userId: string, newRelation: UserTeamRelation) => {
    await updateTeamMember({
      teamId,
      userId,
      updateTeamMemberRequest: { relation: newRelation },
    });
  };

  const handleRemoveMember = async (userId: string) => {
    showConfirmationDialog({
      criticalAction: true,
      title: t("teamMembersPage.removeMemberConfonfirmationDialog.title"),
      message: t("teamMembersPage.removeMemberConfonfirmationDialog.message"),
      confirmButtonLabel: t("teamMembersPage.removeMemberConfonfirmationDialog.confirmButtonLabel"),
      onConfirm: async () => {
        await removeTeamMember({
          teamId,
          userId,
        });
      },
    });
  };

  const handleAddMember = async (userToAdd: UserSummary | null | undefined) => {
    if (!userToAdd || isAddingMember) return;

    setInputValue(""); // Clear immediately

    await addTeamMember({
      teamId,
      addTeamMemberRequest: {
        user_id: userToAdd.id,
        relation: "member", // Default role
      },
    });
  };

  const can_administer_members = permissions?.includes("can_administer_members");
  const can_administer_managers = permissions?.includes("can_administer_managers");
  const can_administer_owners = permissions?.includes("can_administer_owners");

  const can_administer_anyone = can_administer_members || can_administer_managers || can_administer_owners;

  function getAdministerPermissionForTeamRole(target: UserTeamRelation): boolean | undefined {
    if (target === "manager") return can_administer_managers;
    if (target === "owner") return can_administer_owners;
    return can_administer_members;
  }

  return (
    <Box sx={{ px: 2, pb: 2, display: "flex", height: "100%" }}>
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        {/* Header */}
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 2, py: 1 }}>
          <Box sx={{ display: "flex", alignItems: "center", height: "3rem", gap: 0.75, px: 2 }}>
            <Typography variant="body2" color="textSecondary">
              {t("teamMembersPage.headerTitle")}
            </Typography>
            <Tooltip
              title={t("teamMembersPage.headerInfoTooltip")}
              placement="top"
              slotProps={{
                popper: {
                  modifiers: [
                    {
                      name: "offset",
                      options: {
                        offset: [0, -12],
                      },
                    },
                  ],
                },
              }}
            >
              <InfoOutlinedIcon fontSize="small" color="disabled" />
            </Tooltip>
          </Box>

          {/* Add team member bar */}
          {can_administer_members && (
            <Autocomplete
              options={usersNotInTeam || []}
              getOptionLabel={(user) => `${user.first_name} ${user.last_name} (${user.username})`}
              id="free-solo-2-demo"
              size="small"
              sx={{ maxWidth: "280px", flex: 1 }}
              value={null}
              inputValue={inputValue}
              onInputChange={(_event, newInputValue) => setInputValue(newInputValue)}
              onChange={(_event, value) => handleAddMember(value)}
              disabled={isAddingMember}
              renderInput={(params) => (
                <TextField
                  {...params}
                  placeholder={t("teamMembersPage.addUserInputPlaceholder")}
                  slotProps={{
                    input: {
                      ...params.InputProps,
                      endAdornment: undefined,
                      startAdornment: (
                        <InputAdornment position="start">
                          {isAddingMember ? (
                            <CircularProgress size={20} sx={{ color: theme.palette.text.secondary }} />
                          ) : (
                            <AddIcon sx={{ color: theme.palette.text.secondary }} />
                          )}
                        </InputAdornment>
                      ),
                    },
                  }}
                />
              )}
            />
          )}
        </Box>

        {/* Table */}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t("teamMembersPage.tableHeader.username")}</TableCell>
              <TableCell>{t("teamMembersPage.tableHeader.firstName")}</TableCell>
              <TableCell>{t("teamMembersPage.tableHeader.lastName")}</TableCell>
              <TableCell>{t("teamMembersPage.tableHeader.role")}</TableCell>
              {can_administer_anyone && <TableCell>{t("teamMembersPage.tableHeader.actions")}</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedMembers &&
              sortedMembers.map((member) => {
                const can_administer_this_member = getAdministerPermissionForTeamRole(member.relation);

                return (
                  <TableRow key={member.user.id}>
                    <TableCell>{member.user.username}</TableCell>
                    <TableCell>{member.user.first_name}</TableCell>
                    <TableCell>{member.user.last_name}</TableCell>
                    <TableCell>
                      {can_administer_this_member && (
                        <Select<UserTeamRelation>
                          value={member.relation}
                          size="small"
                          onChange={(event) => handleRoleChange(member.user.id, event.target.value as UserTeamRelation)} // not sure why casting was necessary...
                        >
                          {TEAM_ROLES.map((role) => {
                            const can_assign_role = getAdministerPermissionForTeamRole(role);
                            if (!can_assign_role) {
                              return;
                            }

                            return (
                              <MenuItem key={role} value={role}>
                                {t(`teamMembersPage.teamRole.${role}`)}
                              </MenuItem>
                            );
                          })}
                        </Select>
                      )}
                      {!can_administer_this_member && (
                        <Typography>{t(`teamMembersPage.teamRole.${member.relation}`)}</Typography>
                      )}
                    </TableCell>
                    {can_administer_anyone && (
                      <TableCell>
                        {can_administer_this_member && (
                          <IconButton size="small" onClick={() => handleRemoveMember(member.user.id)} color="error">
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
