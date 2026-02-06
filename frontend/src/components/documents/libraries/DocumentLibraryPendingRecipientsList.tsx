import RemoveCircleOutlineOutlinedIcon from "@mui/icons-material/RemoveCircleOutlineOutlined";
import { IconButton, List, Stack, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";

import { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { UserTagRelation } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryPendingRecipient } from "./sharing/DocumentLibraryShareTypes";
import { UserListItem } from "./sharing/UserListItem";

interface DocumentLibraryPendingRecipientsListProps {
  items: DocumentLibraryPendingRecipient[];
  disabled?: boolean;
  onChangeRelation: (id: string, relation: UserTagRelation) => void;
  onRemove: (id: string) => void;
}

export function DocumentLibraryPendingRecipientsList({
  items,
  disabled = false,
  onChangeRelation,
  onRemove,
}: DocumentLibraryPendingRecipientsListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("documentLibraryShareDialog.emptySelection", {
          defaultValue: "Add people to start building the invite list.",
        })}
      </Typography>
    );
  }

  return (
    <List dense disablePadding>
      {items.map((recipient) => {
        const secondaryAction: ReactNode = (
          <Stack direction="row" spacing={1} alignItems="center">
            <ToggleButtonGroup
              size="small"
              value={recipient.relation}
              exclusive
              onChange={(_, value) => value && onChangeRelation(recipient.target_id, value as UserTagRelation)}
              sx={{
                "& .MuiToggleButton-root": {
                  textTransform: "none",
                  px: 1.5,
                },
              }}
              disabled={disabled}
            >
              <ToggleButton value="viewer">
                {t("documentLibraryShareDialog.relation.viewer", { defaultValue: "Viewer" })}
              </ToggleButton>
              <ToggleButton value="editor">
                {t("documentLibraryShareDialog.relation.editor", { defaultValue: "Editor" })}
              </ToggleButton>
              <ToggleButton value="owner">
                {t("documentLibraryShareDialog.relation.owner", { defaultValue: "Owner" })}
              </ToggleButton>
            </ToggleButtonGroup>
            <IconButton edge="end" onClick={() => onRemove(recipient.target_id)} disabled={disabled}>
              <RemoveCircleOutlineOutlinedIcon fontSize="small" />
            </IconButton>
          </Stack>
        );

        return <UserListItem key={recipient.target_id} user={recipient.data} secondaryAction={secondaryAction} />;
      })}
    </List>
  );
}
