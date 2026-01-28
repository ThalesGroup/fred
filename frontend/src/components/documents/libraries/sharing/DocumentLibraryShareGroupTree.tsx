import GroupAddOutlinedIcon from "@mui/icons-material/GroupAddOutlined";
import { Avatar, Box, IconButton, List, ListItem, ListItemText, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  GroupSummary,
  useListGroupsKnowledgeFlowV1GroupsGetQuery,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryPendingRecipient } from "./DocumentLibraryShareTypes";

interface DocumentLibraryShareGroupTreeProps {
  searchQuery: string;
  selectedIds: Set<string>;
  disabled?: boolean;
  onAdd: (newRecipient: DocumentLibraryPendingRecipient) => void;
}

export function DocumentLibraryShareGroupTree({
  searchQuery,
  selectedIds,
  disabled = false,
  onAdd,
}: DocumentLibraryShareGroupTreeProps) {
  const { t } = useTranslation();
  const { data: groups = [], isLoading } = useListGroupsKnowledgeFlowV1GroupsGetQuery({
    limit: 10000,
    offset: 0,
    memberOnly: true,
  });

  const filterGroups = React.useCallback(
    (items: GroupSummary[]): GroupSummary[] => {
      const query = searchQuery.trim().toLowerCase();
      if (!query) return items;
      return items.filter((g) => g.name.toLowerCase().includes(query));
    },
    [searchQuery],
  );

  const filteredGroups = React.useMemo(() => filterGroups(groups), [filterGroups, groups]);

  const renderGroupNodes = React.useCallback(
    (nodes: GroupSummary[]): React.ReactNode =>
      nodes.map((group) => {
        const disabledForGroup = disabled || selectedIds.has(group.id);

        return (
          <ListItem
            key={group.id}
            disableGutters
            sx={{
              pl: (theme) => theme.spacing(1),
              pr: 1,
              gap: 1,
              alignItems: "center",
              height: 60,
            }}
            secondaryAction={
              <IconButton
                edge="end"
                onClick={() => onAdd({ target_id: group.id, target_type: "group", relation: "viewer", data: group })}
                disabled={disabledForGroup}
                size="small"
              >
                <GroupAddOutlinedIcon fontSize="small" />
              </IconButton>
            }
          >
            <Box sx={{ width: 32 }} />
            <Box
              onClick={() => onAdd({ target_id: group.id, target_type: "group", relation: "viewer", data: group })}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1,
                flex: 1,
                borderRadius: 1,
                cursor: disabledForGroup ? "default" : "pointer",
                opacity: disabledForGroup ? 0.6 : 1,
                "&:hover": disabledForGroup
                  ? undefined
                  : {
                      bgcolor: "action.hover",
                    },
              }}
            >
              <Avatar variant="rounded" sx={{ width: 32, height: 32 }}>
                {group.name.charAt(0).toUpperCase()}
              </Avatar>
              <ListItemText
                primary={group.name}
                secondary={t("documentLibraryShareDialog.groupMembersCount", {
                  count: group.total_member_count ?? group.member_count ?? 0,
                })}
              />
            </Box>
          </ListItem>
        );
      }),
    [disabled, onAdd, selectedIds, t],
  );

  if (isLoading) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.loadingGroups")}
      </Typography>
    );
  }

  if (!filteredGroups.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.noGroupMatches")}
      </Typography>
    );
  }

  return <List disablePadding>{renderGroupNodes(filteredGroups)}</List>;
}
