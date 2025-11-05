// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { Box, IconButton, List, ListItem, ListItemButton, Theme, Tooltip, Typography, useTheme } from "@mui/material";
// Import BoxProps and SxProps from MUI for proper typing
import { BoxProps } from "@mui/material";
import Popover from "@mui/material/Popover";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { ChatResourcesSelectionCard } from "../ChatResourcesSelectionCard";

// Extend with the standard MUI prop types for styling.
// We extend Pick<BoxProps, 'sx'> to inherit the definition of the 'sx' prop.
export type ChatContextPickerPanelProps = {
  selectedChatContextIds: string[];
  onChangeSelectedChatContextIds: (ids: string[]) => void;
} & Pick<BoxProps, "sx">;

export function ChatContextPickerPanel({
  selectedChatContextIds,
  onChangeSelectedChatContextIds,
  sx,
}: ChatContextPickerPanelProps) {
  const theme = useTheme<Theme>();
  const { t } = useTranslation();

  const [chatContextPickerAnchor, setChatContextPickerAnchor] = useState<HTMLElement | null>(null);
  const selectedChatContextId = selectedChatContextIds[0] ?? null;

  const { data: selectedChatContextResource } = useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery(
    { resourceId: selectedChatContextId as string },
    { skip: !selectedChatContextId },
  );

  const hasSelectedChatContext = !!selectedChatContextId;

  const chatContextBodyPreview = useMemo(() => {
    const c = selectedChatContextResource?.content ?? "";
    const sep = "\n---\n";
    const i = c.indexOf(sep);
    const body = (i !== -1 ? c.slice(i + sep.length) : c).replace(/\r\n/g, "\n").trim();
    if (!body) return null;
    const oneline = body.split("\n").filter(Boolean).slice(0, 2).join(" ");
    return oneline.length > 180 ? oneline.slice(0, 180) + "…" : oneline;
  }, [selectedChatContextResource]);

  const applyChatContextSelection = (ids: string[]) => {
    // mono-sélection (dernier choisi gagne)
    const next = ids.length > 0 ? [ids[ids.length - 1]] : [];
    onChangeSelectedChatContextIds(next);
    setChatContextPickerAnchor(null);
  };

  return (
    <Box
      // <-- MODIFIED: Apply the passed-in 'sx' prop to the root Box
      sx={[
        {
          px: 1,
          py: 1,
          borderBottom: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.sidebar.background,
        },
        // Spread the passed-in sx prop (supports object or array form)
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {/* Titre + action à droite */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="subtitle1" sx={{ pl: 1 }}>
          {t("settings.chatContext")}
        </Typography>

        {!hasSelectedChatContext && (
          <Tooltip title={t("settings.selectChatContext", "Select a chat context")}>
            <IconButton
              size="small"
              onClick={(e) => setChatContextPickerAnchor(e.currentTarget)}
              sx={{ borderRadius: 1.5 }}
            >
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Popover de sélection/modification */}
      <Popover
        open={Boolean(chatContextPickerAnchor)}
        anchorEl={chatContextPickerAnchor}
        onClose={() => setChatContextPickerAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        PaperProps={{ sx: { p: 1 } }}
      >
        <ChatResourcesSelectionCard
          libraryType={"chat-context"}
          selectedResourceIds={selectedChatContextIds}
          setSelectedResourceIds={applyChatContextSelection}
        />
      </Popover>

      {/* Carte compacte quand un profil est sélectionné */}
      {hasSelectedChatContext && (
        <List dense disablePadding sx={{ mt: 1 }}>
          <ListItem disableGutters sx={{ mb: 0 }}>
            <ListItemButton
              dense
              selected
              onClick={(e) => setChatContextPickerAnchor(e.currentTarget)}
              sx={{
                borderRadius: 1,
                px: 1,
                py: 0.75,
                border: `1px solid ${theme.palette.primary.main}`,
                backgroundColor: theme.palette.mode === "dark" ? "rgba(25,118,210,0.06)" : "rgba(25,118,210,0.04)",
                "&:hover": {
                  backgroundColor: theme.palette.mode === "dark" ? "rgba(25,118,210,0.1)" : "rgba(25,118,210,0.08)",
                },
                display: "flex",
                gap: 1,
                alignItems: "center",
              }}
            >
              <Box sx={{ width: "100%", minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                  {selectedChatContextResource?.name}
                </Typography>

                {Array.isArray(selectedChatContextResource?.labels) &&
                  selectedChatContextResource!.labels.length > 0 && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block" }} noWrap>
                      {selectedChatContextResource!.labels.join(" · ")}
                    </Typography>
                  )}

                {chatContextBodyPreview && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={
                      {
                        mt: 0.5,
                        display: "-webkit-box",
                        WebkitLineClamp: "2",
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "normal",
                      } as any
                    }
                  >
                    {chatContextBodyPreview}
                  </Typography>
                )}
              </Box>

              <Tooltip title={t("common.remove")}>
                <IconButton
                  size="small"
                  onClick={(event) => {
                    event.stopPropagation();
                    applyChatContextSelection([]);
                  }}
                  sx={{ flexShrink: 0, opacity: 0.7 }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </ListItemButton>
          </ListItem>
        </List>
      )}
    </Box>
  );
}
