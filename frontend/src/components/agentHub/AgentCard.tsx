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
import CodeIcon from "@mui/icons-material/Code";
import EditIcon from "@mui/icons-material/Edit";
import ManageSearchIcon from "@mui/icons-material/ManageSearch";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { Box, Button, Card, IconButton, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
// OpenAPI types
import TryIcon from "@mui/icons-material/Try";
import { Link } from "react-router-dom";
import { AnyAgent, isLikelyV2DefinitionAgent } from "../../common/agent";
import { useFrontendProperties } from "../../hooks/useFrontendProperties";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
type AgentCardProps = {
  agent: AnyAgent;
  onEdit?: (agent: AnyAgent) => void;
  onToggleEnabled?: (agent: AnyAgent) => void;
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
export const AgentCard = ({ agent, onEdit, onToggleEnabled, onInspectCode, onInspectAgent }: AgentCardProps) => {
  const { t } = useTranslation();
  const isEnabled = agent.enabled !== false;
  const showInspection = Boolean(onInspectAgent && isLikelyV2DefinitionAgent(agent));

  const { showAgentCode, showAgentDisableButton } = useFrontendProperties();

  return (
    <Card
      sx={{
        pt: 1.5,
        pb: 2,
        px: 2,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
        transition: "border-color 0.2s ease, transform 0.2s ease",
        userSelect: "none",
        borderRadius: 4,
        "@supports (corner-shape: squircle)": {
          borderRadius: 6,
          cornerShape: "squircle",
        },
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
          <Box sx={{ minWidth: 0 }}>
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
          <Typography
            variant="body1"
            color="textPrimary"
            sx={{ lineHeight: 1.25, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {agent.tuning.role}
          </Typography>
        </Box>
      </Box>

      {/* Body */}
      <Box
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
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Stack direction="row" gap={0.5}>
            {onEdit && (
              <IconButton
                size="medium"
                onClick={() => onEdit(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="edit agent"
              >
                <EditIcon fontSize="medium" />
              </IconButton>
            )}
            {showAgentCode && onInspectCode && (
              <SimpleTooltip title={t("agentCard.inspectCode", "Inspect Source Code")}>
                <IconButton
                  size="medium"
                  // This calls the handler provided by the parent (AgentHub)
                  onClick={() => onInspectCode(agent)}
                  sx={{ color: "text.secondary" }}
                  aria-label="inspect agent source code"
                >
                  <CodeIcon fontSize="medium" />
                </IconButton>
              </SimpleTooltip>
            )}
            {showInspection && (
              <IconButton
                size="medium"
                onClick={() => onInspectAgent?.(agent)}
                sx={{ color: "text.secondary" }}
                aria-label="inspect agent"
              >
                <ManageSearchIcon fontSize="medium" />
              </IconButton>
            )}
            {showAgentDisableButton && onToggleEnabled && (
              <IconButton
                size="medium"
                onClick={() => onToggleEnabled(agent)}
                sx={{ color: "text.secondary" }} // Button color is neutral
                aria-label={isEnabled ? "disable agent" : "enable agent"}
              >
                {isEnabled ? <VisibilityIcon fontSize="medium" /> : <VisibilityOffIcon fontSize="medium" />}
              </IconButton>
            )}
          </Stack>
          <Button
            size="medium"
            variant="outlined"
            startIcon={<TryIcon />}
            component={Link}
            to={`/new-chat/${agent.id}`}
          >
            Chat
          </Button>
        </Box>
      </Box>
    </Card>
  );
};
