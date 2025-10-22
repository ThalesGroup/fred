import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import GroupAddOutlinedIcon from "@mui/icons-material/GroupAddOutlined";
import { Avatar, Box, Collapse, IconButton, List, ListItem, ListItemText, Typography } from "@mui/material";
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
  const { data: groups = [], isLoading } = useListGroupsKnowledgeFlowV1GroupsGetQuery();
  const [expandedGroups, setExpandedGroups] = React.useState<Record<string, boolean>>({});

  const toggleGroup = React.useCallback((groupId: string) => {
    setExpandedGroups((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  }, []);

  const filterGroups = React.useCallback(
    (items: GroupSummary[]): GroupSummary[] => {
      const query = searchQuery.trim().toLowerCase();
      if (!query) return items;

      const walk = (nodes: GroupSummary[]): GroupSummary[] =>
        nodes.flatMap((node) => {
          const children = node.sub_groups ? walk(node.sub_groups) : undefined;
          const matchesSelf = node.name.toLowerCase().includes(query);
          const hasChildMatches = !!children && children.length > 0;

          if (!matchesSelf && !hasChildMatches) {
            return [];
          }

          const next: GroupSummary = {
            ...node,
            sub_groups: hasChildMatches ? children : undefined,
          };

          return [next];
        });

      return walk(items);
    },
    [searchQuery],
  );

  const filteredGroups = React.useMemo(() => filterGroups(groups), [filterGroups, groups]);

  const renderGroupNodes = React.useCallback(
    (nodes: GroupSummary[], depth = 0): React.ReactNode =>
      nodes.map((group) => {
        const hasChildren = !!group.sub_groups && group.sub_groups.length > 0;
        const isExpanded = expandedGroups[group.id] || searchQuery.trim().length > 0;
        const indent = depth * 2;
        const disabledForGroup = disabled || selectedIds.has(group.id);

        return (
          <React.Fragment key={group.id}>
            <ListItem
              disableGutters
              sx={{
                pl: (theme) => theme.spacing(1 + indent),
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
              {hasChildren ? (
                <IconButton size="small" edge="start" onClick={() => toggleGroup(group.id)}>
                  {isExpanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                </IconButton>
              ) : (
                <Box sx={{ width: 32 }} />
              )}
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
                    defaultValue: "{{count}} members",
                  })}
                />
              </Box>
            </ListItem>
            {hasChildren ? (
              <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                <List disablePadding>{renderGroupNodes(group.sub_groups ?? [], depth + 1)}</List>
              </Collapse>
            ) : null}
          </React.Fragment>
        );
      }),
    [disabled, expandedGroups, onAdd, searchQuery, selectedIds, t, toggleGroup],
  );

  if (isLoading) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.loadingGroups", { defaultValue: "Loading groups…" })}
      </Typography>
    );
  }

  if (!filteredGroups.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.noGroupMatches", { defaultValue: "No groups found." })}
      </Typography>
    );
  }

  return <List disablePadding>{renderGroupNodes(filteredGroups)}</List>;
}
