import PersonAddAlt1OutlinedIcon from "@mui/icons-material/PersonAddAlt1Outlined";
import { Avatar, IconButton, List, ListItem, ListItemAvatar, ListItemText, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  ShareTargetResource,
  useListUsersKnowledgeFlowV1UsersGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface DocumentLibraryShareUsersListProps {
  searchQuery: string;
  selectedIds: Set<string>;
  disabled?: boolean;
  onAdd: (target_id: string, target_type: ShareTargetResource, displayName: string) => void;
}

export function DocumentLibraryShareUsersList({
  searchQuery,
  selectedIds,
  disabled = false,
  onAdd,
}: DocumentLibraryShareUsersListProps) {
  const { t } = useTranslation();
  const { data: users = [], isLoading } = useListUsersKnowledgeFlowV1UsersGetQuery();

  const filteredUsers = React.useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return users;

    return users.filter((user) => {
      const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
      const fields = [user.username ?? "", fullName, user.id];
      return fields.some((field) => field.toLowerCase().includes(query));
    });
  }, [searchQuery, users]);

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
        const alreadySelected = selectedIds.has(user.id);

        return (
          <ListItem
            key={user.id}
            secondaryAction={
              <IconButton
                edge="end"
                onClick={() => onAdd(user.id, "user", fullName)}
                disabled={disabled || alreadySelected}
              >
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
