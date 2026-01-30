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
  Typography,
} from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import {
  TagWithItemsId,
  UserTagRelation,
  useShareTagKnowledgeFlowV1TagsTagIdSharePostMutation,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryPendingRecipientsList } from "../DocumentLibraryPendingRecipientsList";
import { DocumentLibraryPendingRecipient } from "./DocumentLibraryShareTypes";
import { DocumentLibraryShareUsersList } from "./DocumentLibraryShareUsersList";

interface DocumentLibraryShareAddTabProps {
  tag: TagWithItemsId;
  onShared?: () => void;
}

export function DocumentLibraryShareAddTab({ tag, onShared }: DocumentLibraryShareAddTabProps) {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = React.useState("");
  const [pendingRecipients, setPendingRecipients] = React.useState<DocumentLibraryPendingRecipient[]>([]);
  const [isSharing, setIsSharing] = React.useState(false);
  const [shareError, setShareError] = React.useState<string | null>(null);
  const [shareTag] = useShareTagKnowledgeFlowV1TagsTagIdSharePostMutation();

  const selectedIds = React.useMemo(
    () => new Set(pendingRecipients.map((item) => item.target_id)),
    [pendingRecipients],
  );

  const handleAddRecipient = React.useCallback((newRecipient: DocumentLibraryPendingRecipient) => {
    setPendingRecipients((prev) => {
      if (prev.some((item) => item.target_id === newRecipient.target_id)) return prev;
      return [...prev, newRecipient];
    });
  }, []);

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
      onShared?.();
    } catch (error) {
      const status = (error as any)?.status ?? (error as any)?.originalStatus ?? (error as any)?.data?.status;
      const isForbidden = status === 403;

      let message =
        (isForbidden && t("documentLibraryShareDialog.shareForbidden", { name: tag.name })) ||
        t("documentLibraryShareDialog.shareError");

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
    <Box display="flex" flexDirection="column" gap={2} sx={{ flex: 1, minHeight: "500px" }}>
      {shareError ? (
        <Alert severity="error" onClose={() => setShareError(null)}>
          {shareError}
        </Alert>
      ) : null}

      <TextField
        fullWidth
        variant="outlined"
        placeholder={t("documentLibraryShareDialog.searchPlaceholder")}
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

      <Box
        sx={{
          display: "grid",
          gridTemplateRows: "1fr auto auto 1fr",
          gap: 2,
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            overflowY: "auto",
          }}
        >
          <DocumentLibraryShareUsersList
            searchQuery={searchQuery}
            selectedIds={selectedIds}
            disabled={isSharing}
            onAdd={handleAddRecipient}
            tagId={tag.id}
          />
        </Box>

        <Divider />

        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="subtitle2">{t("documentLibraryShareDialog.pendingTitle")}</Typography>
          {pendingRecipients.length > 0 && (
            <Chip
              color="default"
              variant="outlined"
              label={t("documentLibraryShareDialog.pendingCount", {
                count: pendingRecipients.length,
              })}
            />
          )}
        </Stack>

        <Box
          sx={{
            overflowY: "auto",
          }}
        >
          <DocumentLibraryPendingRecipientsList
            items={pendingRecipients}
            disabled={isSharing}
            onChangeRelation={handleRelationChange}
            onRemove={handleRemoveRecipient}
          />
        </Box>
      </Box>

      <Box display="flex" justifyContent="flex-end">
        <Button
          variant="contained"
          onClick={() => void handleShare()}
          disabled={pendingRecipients.length === 0 || isSharing}
        >
          {t("documentLibraryShareDialog.shareButton")}
        </Button>
      </Box>
    </Box>
  );
}
