import CreateIcon from "@mui/icons-material/Create";
import StarIcon from "@mui/icons-material/Star";
import VisibilityIcon from "@mui/icons-material/Visibility";
import { Box, CircularProgress, List, Stack, Typography } from "@mui/material";
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
import { GroupListItem } from "./GroupListItem";
import { UserListItem } from "./UserListItem";

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
      <Box component="section">
        <Typography variant="subtitle2" color="text.secondary" sx={{ px: 2, py: 1 }}>
          {t("documentLibraryShareDialog.usersSectionTitle", { defaultValue: "Users" })}
        </Typography>
        <List dense disablePadding>
          {users.map((userMember) => (
            <UserListItem
              user={userMember.user}
              secondaryAction={
                <Stack alignItems="center" direction="row" gap={1}>
                  <RelationIcon relation={userMember.relation} />
                  {relationLabels[userMember.relation]}
                </Stack>
              }
            />
          ))}
        </List>
      </Box>

      <Box component="section">
        <Typography variant="subtitle2" color="text.secondary" sx={{ px: 2, py: 1 }}>
          {t("documentLibraryShareDialog.groupsSectionTitle", { defaultValue: "Groups" })}
        </Typography>
        <List dense disablePadding>
          {groups.map((groupMember) => (
            <GroupListItem
              group={groupMember.group}
              secondaryAction={
                <Stack alignItems="center" direction="row" gap={1}>
                  <RelationIcon relation={groupMember.relation} />
                  {relationLabels[groupMember.relation]}
                </Stack>
              }
            />
          ))}
        </List>
      </Box>
    </Box>
  );
}

function RelationIcon({ relation }: { relation: UserTagRelation }) {
  if (relation === "owner") {
    return <StarIcon />;
  }

  if (relation === "editor") {
    return <CreateIcon />;
  }

  if (relation === "viewer") {
    return <VisibilityIcon />;
  }

  return null;
}
