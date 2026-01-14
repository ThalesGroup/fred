// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  Box,
  Button,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  Theme,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
// Import BoxProps and SxProps from MUI for proper typing
import { BoxProps } from "@mui/material";
import Popover from "@mui/material/Popover";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Resource,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
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

  const { data: chatContextResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery(
    { kind: "chat-context" },
    { refetchOnMountOrArgChange: true },
  );

  const selectedChatContextResources = useMemo<Resource[]>(() => {
    if (!selectedChatContextIds.length) return [];
    const byId = new Map(chatContextResources.map((r) => [r.id, r]));
    return selectedChatContextIds.map((id) => byId.get(id)).filter(Boolean) as Resource[];
  }, [chatContextResources, selectedChatContextIds]);

  const chatContextBodyPreviews = useMemo(() => {
    const makePreview = (content: string | undefined | null) => {
      if (!content) return null;
      const sep = "\n---\n";
      const i = content.indexOf(sep);
      const body = (i !== -1 ? content.slice(i + sep.length) : content).replace(/\r\n/g, "\n").trim();
      if (!body) return null;
      const oneline = body.split("\n").filter(Boolean).slice(0, 2).join(" ");
      return oneline.length > 180 ? oneline.slice(0, 180) + "…" : oneline;
    };

    return selectedChatContextResources.reduce<Record<string, string | null>>((acc, res) => {
      acc[res.id] = makePreview(res.content);
      return acc;
    }, {});
  }, [selectedChatContextResources]);

  const applyChatContextSelection = (ids: string[]) => {
    const uniqueIds = Array.from(new Set(ids));
    onChangeSelectedChatContextIds(uniqueIds);
    setChatContextPickerAnchor(null);
  };

  const hasSelectedChatContext = selectedChatContextIds.length > 0;

  return (
    <Box
      sx={[
        // Spread the passed-in sx prop (supports object or array form)
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {/* Titre + action à droite */}
      {!hasSelectedChatContext && (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 0.5 }}>
          <Button
            size="small"
            startIcon={<AddIcon />}
            onClick={(e) => setChatContextPickerAnchor(e.currentTarget)}
            sx={{ textTransform: "none", color: theme.palette.text.primary }}
          >
            {t("settings.chatContext")}
          </Button>
        </Box>
      )}

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
          selectionMode="multiple"
        />
      </Popover>

      {/* Carte compacte quand un profil est sélectionné */}
      {hasSelectedChatContext ? (
        <List dense disablePadding sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
          {selectedChatContextResources.map((resource) => {
            const preview = chatContextBodyPreviews[resource.id];
            return (
              <ListItem key={resource.id} disableGutters sx={{ width: 170 }}>
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
                      {resource.name}
                    </Typography>

                    {Array.isArray(resource.labels) && resource.labels.length > 0 && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }} noWrap>
                        {resource.labels.join(" · ")}
                      </Typography>
                    )}

                    {preview && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={
                          {
                            mt: 0.5,
                            display: "-webkit-box",
                            WebkitLineClamp: "1",
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "normal",
                          } as any
                        }
                      >
                        {preview}
                      </Typography>
                    )}
                  </Box>

                  <Tooltip title={t("common.remove")}>
                    <IconButton
                      size="small"
                      onClick={(event) => {
                        event.stopPropagation();
                        applyChatContextSelection(selectedChatContextIds.filter((id) => id !== resource.id));
                      }}
                      sx={{ flexShrink: 0, opacity: 0.7 }}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      ) : null}
    </Box>
  );
}
