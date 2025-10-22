import PersonAddAlt1OutlinedIcon from "@mui/icons-material/PersonAddAlt1Outlined";
import {
  alpha,
  Avatar,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Typography,
  useTheme,
} from "@mui/material";
import * as React from "react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  ShareTargetResource,
  useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
  useListUsersKnowledgeFlowV1UsersGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../../ToastProvider";

interface DocumentLibraryShareUsersListProps {
  searchQuery: string;
  selectedIds: Set<string>;
  disabled?: boolean;
  onAdd: (target_id: string, target_type: ShareTargetResource, displayName: string) => void;
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
      showError(t("documentLibraryShareDialog.errorFetchingMembers", { defaultValue: "Error fetching tag members." }));
    }
  }, [errorFetchingMembers]);

  useEffect(() => {
    if (errorFetchingUsers) {
      console.error("Error fetching users:", errorFetchingUsers);
      showError(t("documentLibraryShareDialog.errorFetchingUsers", { defaultValue: "Error fetching users." }));
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
        {t("documentLibraryShareDialog.loadingUsers", { defaultValue: "Loading users…" })}
      </Typography>
    );
  }

  if (!filteredUsers.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.noUserMatches", { defaultValue: "No users found." })}
      </Typography>
    );
  }

  return (
    <List dense disablePadding>
      {filteredUsers.map((user) => {
        const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
        const primary = fullName || user.username || user.id;
        const secondary = user.username && fullName ? user.username : undefined;

        return (
          <ListItem
            sx={{
              height: 60,
              cursor: disabled ? "default" : "pointer",
              "&:hover": { backgroundColor: disabled ? "transparent" : overlayColor },
            }}
            key={user.id}
            onClick={() => onAdd(user.id, "user", fullName)}
            secondaryAction={
              <IconButton edge="end" disabled={disabled}>
                <PersonAddAlt1OutlinedIcon fontSize="small" />
              </IconButton>
            }
          >
            <ListItemAvatar>
              <Avatar>{primary.charAt(0).toUpperCase()}</Avatar>
            </ListItemAvatar>
            <ListItemText primary={primary} secondary={secondary} />
          </ListItem>
        );
      })}
    </List>
  );
}
