// AgentCard.tsx
import { Box, Card, CardContent, Typography, IconButton, Chip, Tooltip, Avatar } from "@mui/material";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
//import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";

import { getAgentBadge } from "../../utils/avatar";
import { useTranslation } from "react-i18next";
import { Agent } from "../../slices/chatApiStructures";

interface AgentCardProps {
  agent: Agent;
  isFavorite: boolean;
  onToggleFavorite: (name: string) => void;
  onDelete: (name: string) => void;
  allAgents: Agent[];
}
export const AgentCard = ({
  agent,
  isFavorite,
  onToggleFavorite,
  onDelete,
  allAgents = [],
}: AgentCardProps) => {
  const { t } = useTranslation();

  return (
    <Card
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        borderRadius: 3,
        boxShadow: 2,
        transition: "transform 0.2s, box-shadow 0.2s",
        "&:hover": {
          transform: "translateY(-4px)",
          boxShadow: 4,
        },
        border: `1px solid #ccc`,
      }}
    >
      <Box
        sx={{
          p: 2,
          pb: 0,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center" }}>
          <Box sx={{ mr: 1.5 }}>{getAgentBadge(agent.nickname)}</Box>
          <Box>
            <Typography variant="h6" sx={{ fontSize: "1rem", fontWeight: 600 }}>
              {agent.nickname}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {agent.role}
            </Typography>
          </Box>
        </Box>

        <Box sx={{ display: "flex", alignItems: "center" }}>
          {agent.tag && (
            <Tooltip title={t("agentCard.taggedWith", { tag: agent.tag })}>
              <Chip
                icon={<LocalOfferIcon fontSize="small" />}
                label={agent.tag}
                size="small"
                sx={{ mr: 1, height: 24, fontSize: "0.7rem" }}
              />
            </Tooltip>
          )}

          <IconButton
            size="small"
            onClick={() => onToggleFavorite(agent.name)}
            sx={{ color: isFavorite ? "warning.main" : "text.secondary" }}
          >
            {isFavorite ? <StarIcon /> : <StarOutlineIcon />}
          </IconButton>
          {/* <Tooltip title={t("agentCard.edit")}>
            <IconButton size="small" onClick={() => onEdit(agent)} sx={{ ml: 0.5 }}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip> */}

          <Tooltip title={t("agentCard.delete")}>
            <IconButton size="small" onClick={() => onDelete(agent.name)} sx={{ ml: 0.5 }}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      <CardContent sx={{ flexGrow: 1, pt: 1 }}>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            mb: 2,
            minHeight: "3.6em",
            fontSize: "0.85rem",
          }}
        >
          {agent.description}
        </Typography>

        {agent.experts?.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              {t("agentCard.expertIntegrations")}
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {agent.experts.map((expertName) => {
                const expert = allAgents.find((a) => a.name === expertName);
                return expert ? (
                  <Tooltip key={expertName} title={expert.description}>
                    <Chip
                      avatar={<Avatar sx={{ width: 20, height: 20 }}>{getAgentBadge(expert.nickname)}</Avatar>}
                      label={expert.nickname}
                      size="small"
                      sx={{
                        height: 24,
                        fontSize: "0.7rem",
                        "& .MuiChip-avatar": {
                          width: 18,
                          height: 18,
                        },
                      }}
                    />
                  </Tooltip>
                ) : null;
              })}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};
