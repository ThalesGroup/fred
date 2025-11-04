import PersonAddAlt1OutlinedIcon from "@mui/icons-material/PersonAddAlt1Outlined";
import { alpha, IconButton, List, Typography, useTheme } from "@mui/material";
import * as React from "react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
  useListUsersKnowledgeFlowV1UsersGetQuery,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../../../ToastProvider";
import { DocumentLibraryPendingRecipient } from "./DocumentLibraryShareTypes";
import { UserListItem } from "./UserListItem";

interface DocumentLibraryShareUsersListProps {
  searchQuery: string;
  selectedIds: Set<string>;
  disabled?: boolean;
  onAdd: (newRecipient: DocumentLibraryPendingRecipient) => void;
  tagId: string;
}

export function DocumentLibraryShareUsersList({
  searchQuery,
  selectedIds,
  disabled = false,
  onAdd,
  tagId,
}: DocumentLibraryShareUsersListProps) {
  const { t } = useTranslation();

  const theme = useTheme();
  const overlayColor = theme.palette.mode === "light" ? alpha("#000", 0.1) : alpha("#fff", 0.1);

  // Get list of all users
  const {
    data: users = [],
    isLoading: isLoadingUsers,
    error: errorFetchingUsers,
  } = useListUsersKnowledgeFlowV1UsersGetQuery();
  // Get list of members of the tag
  const {
    data: members,
    isLoading: isLoadingMembers,
    error: errorFetchingMembers,
  } = useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery({ tagId: tagId ?? "" }, { skip: !open || !tagId });

  // Handle fetching errors
  const { showError } = useToast();

  useEffect(() => {
    if (errorFetchingMembers) {
      console.error("Error fetching tag members:", errorFetchingMembers);
      showError(t("documentLibraryShareDialog.errorFetchingMembers"));
    }
  }, [errorFetchingMembers]);

  useEffect(() => {
    if (errorFetchingUsers) {
      console.error("Error fetching users:", errorFetchingUsers);
      showError(t("documentLibraryShareDialog.errorFetchingUsers"));
    }
  }, [errorFetchingUsers]);

  // Filter usrers
  const filteredUsers = React.useMemo(() => {
    return users.filter((user) => {
      // Remove user already members of the tag
      const isMember = members?.users.some((member) => member.user.id === user.id);
      if (isMember) {
        return false;
      }

      // Remove users already selected
      const isSelected = selectedIds.has(user.id);
      if (isSelected) {
        return false;
      }

      // Apply search filter
      const query = searchQuery.trim().toLowerCase();
      if (!query) {
        return true;
      }

      const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
      const fields = [user.username ?? "", fullName, user.id];
      const isSearched = fields.some((field) => field.toLowerCase().includes(query));

      return isSearched;
    });
  }, [searchQuery, users, selectedIds, members]);

  const isLoading = isLoadingUsers || isLoadingMembers;
  if (isLoading) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.loadingUsers")}
      </Typography>
    );
  }

  if (!filteredUsers.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.noUserMatches")}
      </Typography>
    );
  }

  return (
    <List dense disablePadding>
      {filteredUsers.map((user) => {
        return (
          <UserListItem
            sx={{
              cursor: disabled ? "default" : "pointer",
              "&:hover": { backgroundColor: disabled ? "transparent" : overlayColor },
            }}
            user={user}
            onClick={() => onAdd({ target_id: user.id, target_type: "user", relation: "viewer", data: user })}
            secondaryAction={
              <IconButton edge="end" disabled={disabled}>
                <PersonAddAlt1OutlinedIcon fontSize="small" />
              </IconButton>
            }
          />
        );
      })}
    </List>
  );
}
