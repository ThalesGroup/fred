// components/agentHub/AgentCard.tsx
import { Box, Card, CardContent, Typography, IconButton, Chip, Tooltip, Avatar, useTheme } from "@mui/material";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import DeleteIcon from "@mui/icons-material/Delete";

import { getAgentBadge } from "../../utils/avatar";
import { useTranslation } from "react-i18next";
import { AgenticFlow } from "../../slices/agentic/agenticOpenApi";

interface AgentCardProps {
  agent: AgenticFlow;
  isFavorite: boolean;
  onToggleFavorite: (name: string) => void;
  onDelete: (name: string) => void;
  allAgents: AgenticFlow[];
}

export const AgentCard = ({ agent, isFavorite, onToggleFavorite, onDelete, allAgents = [] }: AgentCardProps) => {
  const { t } = useTranslation();
  const theme = useTheme();

  // Keep the grid tidy: cap visible experts to avoid variable card heights
  const MAX_VISIBLE_EXPERTS = 4;
  const expertObjects = (agent.experts || [])
    .map((name) => allAgents.find((a) => a.name === name))
    .filter(Boolean) as AgenticFlow[];
  const visibleExperts = expertObjects.slice(0, MAX_VISIBLE_EXPERTS);
  const hiddenCount = Math.max(0, expertObjects.length - visibleExperts.length);

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
      {/* Header */}
      <Box
        sx={{
          p: 1.5,
          pb: 0.5,
          display: "grid",
          gridTemplateColumns: "1fr auto", // ← left grows, right is only as wide as needed
          columnGap: 1,
          alignItems: "start",
        }}
      >
        {/* Left side: badge + text (flex, allow shrink/ellipsis) */}
        <Box sx={{ display: "flex", alignItems: "center", minWidth: 0 }}>
          <Box sx={{ mr: 1, flexShrink: 0, lineHeight: 0 }}>{getAgentBadge(agent.nickname)}</Box>
          <Box sx={{ minWidth: 0, flex: "1 1 auto" }}>
            <Typography
              variant="subtitle1"
              noWrap
              sx={{
                fontWeight: 600,
                lineHeight: 1.2,
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: "100%", // ← no artificial cap anymore
                display: "block",
              }}
              title={agent.nickname}
            >
              {agent.nickname}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic", lineHeight: 1.25 }}>
              {agent.role}
            </Typography>
          </Box>
        </Box>

        {/* Right side: tag + actions (auto width) */}
        <Box sx={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
          {agent.tag && (
            <Tooltip title={t("agentCard.taggedWith", { tag: agent.tag })}>
              <Chip
                icon={<LocalOfferIcon fontSize="small" />}
                label={agent.tag}
                size="small"
                sx={{
                  mr: 0.5,
                  height: 22,
                  fontSize: "0.7rem",
                  bgcolor: "transparent",
                  border: (theme) => `1px solid ${theme.palette.divider}`,
                  "& .MuiChip-icon": { mr: 0.25 },
                  // keep the chip tidy so the name can breathe
                  "& .MuiChip-label": {
                    maxWidth: 110,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  },
                }}
              />
            </Tooltip>
          )}

          <Tooltip
            title={
              isFavorite
                ? t("agentCard.unfavorite", "Remove from favorites")
                : t("agentCard.favorite", "Add to favorites")
            }
          >
            <IconButton
              size="small"
              onClick={() => onToggleFavorite(agent.name)}
              sx={{ color: isFavorite ? "warning.main" : "text.secondary" }}
            >
              {isFavorite ? <StarIcon fontSize="small" /> : <StarOutlineIcon fontSize="small" />}
            </IconButton>
          </Tooltip>

          <Tooltip title={t("agentCard.delete")}>
            <IconButton size="small" onClick={() => onDelete(agent.name)} sx={{ ml: 0.25, color: "text.secondary" }}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
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
        {/* Description — clamped to 3 lines for uniform height */}
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
          }}
          title={agent.description || ""}
        >
          {agent.description}
        </Typography>

        {/* Experts (fixed-height block; shows up to 4 + “+N”) */}
        {expertObjects.length > 0 && (
          <Box sx={{ mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
              {t("agentCard.expertIntegrations")}
            </Typography>
            <Box
              sx={{
                display: "flex",
                flexWrap: "wrap",
                gap: 0.5,
                // keep the section compact & equal across cards
                maxHeight: 48,
                overflow: "hidden",
                position: "relative",
              }}
            >
              {visibleExperts.map((exp) => (
                <Tooltip key={exp.name} title={exp.description || ""}>
                  <Chip
                    size="small"
                    avatar={<Avatar sx={{ width: 18, height: 18, fontSize: 10 }}>{getAgentBadge(exp.nickname)}</Avatar>}
                    label={exp.nickname}
                    sx={{
                      height: 22,
                      fontSize: "0.7rem",
                      bgcolor: "transparent",
                      border: `1px solid ${theme.palette.divider}`,
                      "& .MuiChip-avatar": {
                        width: 18,
                        height: 18,
                        mr: 0.5,
                      },
                      "& .MuiChip-label": { px: 0.5 },
                    }}
                  />
                </Tooltip>
              ))}

              {hiddenCount > 0 && (
                <Tooltip
                  title={expertObjects
                    .slice(MAX_VISIBLE_EXPERTS)
                    .map((e) => e.nickname)
                    .join(", ")}
                >
                  <Chip
                    size="small"
                    label={`+${hiddenCount}`}
                    sx={{
                      height: 22,
                      fontSize: "0.7rem",
                      bgcolor: "transparent",
                      border: `1px solid ${theme.palette.divider}`,
                    }}
                  />
                </Tooltip>
              )}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};
