// AgentCard.tsx (Updated Layout)

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
import CloudQueueIcon from "@mui/icons-material/CloudQueue";
import CodeIcon from "@mui/icons-material/Code";
import GroupIcon from "@mui/icons-material/Group"; // for crew
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import VisibilityIcon from "@mui/icons-material/Visibility";

import TuneIcon from "@mui/icons-material/Tune";
import { Box, Card, CardContent, IconButton, Stack, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

// OpenAPI types
import { AnyAgent } from "../../common/agent";
import { AgentChipWithIcon } from "../../common/AgentChip";
import { useFrontendProperties } from "../../hooks/useFrontendProperties";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
import { Leader } from "../../slices/agentic/agenticOpenApi";

type AgentCardProps = {
  agent: AnyAgent;
  onEdit?: (agent: AnyAgent) => void;
  onToggleEnabled?: (agent: AnyAgent) => void;
  onManageCrew?: (leader: Leader & { type: "leader" }) => void; // only visible for leaders
  onManageAssets?: (agent: AnyAgent) => void;
  onInspectCode?: (agent: AnyAgent) => void;
  onViewA2ACard?: (agent: AnyAgent) => void;
};

/**
 * Fred architecture note (hover-worthy):
 * - The card shows **functional identity** (name, role, tags) to help users pick the right agent.
 * - Actions follow our minimal contract:
 * Edit → schema-driven tuning UI
 * Enable/Disable → operational switch
 * Delete → remove the agent
 * Manage Crew → leader-only relation editor (leader owns crew membership)
 */
export const AgentCard = ({
  agent,
  onEdit,
  onToggleEnabled,
  onManageCrew,
  onManageAssets,
  onInspectCode,
  onViewA2ACard,
}: AgentCardProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const isEnabled = agent.enabled !== false;
  const hasA2aCard = Boolean(agent.metadata && (agent.metadata as any).a2a_card);
  const isA2A = Boolean(agent.metadata && (agent.metadata as any).a2a_base_url);
  const a2aBorder = theme.palette.success.main;

  const { showAgentCode, showAgentDisableButton } = useFrontendProperties();

  return (
    <Card
      sx={{
        pt: 2,
        px: 2,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        transition: "border-color 0.2s ease, transform 0.2s ease",
        userSelect: "none",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          flexDirection: "column", // Stack content vertically
          gap: 0.25,
          opacity: isEnabled ? 1 : 0.4,
        }}
      >
        {/* ROW 1: Chip + Tags + Favorite Star */}
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "1fr auto", // Agent Chip left, Actions right
            columnGap: 1,
            alignItems: "center",
          }}
        >
          {/* Left: Agent Chip (includes name) */}
          <Box sx={{ flexShrink: 0 }}>
            {isA2A ? (
              <Box
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.6,
                  minWidth: 0,
                }}
              >
                <CloudQueueIcon
                  sx={{
                    fontSize: 18,
                    color: a2aBorder,
                    flexShrink: 0,
                  }}
                />
                <Typography
                  variant="body1"
                  fontWeight={700}
                  sx={{
                    color: a2aBorder,
                    lineHeight: 1.2,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    maxWidth: 180,
                  }}
                  title={agent.name}
                >
                  {agent.name}
                </Typography>
              </Box>
            ) : (
              <AgentChipWithIcon agent={agent} />
            )}
          </Box>
        </Box>

        {/* ROW 2: Agent Role (Moved here) */}
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" color="textPrimary" sx={{ lineHeight: 1.25, fontWeight: 500 }}>
            {agent.tuning.role}
          </Typography>
        </Box>
      </Box>

      {/* Body */}
      <CardContent
        sx={{
          p: 0,
          display: "flex",
          flexDirection: "column",
          gap: 1,
          flexGrow: 1,
        }}
      >
        {/* Description — clamp to 3 lines for uniform height */}
        <Typography
          variant="body2"
          color="textSecondary"
          sx={{
            mb: 0.5,
            display: "-webkit-box",
            WebkitBoxOrient: "vertical",
            WebkitLineClamp: 3,
            overflow: "hidden",
            minHeight: "3.6em", // ~3 lines @ 1.2 line-height
            flexGrow: 1,
            opacity: isEnabled ? 1 : 0.75,
          }}
        >
          {agent.tuning.description}
        </Typography>
        {/* Footer actions (unchanged) */}
        <Stack direction="row" gap={0.5} sx={{ ml: "auto" }}>
          {agent.type === "leader" && onManageCrew && (
            <SimpleTooltip title={t("agentCard.manageCrew", "Manage crew")}>
              <IconButton
                size="small"
                onClick={() => onManageCrew(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="manage crew"
              >
                <GroupIcon fontSize="small" />
              </IconButton>
            </SimpleTooltip>
          )}
          {!isA2A && onManageAssets && (
            <SimpleTooltip title={t("agentCard.manageAssets")}>
              <IconButton
                size="small"
                onClick={() => onManageAssets(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="manage agent assets"
              >
                <AttachFileIcon fontSize="small" />
              </IconButton>
            </SimpleTooltip>
          )}
          {!isA2A && onEdit && (
            <SimpleTooltip title={t("agentCard.edit")}>
              <IconButton
                size="small"
                onClick={() => onEdit(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="edit agent"
              >
                <TuneIcon fontSize="small" />
              </IconButton>
            </SimpleTooltip>
          )}
          {!isA2A && showAgentCode && onInspectCode && (
            <SimpleTooltip title={t("agentCard.inspectCode", "Inspect Source Code")}>
              <IconButton
                size="small"
                // This calls the handler provided by the parent (AgentHub)
                onClick={() => onInspectCode(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="inspect agent source code"
              >
                <CodeIcon fontSize="small" />
              </IconButton>
            </SimpleTooltip>
          )}
          {onViewA2ACard && hasA2aCard && (
            <SimpleTooltip title={t("agentCard.viewA2ACard", "View A2A card")}>
              <IconButton
                size="small"
                onClick={() => onViewA2ACard(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="view a2a card"
              >
                <VisibilityIcon fontSize="small" />
              </IconButton>
            </SimpleTooltip>
          )}

          {showAgentDisableButton && onToggleEnabled && (
            <SimpleTooltip title={isEnabled ? t("agentCard.disable") : t("agentCard.enable")}>
              <IconButton
                size="small"
                onClick={() => onToggleEnabled(agent)}
                sx={{ color: "text.secondary" }} // Button color is neutral
                aria-label={isEnabled ? "disable agent" : "enable agent"}
              >
                <PowerSettingsNewIcon fontSize="small" />
              </IconButton>
            </SimpleTooltip>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
};
