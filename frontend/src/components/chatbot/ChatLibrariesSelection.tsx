import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import TextsmsIcon from "@mui/icons-material/Textsms";
import {
  Badge,
  Box,
  Checkbox,
  IconButton,
  Popover,
  Stack,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  TagType,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface ChatLibrariesSelectionProps {
  selectedLibrariesIds: string[];
  setSelectedLibrariesIds: (ids: string[]) => void;
  libraryType: TagType;
}

export function ChatLibrariesSelection({
  selectedLibrariesIds,
  setSelectedLibrariesIds,
  libraryType,
}: ChatLibrariesSelectionProps) {
  const { t } = useTranslation();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const Icon = libraryType === "prompt" ? TextsmsIcon : LibraryBooksIcon;
  const tooltipText =
    libraryType === "prompt"
      ? t("chatbot.tooltip.selectPromptLibraries")
      : t("chatbot.tooltip.selectDocumentLibraries");

  const handleClick = (event: React.MouseEvent<HTMLElement>) => setAnchorEl(event.currentTarget);
  const handleClose = () => setAnchorEl(null);
  const open = Boolean(anchorEl);
  const id = open ? "chat-libraries-popover" : undefined;

  return (
    <>
      <Tooltip title={tooltipText} placement="top">
        <Badge
          badgeContent={selectedLibrariesIds.length > 0 ? selectedLibrariesIds.length : undefined}
          color="primary"
        >
          <IconButton sx={{ fontSize: "1.6rem", padding: "8px" }} onClick={handleClick}>
            <Icon fontSize="inherit" />
          </IconButton>
        </Badge>
      </Tooltip>

      <Popover
        id={id}
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
        transformOrigin={{ vertical: "bottom", horizontal: "center" }}
        slotProps={{ paper: { sx: { borderRadius: 4 } } }}
      >
        <LibrariesSelectionCard
          selectedLibrariesIds={selectedLibrariesIds}
          setSelectedLibrariesIds={setSelectedLibrariesIds}
          libraryType={libraryType}
        />
      </Popover>
    </>
  );
}

export function LibrariesSelectionCard({
  selectedLibrariesIds,
  setSelectedLibrariesIds,
  libraryType,
}: ChatLibrariesSelectionProps) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { data: libraries = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: libraryType });
  const [search, setSearch] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const filteredLibraries = useMemo(
    () =>
      libraries
        .filter((lib) => lib.name.toLowerCase().includes(search.toLowerCase()))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [libraries, search]
  );

  const toggleLibrary = (id: string) => {
    setSelectedLibrariesIds(
      selectedLibrariesIds.includes(id)
        ? selectedLibrariesIds.filter((libId) => libId !== id)
        : [...selectedLibrariesIds, id]
    );
  };
  const label =
    libraryType === "document"
      ? t("chatbot.searchDocumentLibraries")
      : t("chatbot.searchPromptLibraries");
  return (
    <Box sx={{ width: "380px", height: "406px", display: "flex", flexDirection: "column" }}>
      <Box sx={{ mx: 2, mt: 2, mb: 1 }}>
        <TextField
          autoFocus
          label={label}
          variant="outlined"
          size="small"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          fullWidth
        />
      </Box>

      <Stack
        sx={{
          overflowY: "auto",
          overflowX: "hidden",
          scrollbarWidth: "thin",
          px: 1,
        }}
      >
        {filteredLibraries.map((lib) => (
          <Box
            key={lib.id}
            sx={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              borderRadius: 2,
              transition: "background 0.2s",
              cursor: "pointer",
              minHeight: 40,
              "&:hover": { background: theme.palette.action.hover },
            }}
            onMouseEnter={(e) => {
              setHoveredId(lib.id);
              setAnchorEl(e.currentTarget);
            }}
            onMouseLeave={() => {
              setHoveredId(null);
              setAnchorEl(null);
            }}
            onClick={() => toggleLibrary(lib.id)}
          >
            <Checkbox
              checked={selectedLibrariesIds.includes(lib.id)}
              tabIndex={-1}
              disableRipple
              sx={{ mr: 1 }}
              onClick={(e) => e.stopPropagation()}
            />
            <Typography
              variant="body1"
              sx={{
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {lib.name}
            </Typography>

            {hoveredId === lib.id && anchorEl && (
              <Tooltip
                open
                title={
                  <>
                    <Typography color="inherit">{lib.name}</Typography>
                    {lib.description && (
                      <Typography
                        color="inherit"
                        fontWeight="light"
                        fontSize=".95rem"
                        fontStyle="italic"
                      >
                        {lib.description}
                      </Typography>
                    )}
                  </>
                }
                placement="right"
                disableInteractive
                PopperProps={{ anchorEl }}
              >
                <span />
              </Tooltip>
            )}
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
