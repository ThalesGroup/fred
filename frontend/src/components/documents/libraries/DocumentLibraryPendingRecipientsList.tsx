import RemoveCircleOutlineOutlinedIcon from "@mui/icons-material/RemoveCircleOutlineOutlined";
import {
  Avatar,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import { UserTagRelation } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryPendingRecipient } from "./DocumentLibraryShareTypes";

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
          defaultValue: "Add people or groups to start building the invite list.",
        })}
      </Typography>
    );
  }

  return (
    <List dense disablePadding>
      {items.map((recipient) => (
        <ListItem
          key={recipient.target_id}
          secondaryAction={
            <IconButton edge="end" onClick={() => onRemove(recipient.target_id)} disabled={disabled}>
              <RemoveCircleOutlineOutlinedIcon fontSize="small" />
            </IconButton>
          }
        >
          <ListItemAvatar>
            <Avatar sx={{ bgcolor: "primary.light", color: "primary.contrastText" }}>
              {recipient.displayName.charAt(0).toUpperCase()}
            </Avatar>
          </ListItemAvatar>
          <ListItemText
            primary={recipient.displayName}
            secondary={
              recipient.target_type === "user"
                ? t("documentLibraryShareDialog.type.user", { defaultValue: "User" })
                : t("documentLibraryShareDialog.type.group", { defaultValue: "Group" })
            }
          />
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
        </ListItem>
      ))}
    </List>
  );
}
