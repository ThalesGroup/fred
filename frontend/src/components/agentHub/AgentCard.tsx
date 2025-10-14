// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CodeIcon from "@mui/icons-material/Code";
import DeleteIcon from "@mui/icons-material/Delete";
import GroupIcon from "@mui/icons-material/Group"; // for crew
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import PowerOffIcon from "@mui/icons-material/PowerOff"; // for disable
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import StarIcon from "@mui/icons-material/Star";

import StarOutlineIcon from "@mui/icons-material/StarOutline";
import TuneIcon from "@mui/icons-material/Tune";
import { Box, Card, CardContent, Chip, IconButton, Stack, Tooltip, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import { getAgentBadge } from "../../utils/avatar";

// OpenAPI types
import { AnyAgent } from "../../common/agent";
import { Leader } from "../../slices/agentic/agenticOpenApi";

type AgentCardProps = {
  agent: AnyAgent;
  isFavorite?: boolean;
  onToggleFavorite?: (name: string) => void;
  onEdit?: (agent: AnyAgent) => void;
  onToggleEnabled?: (agent: AnyAgent) => void;
  onManageCrew?: (leader: Leader & { type: "leader" }) => void; // only visible for leaders
  onDelete?: (agent: AnyAgent) => void;
  onManageAssets?: (agent: AnyAgent) => void;
  onInspectCode?: (agent: AnyAgent) => void;
};

/**
 * Fred architecture note (hover-worthy):
 * - The card shows **functional identity** (name, role, tags) to help users pick the right agent.
 * - Actions follow our minimal contract:
 *   Edit → schema-driven tuning UI
 *   Enable/Disable → operational switch (no delete)
 *   Manage Crew → leader-only relation editor (leader owns crew membership)
 */
export const AgentCard = ({
  agent,
  isFavorite = false,
  onToggleFavorite,
  onEdit,
  onToggleEnabled,
  onManageCrew,
  onDelete,
  onManageAssets,
  onInspectCode,
}: AgentCardProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const tags = agent.tags ?? [];
  const tagLabel = tags.join(", ");

  return (
    <Card
      variant="outlined"
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        borderRadius: 2,
        bgcolor: "transparent",
        borderColor: "divider",
        boxShadow: "none",
        transition: "border-color 0.2s ease, transform 0.2s ease",
        "&:hover": {
          transform: "translateY(-2px)",
          borderColor: theme.palette.primary.main,
        },
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 1.5,
          pb: 0.5,
          display: "grid",
          gridTemplateColumns: "1fr auto", // left grows, right auto width
          columnGap: 1,
          alignItems: "start",
          opacity: agent.enabled ? 1 : 0.5,
        }}
      >
        {/* Left: badge + name + role */}
        <Box sx={{ display: "flex", alignItems: "center", minWidth: 0 }}>
          <Box sx={{ mr: 1, flexShrink: 0, lineHeight: 0 }}>{getAgentBadge(agent.name, agent.type === "leader")}</Box>
          <Box sx={{ minWidth: 0, flex: "1 1 auto" }}>
            <Typography variant="h6" color="text.secondary" sx={{ lineHeight: 1.25 }}>
              {agent.name}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.25 }}>
              {agent.role}
            </Typography>
          </Box>
        </Box>

        {/* Right: tags + favorite */}
        <Box sx={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
          {tags.length > 0 && (
            <Tooltip title={t("agentCard.taggedWith", { tag: tagLabel })}>
              <Chip
                icon={<LocalOfferIcon fontSize="small" />}
                label={tagLabel}
                size="small"
                sx={{
                  mr: 0.5,
                  height: 22,
                  fontSize: "0.7rem",
                  bgcolor: "transparent",
                  border: (th) => `1px solid ${th.palette.divider}`,
                  "& .MuiChip-icon": { mr: 0.25 },
                  "& .MuiChip-label": {
                    maxWidth: 140,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  },
                }}
              />
            </Tooltip>
          )}

          {onToggleFavorite && (
            <Tooltip title={isFavorite ? t("agentCard.unfavorite") : t("agentCard.favorite")}>
              <IconButton
                size="small"
                onClick={() => onToggleFavorite(agent.name)}
                sx={{ color: isFavorite ? "warning.main" : "text.secondary" }}
              >
                {isFavorite ? <StarIcon fontSize="small" /> : <StarOutlineIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Box>

      {/* Body */}
      <CardContent
        sx={{
          display: "flex",
          flexDirection: "column",
          gap: 1,
          pt: 1,
          pb: 1.5,
          flexGrow: 1,
        }}
      >
        {/* Description — clamp to 3 lines for uniform height */}
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            mb: 0.5,
            display: "-webkit-box",
            WebkitBoxOrient: "vertical",
            WebkitLineClamp: 3,
            overflow: "hidden",
            minHeight: "3.6em", // ~3 lines @ 1.2 line-height
            flexGrow: 1,
            opacity: agent.enabled ? 1 : 0.5,
          }}
          title={agent.description || ""}
        >
          {agent.description}
        </Typography>
        {/* Footer actions */}
        <Stack direction="row" gap={0.5} sx={{ ml: "auto" }}>
          {agent.type === "leader" && onManageCrew && (
            <Tooltip title={t("agentCard.manageCrew", "Manage crew")}>
              <IconButton
                size="small"
                onClick={() => onManageCrew(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="manage crew"
              >
                <GroupIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {onManageAssets && (
            <Tooltip title={t("agentCard.manageAssets")}>
              <IconButton
                size="small"
                onClick={() => onManageAssets(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="manage agent assets"
              >
                <AttachFileIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {onEdit && (
            <Tooltip title={t("agentCard.edit")}>
              <IconButton
                size="small"
                onClick={() => onEdit(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="edit agent"
              >
                <TuneIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {onInspectCode && (
            <Tooltip title={t("agentCard.inspectCode", "Inspect Source Code")}>
              <IconButton
                size="small"
                // This calls the handler provided by the parent (AgentHub)
                onClick={() => onInspectCode(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="inspect agent source code"
              >
                <CodeIcon fontSize="small" /> {/* 👈 Uses the imported icon */}
              </IconButton>
            </Tooltip>
          )}

          {onToggleEnabled && (
            <Tooltip title={agent.enabled ? t("agentCard.disable") : t("agentCard.enable", "Enable")}>
              <IconButton
                size="small"
                onClick={() => onToggleEnabled(agent)}
                sx={{ color: "text.secondary" }} // Button color is neutral
                aria-label={agent.enabled ? "disable agent" : "enable agent"}
              >
                {/* Conditional Icon to suggest the NEXT action */}
                {agent.enabled ? (
                  // If ENABLED, the next action is to DISABLE (turn OFF)
                  <PowerOffIcon fontSize="small" />
                ) : (
                  // If DISABLED, the next action is to ENABLE (turn ON)
                  <PowerSettingsNewIcon fontSize="small" />
                )}
              </IconButton>
            </Tooltip>
          )}
          {onDelete && (
            <Tooltip title={t("agentCard.delete")}>
              <IconButton
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(agent);
                }}
                sx={{ color: "text.secondary" }}
                aria-label="delete agent"
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Stack>{" "}
      </CardContent>
    </Card>
  );
};
