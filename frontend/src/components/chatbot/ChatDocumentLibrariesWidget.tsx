// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import {
  Badge,
  Box,
  Button,
  ClickAwayListener,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Paper,
  Popper,
  Stack,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { TagWithItemsId } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { ChatDocumentLibrariesSelectionCard } from "./ChatDocumentLibrariesSelectionCard.tsx";

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
  const isVisible = open;
  const selectedCount = selectedLibraryIds.length;

  useEffect(() => {
    if (!isVisible) setPickerAnchor(null);
  }, [isVisible]);

  const selectedLabels = useMemo(
    () =>
      selectedLibraryIds.map((id) => ({
        id,
        label: libraryById?.[id]?.name ?? nameById[id] ?? id,
      })),
    [libraryById, nameById, selectedLibraryIds],
  );

  const handleRemove = (id: string) => {
    onChangeSelectedLibraryIds(selectedLibraryIds.filter((entry) => entry !== id));
  };

  const previewLibrary = previewLibraryId ? libraryById?.[previewLibraryId] : undefined;
  const handleClosePreview = () => {
    ignoreClickAwayRef.current = true;
    setPreviewLibraryId(null);
    setTimeout(() => {
      ignoreClickAwayRef.current = false;
    }, 0);
  };

  const widgetBody = (
    <Paper
      elevation={2}
      sx={{
        width: "100%",
        minWidth: "100%",
        maxWidth: "100%",
        maxHeight: "70vh",
        borderRadius: 3,
        border: `1px solid ${theme.palette.divider}`,
        p: 1.5,
        bgcolor: theme.palette.background.paper,
      }}
    >
      <Stack spacing={1} sx={{ pb: 0.5 }}>
        <Box display="flex" alignItems="center" gap={1} sx={{ width: "100%" }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Button
              variant="outlined"
              size="small"
              onClick={(event) => setPickerAnchor(event.currentTarget)}
              disabled={disabled}
              sx={{
                borderRadius: "8px",
                textTransform: "none",
                minHeight: 28,
                px: 1.5,
                justifyContent: "flex-start",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {t("chatbot.addLibraries", "Add libraries")}
            </Button>
          </Box>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box>
          {selectedCount > 0 ? (
            <List
              dense
              disablePadding
              sx={{
                maxHeight: "40vh",
                overflowY: "auto",
                "&::-webkit-scrollbar": { width: 6 },
                "&::-webkit-scrollbar-thumb": {
                  backgroundColor: theme.palette.divider,
                  borderRadius: 4,
                },
              }}
            >
              {selectedLabels.map((entry) => (
                <ListItem
                  key={entry.id}
                  disableGutters
                  secondaryAction={
                    <Stack direction="row" spacing={0.5}>
                      <IconButton size="small" disabled={disabled} onClick={() => setPreviewLibraryId(entry.id)}>
                        <VisibilityOutlinedIcon fontSize="small" />
                      </IconButton>
                      <IconButton size="small" disabled={disabled} onClick={() => handleRemove(entry.id)}>
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Stack>
                  }
                  sx={{ pr: 4 }}
                >
                  <ListItemText primary={entry.label} primaryTypographyProps={{ variant: "body2", noWrap: true }} />
                </ListItem>
              ))}
            </List>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ pb: 0.5 }}>
              {t("chatbot.libraries.empty", "No libraries selected")}
            </Typography>
          )}
        </Box>
      </Stack>
    </Paper>
  );

  return (
    <Box sx={{ position: "relative", width: isVisible ? "100%" : "auto" }}>
      {!isVisible && (
        <Tooltip title={t("chatbot.libraries.open", "Open libraries")}>
          <IconButton
            size="small"
            onClick={onOpen}
            aria-label={t("chatbot.libraries", "Libraries")}
            disabled={disabled}
            sx={{ color: disabled ? "text.disabled" : "inherit" }}
          >
            <Badge
              color={disabled ? "default" : "primary"}
              badgeContent={selectedCount > 0 ? selectedCount : undefined}
              overlap="circular"
              anchorOrigin={{ vertical: "top", horizontal: "right" }}
              sx={{ "& .MuiBadge-badge": { opacity: disabled ? 0.5 : 1 } }}
            >
              <MenuBookOutlinedIcon fontSize="small" />
            </Badge>
          </IconButton>
        </Tooltip>
      )}

      {isVisible && closeOnClickAway && (
        <ClickAwayListener
          onClickAway={() => {
            if (ignoreClickAwayRef.current) return;
            if (previewLibraryId) return;
            if (!isPickerOpen) onClose();
          }}
        >
          <Box sx={{ width: "100%" }}>{widgetBody}</Box>
        </ClickAwayListener>
      )}
      {isVisible && !closeOnClickAway && <Box sx={{ width: "100%" }}>{widgetBody}</Box>}

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

      <Dialog
        open={Boolean(previewLibraryId)}
        onClose={handleClosePreview}
        maxWidth="sm"
        fullWidth
      >
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
