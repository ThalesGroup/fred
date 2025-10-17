import { Avatar, Box, CircularProgress, List, ListItem, ListItemAvatar, ListItemText, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  TagMember,
  TagWithItemsId,
  UserTagRelation,
  useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface DocumentLibraryShareCurrentAccessTabProps {
  tag?: TagWithItemsId;
  open: boolean;
  refreshKey: number;
}

export function DocumentLibraryShareCurrentAccessTab({
  tag,
  open,
  refreshKey,
}: DocumentLibraryShareCurrentAccessTabProps) {
  const { t } = useTranslation();

  const tagId = tag?.id;
  const { data, isFetching, isError, refetch } = useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery(
    { tagId: tagId ?? "" },
    { skip: !open || !tagId },
  );

  React.useEffect(() => {
    if (!open || !tagId) return;
    void refetch();
  }, [open, tagId, refreshKey, refetch]);

  const relationLabels = React.useMemo<Record<UserTagRelation, string>>(
    () => ({
      owner: t("documentLibraryShareDialog.relation.owner", { defaultValue: "Owner" }),
      editor: t("documentLibraryShareDialog.relation.editor", { defaultValue: "Editor" }),
      viewer: t("documentLibraryShareDialog.relation.viewer", { defaultValue: "Viewer" }),
    }),
    [t],
  );

  const members = React.useMemo<TagMember[]>(() => {
    const relationPriority: Record<UserTagRelation, number> = {
      owner: 0,
      editor: 1,
      viewer: 2,
    };

    const list = data?.members ?? [];
    return [...list].sort((a, b) => {
      const relationDiff = relationPriority[a.relation] - relationPriority[b.relation];
      if (relationDiff !== 0) return relationDiff;
      return a.user_id.localeCompare(b.user_id);
    });
  }, [data?.members]);

  if (isFetching) {
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

  if (!members.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.noMembers", {
          defaultValue: "No one has access to this folder yet.",
        })}
      </Typography>
    );
  }

  return (
    <List dense disablePadding>
      {members.map((member) => (
        <ListItem key={member.user_id}>
          <ListItemAvatar>
            <Avatar>{member.user_id.charAt(0).toUpperCase()}</Avatar>
          </ListItemAvatar>
          <ListItemText primary={member.user_id} secondary={relationLabels[member.relation]} />
        </ListItem>
      ))}
    </List>
  );
}
