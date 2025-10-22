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

  const theme = useTheme();
  const overlayColor = theme.palette.mode === "light" ? alpha("#000", 0.1) : alpha("#fff", 0.1);

  const filteredUsers = React.useMemo(() => {
    return users.filter((user) => {
      // Remove already selected users
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
  }, [searchQuery, users, selectedIds]);

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
