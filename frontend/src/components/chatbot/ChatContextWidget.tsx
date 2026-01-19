// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import { Box, ClickAwayListener, Paper, Popper, Stack, useTheme } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Resource } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";
import { ViewIconButton } from "../../shared/ui/buttons/ViewIconButton";
import { ChatContextEditorModal } from "../resources/ChatContextEditorModal.tsx";
import { ChatResourcesSelectionCard } from "./ChatResourcesSelectionCard.tsx";
import ChatWidgetList from "./ChatWidgetList.tsx";
import ChatWidgetShell from "./ChatWidgetShell.tsx";

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
  const selectedCount = selectedChatContextIds.length;

  useEffect(() => {
    if (!open) setPickerAnchor(null);
  }, [open]);

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

  const items = selectedLabels.map((entry) => ({
    id: entry.id,
    label: entry.label,
    secondaryAction: (
      <Stack direction="row" spacing={0.5}>
        <ViewIconButton size="small" onClick={() => setPreviewContextId(entry.id)} />
        <DeleteIconButton size="small" onClick={() => handleRemove(entry.id)} />
      </Stack>
    ),
  }));

  const handleClickAway = () => {
    if (ignoreClickAwayRef.current) return;
    if (previewContextId) return;
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
        badgeCount={selectedCount}
        icon={<ForumOutlinedIcon fontSize="small" />}
        ariaLabel={t("settings.chatContext", "Chat context")}
        tooltipLabel={t("settings.chatContext", "Chat context")}
        tooltipDescription={t(
          "settings.chatContextTooltip.description",
          "Select reusable context snippets included with every message in this conversation.",
        )}
        actionLabel={t("conversationChatContext.add", "Add chat context")}
        onAction={(event) => setPickerAnchor(event.currentTarget)}
      >
        <ChatWidgetList items={items} emptyText={t("conversationChatContext.empty", "No chat contexts selected")} />
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
