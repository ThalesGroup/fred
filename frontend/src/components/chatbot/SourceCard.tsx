import { useTheme } from "@mui/material/styles";
import {
  Card,
  CardContent,
  Tooltip,
  Typography,
  Box,
  IconButton,
  Divider,
  Chip,
} from "@mui/material";
import VisibilityIcon from "@mui/icons-material/Visibility";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import HistoryIcon from "@mui/icons-material/History";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import dayjs from "dayjs";
import { getDocumentIcon } from "../documents/DocumentIcon";
import { ChatSource } from "../../slices/chatApiStructures.ts";

/**
 * Props for the SourceCard component
 */
interface SourceCardProps {
  source: ChatSource; // Document metadata to display
  onCardClick: () => void; // Callback when the card itself is clicked
  onViewDocument: (event: React.MouseEvent) => void; // Callback when preview icon is clicked
  loading: boolean; // If true, disables the preview button while fetching
}

/**
 * SourceCard
 *
 * A visual summary of a single document source, designed to be displayed in a card grid.
 * Shows:
 * - Document icon
 * - File name
 * - Title, last modified date
 * - Agent name (if any)
 * - A preview button
 *
 * Triggers:
 * - `onCardClick` for full card interaction
 * - `onViewDocument` for explicit preview
 */
export const SourceCard = ({
  source,
  onCardClick,
  onViewDocument,
  loading,
}: SourceCardProps) => {
  const theme = useTheme();

  // Formats date strings into DD/MM/YYYY
  const formatDate = (dateString?: string) =>
    dateString ? dayjs(dateString).format("DD/MM/YYYY") : "N/A";

  return (
    <Card
      onClick={onCardClick}
      sx={{
        width: 220,
        height: 180,
        cursor: "pointer",
        transition: "transform 0.2s, box-shadow 0.2s",
        "&:hover": {
          transform: "translateY(-4px)",
          boxShadow: 3,
        },
        display: "flex",
        flexDirection: "column",
        position: "relative",
        overflow: "visible",
      }}
    >
      {/* Floating document icon (top-left corner) */}
      <Box
        sx={{
          position: "absolute",
          top: -10,
          left: 10,
          bgcolor: theme.palette.background.paper,
          borderRadius: "50%",
          p: 1,
          boxShadow: 1,
          display: "flex",
          zIndex: 1,
        }}
      >
        {getDocumentIcon(source.file_name)}
      </Box>

      {/* Main content */}
      <CardContent
        sx={{
          p: 2,
          pt: 3,
          flex: 1,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Filename with ellipsis truncation */}
        <Typography
          variant="subtitle1"
          sx={{
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            fontWeight: "medium",
            mb: 1,
            mt: 1,
          }}
        >
          {source.file_name}
        </Typography>

        <Divider sx={{ my: 1 }} />

        {/* Document metadata (title, date, agent) */}
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 0.5 }}>
          {/* Title line with info icon */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <InfoOutlinedIcon fontSize="small" color="action" sx={{ fontSize: "0.9rem" }} />
            <Typography
              variant="body2"
              sx={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                display: "-webkit-box",
                WebkitLineClamp: 1,
                WebkitBoxOrient: "vertical",
              }}
            >
              {source.title ?? "Title unavailable"}
            </Typography>
          </Box>

          {/* Last modified date */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <HistoryIcon fontSize="small" color="action" sx={{ fontSize: "0.9rem" }} />
            <Typography variant="body2" color="text.secondary">
              {formatDate(source.modified)}
            </Typography>
          </Box>

          {/* Agent chip (if provided) */}
          {source.agent_name && (
            <Chip
              icon={<PersonOutlineIcon sx={{ fontSize: "0.9rem" }} />}
              label={source.agent_name}
              size="small"
              sx={{
                height: 24,
                "& .MuiChip-label": { px: 1, fontSize: "0.75rem" },
                alignSelf: "flex-start",
                mt: 0.5,
              }}
            />
          )}
        </Box>

        {/* Preview icon (bottom-right, floating) */}
        <Tooltip title="Preview the document">
          <IconButton
            onClick={onViewDocument}
            disabled={loading}
            size="small"
            sx={{
              position: "absolute",
              bottom: 8,
              right: 8,
              padding: "8px",
              bgcolor: theme.palette.background.paper,
              boxShadow: 1,
              transition: "all 0.2s",
              "&:hover": {
                bgcolor: theme.palette.primary.light,
                color: theme.palette.primary.contrastText,
              },
            }}
          >
            <VisibilityIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </CardContent>
    </Card>
  );
};
