// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import CloseIcon from "@mui/icons-material/Close";
import ToggleOffOutlinedIcon from "@mui/icons-material/ToggleOffOutlined";
import ToggleOnOutlinedIcon from "@mui/icons-material/ToggleOnOutlined";
import {
  Box,
  Button,
  Checkbox,
  ClickAwayListener,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Popper,
  Stack,
  TextField,
  Typography,
  useTheme,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";
import { ToggleIconButton } from "../../shared/ui/buttons/ToggleIconButton";
import { FloatingPanel } from "../../shared/ui/surfaces/FloatingPanel";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
import { DocumentMetadata, useBrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostMutation } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { matchesDocByName } from "../documents/libraries/documentHelper";
import ChatWidgetList from "./ChatWidgetList";
import ChatWidgetShell from "./ChatWidgetShell";

export type ChatDocumentsWidgetProps = {
  selectedDocumentUids: string[];
  onChangeSelectedDocumentUids: (ids: string[]) => void;
  includeInSearch: boolean;
  onIncludeInSearchChange: (next: boolean) => void;
  includeInSearchDisabled?: boolean;
  open: boolean;
  closeOnClickAway?: boolean;
  disabled?: boolean;
  onOpen: () => void;
  onClose: () => void;
};

const PAGE_SIZE = 25;

const getDocLabel = (doc: DocumentMetadata) =>
  doc.identity.title?.trim() || doc.identity.document_name || doc.identity.document_uid;

const ChatDocumentsWidget = ({
  selectedDocumentUids,
  onChangeSelectedDocumentUids,
  includeInSearch,
  onIncludeInSearchChange,
  includeInSearchDisabled = false,
  open,
  closeOnClickAway = true,
  disabled = false,
  onOpen,
  onClose,
}: ChatDocumentsWidgetProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const [pickerAnchor, setPickerAnchor] = useState<HTMLElement | null>(null);
  const [query, setQuery] = useState("");
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [totalDocuments, setTotalDocuments] = useState<number | null>(null);
  const [nextOffset, setNextOffset] = useState(0);
  const [browseDocuments, { isLoading }] = useBrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostMutation();

  const isPickerOpen = Boolean(pickerAnchor);
  const selectedCount = selectedDocumentUids.length;
  const badgeColor = includeInSearch ? (disabled ? "default" : "primary") : "warning";

  useEffect(() => {
    if (!open) {
      setPickerAnchor(null);
      setQuery("");
    }
  }, [open]);

  const loadPage = useCallback(
    async (offset: number, append: boolean) => {
      const res = await browseDocuments({
        browseDocumentsRequest: {
          offset,
          limit: PAGE_SIZE,
          sort_by: [{ field: "document_name", direction: "asc" }],
        },
      }).unwrap();
      const docs = res.documents || [];
      setDocuments((prev) => (append ? [...prev, ...docs] : docs));
      setTotalDocuments(res.total ?? docs.length);
      setNextOffset(offset + docs.length);
    },
    [browseDocuments],
  );

  useEffect(() => {
    if (!isPickerOpen || documents.length) return;
    void loadPage(0, false);
  }, [isPickerOpen, documents.length, loadPage]);

  const handleLoadMore = useCallback(() => {
    if (isLoading) return;
    void loadPage(nextOffset, true);
  }, [isLoading, loadPage, nextOffset]);

  const docById = useMemo(() => {
    const map = new Map<string, DocumentMetadata>();
    documents.forEach((doc) => map.set(doc.identity.document_uid, doc));
    return map;
  }, [documents]);

  const selectedItems = useMemo(
    () =>
      selectedDocumentUids.map((uid) => {
        const doc = docById.get(uid);
        return { id: uid, label: doc ? getDocLabel(doc) : uid };
      }),
    [docById, selectedDocumentUids],
  );

  const toggleDocument = useCallback(
    (uid: string) => {
      const next = selectedDocumentUids.includes(uid)
        ? selectedDocumentUids.filter((id) => id !== uid)
        : [...selectedDocumentUids, uid];
      onChangeSelectedDocumentUids(next);
    },
    [onChangeSelectedDocumentUids, selectedDocumentUids],
  );

  const filteredDocs = useMemo(
    () => (query ? documents.filter((doc) => matchesDocByName(doc, query)) : documents),
    [documents, query],
  );

  const canLoadMore = totalDocuments !== null && documents.length < totalDocuments;

  const items = selectedItems.map((item) => ({
    id: item.id,
    label: item.label,
    secondaryAction: (
      <DeleteIconButton size="small" onClick={() => toggleDocument(item.id)} disabled={disabled} />
    ),
  }));

  const handleClickAway = () => {
    if (!isPickerOpen) onClose();
  };

  return (
    <Box sx={{ position: "relative", width: open ? "100%" : "auto" }}>
      <ChatWidgetShell
        open={open}
        onOpen={onOpen}
        onClose={onClose}
        closeOnClickAway={closeOnClickAway}
        onClickAway={handleClickAway}
        disabled={disabled}
        badgeCount={selectedCount}
        badgeColor={badgeColor}
        icon={<ArticleOutlinedIcon fontSize="small" />}
        ariaLabel={t("chatbot.documents.drawerTitle", "Documents")}
        tooltipLabel={t("chatbot.documents.drawerTitle", "Documents")}
        tooltipDescription={t(
          "chatbot.documents.tooltip.description",
          "Restrict retrieval to specific documents for this conversation.",
        )}
        tooltipDisabledReason={
          disabled ? t("chatbot.documents.tooltip.disabled", "This agent does not support document scoping.") : undefined
        }
        actionLabel={t("chatbot.addDocuments", "Add documents")}
        onAction={(event) => {
          if (isPickerOpen) {
            setPickerAnchor(null);
            return;
          }
          setPickerAnchor(event.currentTarget);
        }}
        headerActions={
          <SimpleTooltip
            title={
              includeInSearch
                ? t(
                    "chatbot.documents.includeTooltipOn",
                    "Document scoping is enabled for this conversation.",
                  )
                : t(
                    "chatbot.documents.includeTooltipOff",
                    "Document scoping is disabled for this conversation.",
                  )
            }
            placement="left"
          >
            <span>
              <ToggleIconButton
                size="small"
                onClick={() => onIncludeInSearchChange(!includeInSearch)}
                disabled={disabled || includeInSearchDisabled}
                aria-label={t("chatbot.documents.includeToggle", "Toggle document scoping")}
                icon={
                  includeInSearch ? (
                    <ToggleOnOutlinedIcon fontSize="small" />
                  ) : (
                    <ToggleOffOutlinedIcon fontSize="small" />
                  )
                }
                active={!includeInSearch}
                indicatorColor="warning"
                sx={{ color: includeInSearch ? "inherit" : "text.secondary" }}
              />
            </span>
          </SimpleTooltip>
        }
      >
        <ChatWidgetList items={items} emptyText={t("chatbot.documents.empty", "No documents selected.")} />
      </ChatWidgetShell>
      <Popper
        open={isPickerOpen}
        anchorEl={pickerAnchor}
        placement="bottom-end"
        modifiers={[{ name: "offset", options: { offset: [0, 8] } }]}
        sx={{ zIndex: theme.zIndex.modal + 1 }}
      >
        <ClickAwayListener onClickAway={() => setPickerAnchor(null)}>
          <FloatingPanel sx={{ p: 1, width: 420, maxWidth: "90vw" }}>
            <Stack spacing={1}>
              <Box display="flex" alignItems="center" gap={1}>
                <TextField
                  size="small"
                  placeholder={t("chatbot.searchDocuments", "Search documents...")}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  fullWidth
                />
                <IconButton size="small" onClick={() => setPickerAnchor(null)} aria-label={t("common.close", "Close")}>
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Box>
              <Box sx={{ maxHeight: "50vh", overflowY: "auto" }}>
                {filteredDocs.length === 0 && !isLoading ? (
                  <Typography variant="caption" color="text.secondary">
                    {t("documentLibrary.noDocument", "No document found")}
                  </Typography>
                ) : (
                  <List dense disablePadding>
                    {filteredDocs.map((doc) => {
                      const uid = doc.identity.document_uid;
                      const label = getDocLabel(doc);
                      const isSelected = selectedDocumentUids.includes(uid);
                      return (
                        <ListItemButton key={uid} onClick={() => toggleDocument(uid)}>
                          <Checkbox size="small" checked={isSelected} />
                          <ListItemText
                            primary={label}
                            secondary={doc.identity.document_uid}
                            primaryTypographyProps={{ noWrap: true }}
                            secondaryTypographyProps={{ noWrap: true }}
                          />
                        </ListItemButton>
                      );
                    })}
                  </List>
                )}
              </Box>
              {canLoadMore && (
                <Button size="small" onClick={handleLoadMore} disabled={isLoading}>
                  {t("common.loadMore", "Load more")}
                </Button>
              )}
            </Stack>
          </FloatingPanel>
        </ClickAwayListener>
      </Popper>
    </Box>
  );
};

export default ChatDocumentsWidget;
