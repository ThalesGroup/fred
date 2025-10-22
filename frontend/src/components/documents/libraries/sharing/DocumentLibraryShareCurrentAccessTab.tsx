import { Avatar, Box, CircularProgress, List, ListItem, ListItemAvatar, ListItemText, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  GroupSummary,
  TagMemberGroup,
  TagMemberUser,
  TagWithItemsId,
  UserSummary,
  UserTagRelation,
  useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

const relationPriority = {
  owner: 0,
  editor: 1,
  viewer: 2,
};

const getUserDisplayName = (user: UserSummary): string => {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  return user.username ?? (fullName || user.id);
};

const getGroupDisplayName = (group: GroupSummary): string => {
  return group.name ?? group.id;
};

const sortMembers = <T extends { relation: UserTagRelation }>(list: T[], getKey: (item: T) => string) => {
  return [...list].sort((a, b) => {
    // Sort by relation first
    const relationDiff = relationPriority[a.relation] - relationPriority[b.relation];
    if (relationDiff !== 0) {
      return relationDiff;
    }
    // If relation is the same, sort by name
    return getKey(a).localeCompare(getKey(b), undefined, { sensitivity: "base" });
  });
};

const getInitial = (value: string): string => {
  const trimmed = value.trim();
  return trimmed ? trimmed.charAt(0).toUpperCase() : "?";
};

interface DocumentLibraryShareCurrentAccessTabProps {
  tag?: TagWithItemsId;
  open: boolean;
}

export function DocumentLibraryShareCurrentAccessTab({ tag, open }: DocumentLibraryShareCurrentAccessTabProps) {
  const { t } = useTranslation();

  const tagId = tag?.id;
  const {
    data: members,
    isLoading,
    isError,
  } = useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery(
    { tagId: tagId ?? "" },
    { skip: !open || !tagId, refetchOnMountOrArgChange: true },
  );

  const relationLabels = React.useMemo<Record<UserTagRelation, string>>(
    () => ({
      owner: t("documentLibraryShareDialog.relation.owner", { defaultValue: "Owner" }),
      editor: t("documentLibraryShareDialog.relation.editor", { defaultValue: "Editor" }),
      viewer: t("documentLibraryShareDialog.relation.viewer", { defaultValue: "Viewer" }),
    }),
    [t],
  );

  const users = React.useMemo<TagMemberUser[]>(() => {
    return sortMembers(members?.users ?? [], (member) => getUserDisplayName(member.user));
  }, [members?.users, getUserDisplayName, sortMembers]);

  const groups = React.useMemo<TagMemberGroup[]>(() => {
    return sortMembers(members?.groups ?? [], (member) => getGroupDisplayName(member.group));
  }, [members?.groups, getGroupDisplayName, sortMembers]);

  const renderMemberSection = React.useCallback(
    <T extends { relation: UserTagRelation }>(
      title: string,
      items: T[],
      getKey: (item: T) => string,
      getPrimaryText: (item: T) => string,
    ) => {
      if (!items.length) return null;

      return (
        <Box component="section" key={title}>
          <Typography variant="subtitle2" color="text.secondary" sx={{ px: 2, py: 1 }}>
            {title}
          </Typography>
          <List dense disablePadding>
            {items.map((item) => {
              const primaryText = getPrimaryText(item);
              return (
                <ListItem key={getKey(item)}>
                  <ListItemAvatar>
                    <Avatar>{getInitial(primaryText)}</Avatar>
                  </ListItemAvatar>
                  <ListItemText primary={primaryText} secondary={relationLabels[item.relation]} />
                </ListItem>
              );
            })}
          </List>
        </Box>
      );
    },
    [getInitial, relationLabels],
  );

  if (isLoading) {
    return (
      <Box display="flex" alignItems="center" justifyContent="center" py={4}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  if (isError) {
    return (
      <Typography variant="body2" color="error">
        {t("documentLibraryShareDialog.membersError", {
          defaultValue: "We could not load the current access list.",
        })}
      </Typography>
    );
  }

  if (!users.length && !groups.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.noMembers", {
          defaultValue: "No one has access to this folder yet.",
        })}
      </Typography>
    );
  }

  return (
    <Box display="flex" flexDirection="column" gap={3}>
      {renderMemberSection(
        t("documentLibraryShareDialog.usersSectionTitle", { defaultValue: "Users" }),
        users,
        (member) => member.user.id,
        (member) => getUserDisplayName(member.user),
      )}
      {renderMemberSection(
        t("documentLibraryShareDialog.groupsSectionTitle", { defaultValue: "Groups" }),
        groups,
        (member) => member.group.id,
        (member) => getGroupDisplayName(member.group),
      )}
    </Box>
  );
}
