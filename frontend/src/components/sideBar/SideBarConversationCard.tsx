import PersonIcon from "@mui/icons-material/Person";
import { alpha, Box, Skeleton, Typography, useTheme } from "@mui/material";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";
import {
  SessionWithFiles,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
} from "../../slices/agentic/agenticOpenApi";
import { useToast } from "../ToastProvider";

interface SideBarConversationCardProps {
  session: SessionWithFiles;
  refetchSessions: () => void;
}

export function SideBarConversationCard({ session, refetchSessions }: SideBarConversationCardProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const location = useLocation();
  const navigate = useNavigate();

  const isSelected = location.pathname === `/chat/${session.id}`;

  const { showError } = useToast();
  const [deleteSessionMutation] = useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    try {
      await deleteSessionMutation({ sessionId: session.id }).unwrap();
      refetchSessions();

      if (isSelected) {
        navigate("/");
      }
    } catch (error) {
      console.error("Failed to delete conversation: ", error);
      showError(t("sidebar.deleteSessionFailed"));
    }
  };

  return (
    <Box
      component={Link}
      to={`/chat/${session.id}`}
      sx={{
        textDecoration: "none",
        color: "inherit",
        display: "block",
      }}
    >
      <Box
        sx={{
          px: 1.5,
          py: 1,
          borderRadius: 1,
          userSelect: "none",
          background: isSelected ? alpha(theme.palette.primary.main, 0.16) : "transparent",
          ...(isSelected ? {} : { "&:hover": { background: theme.palette.action.hover } }),
          "&:hover .delete-button": { display: "flex" },
          display: "flex",
          alignItems: "center",
          gap: 1,
        }}
      >
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            flex: 1,
          }}
        >
          {/* Title */}
          <Typography
            variant="body2"
            sx={{
              color: theme.palette.text.primary,
              textOverflow: "ellipsis",
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {session.title}
          </Typography>

          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            {/* Agent name */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <PersonIcon sx={{ fontSize: "1rem", color: theme.palette.primary.main }} />
              <Typography variant="caption" sx={{ color: theme.palette.primary.main }}>
                {session.agents.length > 0 ? session.agents[0].name || "?" : "..."}
              </Typography>
            </Box>
            <Typography variant="caption" color="textDisabled">
              •
            </Typography>

            {/* Date */}
            <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
              {dayjs(session.updated_at).format("L")}
            </Typography>
          </Box>
        </Box>

        {/* Delete button */}
        <DeleteIconButton
          className="delete-button"
          size="small"
          onClick={handleDelete}
          color="error"
          sx={{
            display: "none",
          }}
        />
      </Box>
    </Box>
  );
}

export function SideBarConversationCardSkeleton() {
  return (
    <Box sx={{ px: 1.5, py: 1, borderRadius: 1, height: "75.83px" }}>
      <Skeleton variant="rectangular" height="100%" width="100%" sx={{ borderRadius: 1 }} />
    </Box>
  );
}
