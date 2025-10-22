import SearchIcon from "@mui/icons-material/Search";
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  InputAdornment,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  ShareTargetResource,
  TagWithItemsId,
  UserTagRelation,
  useShareTagKnowledgeFlowV1TagsTagIdSharePostMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryPendingRecipientsList } from "./DocumentLibraryPendingRecipientsList";
import { DocumentLibraryShareGroupTree } from "./DocumentLibraryShareGroupTree";
import { DocumentLibraryPendingRecipient } from "./DocumentLibraryShareTypes";
import { DocumentLibraryShareUsersList } from "./DocumentLibraryShareUsersList";

interface DocumentLibraryShareAddTabProps {
  tag: TagWithItemsId;
  onShared?: () => void;
}

export function DocumentLibraryShareAddTab({ tag, onShared }: DocumentLibraryShareAddTabProps) {
  const { t } = useTranslation();
  const [audience, setAudience] = React.useState<ShareTargetResource>("user");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [pendingRecipients, setPendingRecipients] = React.useState<DocumentLibraryPendingRecipient[]>([]);
  const [isSharing, setIsSharing] = React.useState(false);
  const [shareError, setShareError] = React.useState<string | null>(null);
  const [shareTag] = useShareTagKnowledgeFlowV1TagsTagIdSharePostMutation();

  const selectedIds = React.useMemo(
    () => new Set(pendingRecipients.map((item) => item.target_id)),
    [pendingRecipients],
  );

  const handleAddRecipient = React.useCallback(
    (target_id: string, target_type: ShareTargetResource, displayName: string) => {
      setPendingRecipients((prev) => {
        if (prev.some((item) => item.target_id === target_id)) return prev;
        return [...prev, { target_id, target_type, displayName, relation: "viewer" }];
      });
    },
    [],
  );

  const handleRelationChange = (id: string, relation: UserTagRelation) => {
    setPendingRecipients((prev) => prev.map((item) => (item.target_id === id ? { ...item, relation } : item)));
  };

  const handleRemoveRecipient = (id: string) => {
    setPendingRecipients((prev) => prev.filter((item) => item.target_id !== id));
  };

  const handleShare = async () => {
    if (!pendingRecipients.length) return;

    setIsSharing(true);
    setShareError(null);

    try {
      for (const recipient of pendingRecipients) {
        await shareTag({
          tagId: tag.id,
          tagShareRequest: recipient,
        }).unwrap();
      }

      setPendingRecipients([]);
      setSearchQuery("");
      setAudience("user");
      onShared?.();
    } catch (error) {
      let message = t("documentLibraryShareDialog.shareError", {
        defaultValue: "We couldn't apply sharing settings. Please try again.",
      });
      if (error && typeof error === "object" && "data" in error) {
        const data = (error as { data?: unknown }).data;
        if (data && typeof data === "object" && "detail" in data) {
          const detail = (data as { detail?: unknown }).detail;
          if (typeof detail === "string") message = detail;
        }
      }
      setShareError(message);
    } finally {
      setIsSharing(false);
    }
  };

  return (
    <Box display="flex" flexDirection="column" gap={2}>
      {shareError ? (
        <Alert severity="error" onClose={() => setShareError(null)}>
          {shareError}
        </Alert>
      ) : null}

      <TextField
        fullWidth
        variant="outlined"
        placeholder={t("documentLibraryShareDialog.searchPlaceholder", {
          defaultValue: "Search users or groups…",
        })}
        value={searchQuery}
        onChange={(event) => setSearchQuery(event.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
        disabled={isSharing}
      />

      <ToggleButtonGroup
        value={audience}
        exclusive
        onChange={(_, value) => value && setAudience(value)}
        color="primary"
        sx={{
          alignSelf: "flex-start",
          "& .MuiToggleButton-root": {
            borderRadius: 999,
            textTransform: "none",
            px: 2.5,
          },
        }}
        disabled={isSharing}
      >
        <ToggleButton value="user">
          {t("documentLibraryShareDialog.usersToggle", { defaultValue: "Users" })}
        </ToggleButton>
        <ToggleButton value="group">
          {t("documentLibraryShareDialog.groupsToggle", { defaultValue: "Groups" })}
        </ToggleButton>
      </ToggleButtonGroup>

      {audience === "user" ? (
        <DocumentLibraryShareUsersList
          searchQuery={searchQuery}
          selectedIds={selectedIds}
          disabled={isSharing}
          onAdd={handleAddRecipient}
          tagId={tag.id}
        />
      ) : (
        <DocumentLibraryShareGroupTree
          searchQuery={searchQuery}
          selectedIds={selectedIds}
          disabled={isSharing}
          onAdd={handleAddRecipient}
        />
      )}

      <Divider />

      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="subtitle2">
          {t("documentLibraryShareDialog.pendingTitle", { defaultValue: "Pending access" })}
        </Typography>
        {pendingRecipients.length > 0 && (
          <Chip
            color="default"
            variant="outlined"
            label={t("documentLibraryShareDialog.pendingCount", {
              count: pendingRecipients.length,
              defaultValue: "{{count}} pending",
            })}
          />
        )}
      </Stack>

      <DocumentLibraryPendingRecipientsList
        items={pendingRecipients}
        disabled={isSharing}
        onChangeRelation={handleRelationChange}
        onRemove={handleRemoveRecipient}
      />

      <Box display="flex" justifyContent="flex-end">
        <Button
          variant="contained"
          onClick={() => void handleShare()}
          disabled={pendingRecipients.length === 0 || isSharing}
        >
          {t("documentLibraryShareDialog.shareButton", { defaultValue: "Share" })}
        </Button>
      </Box>
    </Box>
  );
}
