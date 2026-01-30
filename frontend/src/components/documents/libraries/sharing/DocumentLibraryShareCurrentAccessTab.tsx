import CreateIcon from "@mui/icons-material/Create";
import StarIcon from "@mui/icons-material/Star";
import VisibilityIcon from "@mui/icons-material/Visibility";
import { Box, CircularProgress, List, Stack, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  TagMemberUser,
  TagWithItemsId,
  UserSummary,
  UserTagRelation,
  useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
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
      owner: t("documentLibraryShareDialog.relation.owner"),
      editor: t("documentLibraryShareDialog.relation.editor"),
      viewer: t("documentLibraryShareDialog.relation.viewer"),
    }),
    [t],
  );

  const users = React.useMemo<TagMemberUser[]>(() => {
    return sortMembers(members?.users ?? [], (member) => getUserDisplayName(member.user));
  }, [members?.users]);

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
        {t("documentLibraryShareDialog.membersError")}
      </Typography>
    );
  }

  if (!users.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.noMembers")}
      </Typography>
    );
  }

  return (
    <Box display="flex" flexDirection="column" gap={3} sx={{ flex: 1, minHeight: 0, overflow: "auto", pb: 1 }}>
      <Box component="section">
        <Typography variant="subtitle2" color="text.secondary" sx={{ px: 2, py: 1 }}>
          {t("documentLibraryShareDialog.usersSectionTitle")}
        </Typography>
        <List dense disablePadding>
          {users.map((userMember) => (
            <UserListItem
              key={userMember.user.id}
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
