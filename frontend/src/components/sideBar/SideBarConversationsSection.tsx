import { Box, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
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

  const sortedSessions = sessions?.slice().sort((a, b) => {
    const dateA = new Date(a.updated_at).getTime();
    const dateB = new Date(b.updated_at).getTime();
    return dateB - dateA;
  });
  return (
    <>
      {/* Conversation header */}
      {isSidebarOpen && (
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1 }}>
            <Typography variant="subtitle2" sx={{ color: theme.palette.text.secondary }}>
              {t("sidebar.chat")}
            </Typography>
          </Box>
        </Box>
      )}

      {/* Conversation list */}
      <Box sx={{ flexGrow: 1, overflowY: "auto", overflowX: "hidden", scrollbarWidth: "none", pb: 1, px: 1 }}>
        {isSidebarOpen &&
          sortedSessions === undefined &&
          [...Array(15)].map((_, index) => <SideBarConversationCardSkeleton key={`skeleton-${index}`} />)}

        {isSidebarOpen &&
          sortedSessions !== undefined &&
          sortedSessions.map((session) => (
            <SideBarConversationCard key={session.id} session={session} refetchSessions={refetchSessions} />
          ))}
      </Box>
    </>
  );
}
