import AddIcon from "@mui/icons-material/Add";
import { Box, Button, MenuItem, Paper, Select, SelectChangeEvent, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useLocalStorageState } from "../../hooks/useLocalStorageState";
import { useGetSessionsAgenticV1ChatbotSessionsGetQuery } from "../../slices/agentic/agenticOpenApi";
import { SideBarConversationCard, SideBarConversationCardSkeleton } from "./SideBarConversationCard";

interface ConversationsSectionProps {
  isSidebarOpen: boolean;
}

export function SideBarConversationsSection({ isSidebarOpen }: ConversationsSectionProps) {
  const { t } = useTranslation();
  const theme = useTheme();

  const { data: sessions, refetch: refetchSessions } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
    refetchOnReconnect: true,
  });

  const allAgentOptionValue = "all-agents";
  const [selectedAgent, setSelectedAgent] = useLocalStorageState<string>(
    "ConversationsSection.selectedAgent",
    allAgentOptionValue,
  );

  const uniqueAgents = Array.from(new Set(sessions?.flatMap((s) => s.agents) ?? [])).sort();

  const filteredSessions =
    selectedAgent === allAgentOptionValue
      ? sessions
      : sessions?.filter((session) => session.agents.includes(selectedAgent));

  const sortedSessions = filteredSessions?.slice().sort((a, b) => {
    const dateA = new Date(a.updated_at).getTime();
    const dateB = new Date(b.updated_at).getTime();
    return dateB - dateA;
  });
  return (
    <>
      {/* Conversation header */}
      {isSidebarOpen && (
        <Paper elevation={1}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", px: 2, py: 1 }}>
            <Typography variant="subtitle2" sx={{ color: theme.palette.text.secondary }}>
              {t("sidebar.chat")}
            </Typography>
            <Button component={Link} to="/" variant="outlined" size="small" startIcon={<AddIcon />}>
              {t("common.create")}
            </Button>
          </Box>
          <Box sx={{ px: 2, py: 1 }}>
            <Select
              size="small"
              value={selectedAgent}
              onChange={(event: SelectChangeEvent) => setSelectedAgent(event.target.value as string)}
              sx={{ width: "100%" }}
            >
              <MenuItem value={allAgentOptionValue}>{t("sidebar.allAgents")}</MenuItem>
              {uniqueAgents.map((agent) => (
                <MenuItem key={agent} value={agent}>
                  {agent}
                </MenuItem>
              ))}
            </Select>
          </Box>
        </Paper>
      )}

      {/* Conversation list */}
      <Paper
        elevation={0}
        sx={{ flexGrow: 1, overflowY: "auto", overflowX: "hidden", scrollbarWidth: "none", py: 1, px: 1 }}
      >
        {isSidebarOpen &&
          sortedSessions === undefined &&
          [...Array(15)].map((_, index) => <SideBarConversationCardSkeleton key={`skeleton-${index}`} />)}

        {isSidebarOpen &&
          sortedSessions !== undefined &&
          sortedSessions.map((session) => (
            <SideBarConversationCard key={session.id} session={session} refetchSessions={refetchSessions} />
          ))}
      </Paper>
    </>
  );
}
