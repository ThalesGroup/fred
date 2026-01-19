// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import {
  Box,
  Button,
  ClickAwayListener,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Popper,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { TagWithItemsId } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { buildTree } from "../../../shared/utils/tagTree";
import { TagTreeList } from "../../../shared/ui/tree/TagTreeList";
import { DeleteIconButton } from "../../../shared/ui/buttons/DeleteIconButton";
import { ViewIconButton } from "../../../shared/ui/buttons/ViewIconButton";
import { ChatDocumentLibrariesSelectionCard } from "./ChatDocumentLibrariesSelectionCard.tsx";
import ChatWidgetList from "../../../components/chatbot/ChatWidgetList.tsx";
import ChatWidgetShell from "../../../components/chatbot/ChatWidgetShell.tsx";

export type ChatDocumentLibrariesWidgetProps = {
  selectedLibraryIds: string[];
  onChangeSelectedLibraryIds: (ids: string[]) => void;
  nameById: Record<string, string>;
  libraryById?: Record<string, TagWithItemsId | undefined>;
  open: boolean;
  closeOnClickAway?: boolean;
  disabled?: boolean;
  onOpen: () => void;
  onClose: () => void;
};

const ChatDocumentLibrariesWidget = ({
  selectedLibraryIds,
  onChangeSelectedLibraryIds,
  nameById,
  libraryById,
  open,
  closeOnClickAway = true,
  disabled = false,
  onOpen,
  onClose,
}: ChatDocumentLibrariesWidgetProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const [pickerAnchor, setPickerAnchor] = useState<HTMLElement | null>(null);
  const [previewLibraryId, setPreviewLibraryId] = useState<string | null>(null);
  const ignoreClickAwayRef = useRef(false);

  const isPickerOpen = Boolean(pickerAnchor);
  const selectedCount = selectedLibraryIds.length;

  useEffect(() => {
    if (!open) setPickerAnchor(null);
  }, [open]);

  const selectedLibraries = useMemo(() => {
    if (!libraryById) return [];
    return selectedLibraryIds
      .map((id) => libraryById[id])
      .filter((entry): entry is TagWithItemsId => Boolean(entry));
  }, [libraryById, selectedLibraryIds]);

  const hasFullLibraryData =
    Boolean(libraryById) && selectedLibraries.length === selectedLibraryIds.length;

  const selectedTree = useMemo(() => {
    if (!hasFullLibraryData || selectedLibraries.length === 0) return null;
    return buildTree(selectedLibraries);
  }, [hasFullLibraryData, selectedLibraries]);

  const handleRemove = useCallback(
    (id: string) => {
      onChangeSelectedLibraryIds(selectedLibraryIds.filter((entry) => entry !== id));
    },
    [onChangeSelectedLibraryIds, selectedLibraryIds],
  );

  const previewLibrary = previewLibraryId ? libraryById?.[previewLibraryId] : undefined;
  const handleClosePreview = () => {
    ignoreClickAwayRef.current = true;
    setPreviewLibraryId(null);
    setTimeout(() => {
      ignoreClickAwayRef.current = false;
    }, 0);
  };

  const buildActions = useCallback(
    (id: string) => (
      <Stack direction="row" spacing={0.5}>
        <ViewIconButton
          size="small"
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            setPreviewLibraryId(id);
          }}
        />
        <DeleteIconButton
          size="small"
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            handleRemove(id);
          }}
        />
      </Stack>
    ),
    [disabled, handleRemove],
  );

  const fallbackItems = useMemo(
    () =>
      selectedLibraryIds.map((id) => ({
        id,
        label: nameById[id] ?? id,
        secondaryAction: buildActions(id),
      })),
    [buildActions, nameById, selectedLibraryIds],
  );

  const handleClickAway = () => {
    if (ignoreClickAwayRef.current) return;
    if (previewLibraryId) return;
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
        icon={<MenuBookOutlinedIcon fontSize="small" />}
        ariaLabel={t("knowledge.viewSelector.libraries", "Libraries")}
        tooltipLabel={t("knowledge.viewSelector.libraries", "Libraries")}
        tooltipDescription={t(
          "knowledge.viewSelector.librariesTooltip",
          "Scope document retrieval to only the selected document libraries.",
        )}
        tooltipDisabledReason={
          disabled
            ? t("knowledge.viewSelector.librariesUnsupported", "This agent does not support library scoping.")
            : undefined
        }
        actionLabel={t("chatbot.addLibraries", "Add libraries")}
        onAction={(event) => setPickerAnchor(event.currentTarget)}
      >
        {hasFullLibraryData ? (
          <Box
            sx={{
              maxHeight: "40vh",
              overflowY: "auto",
              "&::-webkit-scrollbar": { width: 6 },
              "&::-webkit-scrollbar-thumb": {
                backgroundColor: (theme) => theme.palette.divider,
                borderRadius: 4,
              },
            }}
          >
            <TagTreeList
              tree={selectedTree}
              emptyText={t("chatbot.libraries.empty", "No libraries selected")}
              renderActions={(tag) => buildActions(tag.id)}
            />
          </Box>
        ) : (
          <ChatWidgetList
            items={fallbackItems}
            emptyText={t("chatbot.libraries.empty", "No libraries selected")}
          />
        )}
      </ChatWidgetShell>
      <Popper
        open={isPickerOpen}
        anchorEl={pickerAnchor}
        placement="bottom-end"
        modifiers={[{ name: "offset", options: { offset: [0, 8] } }]}
        sx={{ zIndex: theme.zIndex.modal + 1 }}
      >
        <ClickAwayListener onClickAway={() => setPickerAnchor(null)}>
          <Paper elevation={6} sx={{ p: 1 }}>
            <ChatDocumentLibrariesSelectionCard
              libraryType={"document"}
              selectedLibrariesIds={selectedLibraryIds}
              setSelectedLibrariesIds={onChangeSelectedLibraryIds}
            />
          </Paper>
        </ClickAwayListener>
      </Popper>

      <Dialog open={Boolean(previewLibraryId)} onClose={handleClosePreview} maxWidth="sm" fullWidth>
        <DialogTitle>{previewLibrary?.name ?? t("chatbot.libraries.previewTitle", "Library")}</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary">
            {previewLibrary?.description || t("chatbot.libraries.noDescription", "No description available.")}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClosePreview}>{t("common.close", "Close")}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ChatDocumentLibrariesWidget;
