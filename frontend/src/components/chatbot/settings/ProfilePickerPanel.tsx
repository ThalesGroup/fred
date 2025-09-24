// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import { useMemo, useState } from "react";
import {
  Box,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  Tooltip,
  Typography,
  useTheme,
  Theme,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import Popover from "@mui/material/Popover";
import { useTranslation } from "react-i18next";
import {
  useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { ChatResourcesSelectionCard } from "../ChatResourcesSelectionCard";

export type ProfilePickerPanelProps = {
  selectedProfileIds: string[];
  onChangeSelectedProfileIds: (ids: string[]) => void;
};

export function ProfilePickerPanel({
  selectedProfileIds,
  onChangeSelectedProfileIds,
}: ProfilePickerPanelProps) {
  const theme = useTheme<Theme>();
  const { t } = useTranslation();

  const [profilePickerAnchor, setProfilePickerAnchor] = useState<HTMLElement | null>(null);
  const selectedProfileId = selectedProfileIds[0] ?? null;

  const { data: selectedProfileResource } =
    useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery(
      { resourceId: selectedProfileId as string },
      { skip: !selectedProfileId }
    );

  const hasSelectedProfile = !!selectedProfileId;

  const profileBodyPreview = useMemo(() => {
    const c = selectedProfileResource?.content ?? "";
    const sep = "\n---\n";
    const i = c.indexOf(sep);
    const body = (i !== -1 ? c.slice(i + sep.length) : c).replace(/\r\n/g, "\n").trim();
    if (!body) return null;
    const oneline = body.split("\n").filter(Boolean).slice(0, 2).join(" ");
    return oneline.length > 180 ? oneline.slice(0, 180) + "…" : oneline;
  }, [selectedProfileResource]);

  const applyProfileSelection = (ids: string[]) => {
    // mono-sélection (dernier choisi gagne)
    const next = ids.length > 0 ? [ids[ids.length - 1]] : [];
    onChangeSelectedProfileIds(next);
    setProfilePickerAnchor(null);
  };

  return (
    <Box
      sx={{
        px: 1,
        py: 1,
        borderBottom: `1px solid ${theme.palette.divider}`,
        backgroundColor: theme.palette.sidebar.background,
      }}
    >
      {/* Titre + action à droite */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="subtitle1" sx={{ pl: 1 }}>
          {t("settings.profile")}
        </Typography>

        {!hasSelectedProfile && (
          <Tooltip title={t("settings.selectProfile", "Select a profile")}>
            <IconButton
              size="small"
              onClick={(e) => setProfilePickerAnchor(e.currentTarget)}
              sx={{ borderRadius: 1.5 }}
            >
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Popover de sélection/modification */}
      <Popover
        open={Boolean(profilePickerAnchor)}
        anchorEl={profilePickerAnchor}
        onClose={() => setProfilePickerAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        PaperProps={{ sx: { p: 1 } }}
      >
        <ChatResourcesSelectionCard
          libraryType={"profile"}
          selectedResourceIds={selectedProfileIds}
          setSelectedResourceIds={applyProfileSelection}
        />
      </Popover>

      {/* Carte compacte quand un profil est sélectionné */}
      {hasSelectedProfile && (
        <List dense disablePadding sx={{ mt: 1 }}>
          <ListItem disableGutters sx={{ mb: 0 }}>
            <ListItemButton
              dense
              selected
              onClick={(e) => setProfilePickerAnchor(e.currentTarget)}
              sx={{
                borderRadius: 1,
                px: 1,
                py: 0.75,
                alignItems: "flex-start",
                border: `1px solid ${theme.palette.primary.main}`,
                backgroundColor:
                  theme.palette.mode === "dark"
                    ? "rgba(25,118,210,0.06)"
                    : "rgba(25,118,210,0.04)",
                "&:hover": {
                  backgroundColor:
                    theme.palette.mode === "dark"
                      ? "rgba(25,118,210,0.1)"
                      : "rgba(25,118,210,0.08)",
                },
              }}
            >
              <Box sx={{ width: "100%", minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                  {selectedProfileResource?.name}
                </Typography>

                {Array.isArray(selectedProfileResource?.labels) &&
                  selectedProfileResource!.labels.length > 0 && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block" }} noWrap>
                      {selectedProfileResource!.labels.join(" · ")}
                    </Typography>
                  )}

                {profileBodyPreview && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{
                      mt: 0.5,
                      display: "-webkit-box",
                      WebkitLineClamp: "2",
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "normal",
                    } as any}
                  >
                    {profileBodyPreview}
                  </Typography>
                )}
              </Box>
            </ListItemButton>
          </ListItem>
        </List>
      )}
    </Box>
  );
}
