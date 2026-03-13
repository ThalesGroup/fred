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
import CodeIcon from "@mui/icons-material/Code";
import ManageSearchIcon from "@mui/icons-material/ManageSearch";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";

import TuneIcon from "@mui/icons-material/Tune";
import { Box, Card, CardContent, IconButton, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

// OpenAPI types
import { AnyAgent, isLikelyV2DefinitionAgent } from "../../common/agent";
import { useFrontendProperties } from "../../hooks/useFrontendProperties";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";

type AgentCardProps = {
  agent: AnyAgent;
  onEdit?: (agent: AnyAgent) => void;
  onToggleEnabled?: (agent: AnyAgent) => void;
  onManageAssets?: (agent: AnyAgent) => void;
  onInspectCode?: (agent: AnyAgent) => void;
  onInspectAgent?: (agent: AnyAgent) => void;
};

/**
 * Fred architecture note (hover-worthy):
 * - The card shows **functional identity** (name, role, tags) to help users pick the right agent.
 * - Actions follow our minimal contract:
 * Edit → schema-driven tuning UI
 * Enable/Disable → operational switch
 * Delete → remove the agent
 */
export const AgentCard = ({
  agent,
  onEdit,
  onToggleEnabled,
  onManageAssets,
  onInspectCode,
  onInspectAgent,
}: AgentCardProps) => {
  const { t } = useTranslation();
  const isEnabled = agent.enabled !== false;
  const showInspection = Boolean(onInspectAgent && isLikelyV2DefinitionAgent(agent));

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
            <Typography
              variant="subtitle1"
              color="primary"
              sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "1.125rem" }}
            >
              {agent.name}
            </Typography>
          </Box>
        </Box>

        {/* ROW 2: Agent Role (Moved here) */}
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body1" color="textPrimary" sx={{ lineHeight: 1.25 }}>
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
          {onManageAssets && (
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
          {onEdit && (
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
          {showAgentCode && onInspectCode && (
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
          {showInspection && (
            <SimpleTooltip title={t("agentCard.inspectAgent", "Inspect agent")}>
              <IconButton
                size="small"
                onClick={() => onInspectAgent?.(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="inspect agent"
              >
                <ManageSearchIcon fontSize="small" />
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
