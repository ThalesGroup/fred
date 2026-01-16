// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import {
  Badge,
  Box,
  Button,
  ClickAwayListener,
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
import type { Resource } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { ChatContextEditorModal } from "../resources/ChatContextEditorModal.tsx";
import { ChatResourcesSelectionCard } from "./ChatResourcesSelectionCard.tsx";

export type ChatContextWidgetProps = {
  selectedChatContextIds: string[];
  onChangeSelectedChatContextIds: (ids: string[]) => void;
  nameById: Record<string, string>;
  resourceById?: Record<string, Resource | undefined>;
  open: boolean;
  closeOnClickAway?: boolean;
  onOpen: () => void;
  onClose: () => void;
};

const ChatContextWidget = ({
  selectedChatContextIds,
  onChangeSelectedChatContextIds,
  nameById,
  resourceById,
  open,
  closeOnClickAway = true,
  onOpen,
  onClose,
}: ChatContextWidgetProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const [pickerAnchor, setPickerAnchor] = useState<HTMLElement | null>(null);
  const [previewContextId, setPreviewContextId] = useState<string | null>(null);
  const ignoreClickAwayRef = useRef(false);

  const isPickerOpen = Boolean(pickerAnchor);
  const isVisible = open;
  const selectedCount = selectedChatContextIds.length;

  useEffect(() => {
    if (!isVisible) setPickerAnchor(null);
  }, [isVisible]);

  const selectedLabels = useMemo(
    () =>
      selectedChatContextIds.map((id) => ({
        id,
        label: resourceById?.[id]?.name ?? nameById[id] ?? id,
      })),
    [nameById, resourceById, selectedChatContextIds],
  );

  const handleRemove = (id: string) => {
    onChangeSelectedChatContextIds(selectedChatContextIds.filter((entry) => entry !== id));
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
              {t("conversationChatContext.add", "Add chat context")}
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
                      <IconButton size="small" onClick={() => setPreviewContextId(entry.id)}>
                        <VisibilityOutlinedIcon fontSize="small" />
                      </IconButton>
                      <IconButton size="small" onClick={() => handleRemove(entry.id)}>
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
              {t("conversationChatContext.empty", "No chat contexts selected")}
            </Typography>
          )}
        </Box>
      </Stack>
    </Paper>
  );

  return (
    <Box sx={{ position: "relative", width: isVisible ? "100%" : "auto" }}>
      {!isVisible && (
        <Tooltip title={t("conversationChatContext.open", "Open chat context")}>
          <IconButton size="small" onClick={onOpen} aria-label={t("settings.chatContext", "Chat context")}>
            <Badge
              color="primary"
              badgeContent={selectedCount > 0 ? selectedCount : undefined}
              overlap="circular"
              anchorOrigin={{ vertical: "top", horizontal: "right" }}
            >
              <ForumOutlinedIcon fontSize="small" />
            </Badge>
          </IconButton>
        </Tooltip>
      )}

      {isVisible && closeOnClickAway && (
        <ClickAwayListener
          onClickAway={() => {
            if (ignoreClickAwayRef.current) return;
            if (previewContextId) return;
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
            <ChatResourcesSelectionCard
              libraryType={"chat-context"}
              selectedResourceIds={selectedChatContextIds}
              setSelectedResourceIds={onChangeSelectedChatContextIds}
              selectionMode="multiple"
            />
          </Paper>
        </ClickAwayListener>
      </Popper>

      {previewContextId && (
        <ChatContextEditorModal
          isOpen
          onClose={() => {
            ignoreClickAwayRef.current = true;
            setPreviewContextId(null);
            setTimeout(() => {
              ignoreClickAwayRef.current = false;
            }, 0);
          }}
          onSave={() => undefined}
          initial={{
            name: resourceById?.[previewContextId]?.name ?? nameById[previewContextId] ?? "",
            description: resourceById?.[previewContextId]?.description,
            labels: resourceById?.[previewContextId]?.labels,
            yaml: resourceById?.[previewContextId]?.content ?? "",
          }}
          previewOnly
        />
      )}
    </Box>
  );
};

export default ChatContextWidget;
