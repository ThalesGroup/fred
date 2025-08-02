import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
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
import { useState } from "react";
import { Tag, useListTagsKnowledgeFlowV1TagsGetQuery } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface ChatLibrariesSelectionProps {
  selectedLibrariesIds: string[];
  setSelectedLibrariesIds: (ids: string[]) => void;
}

// Icon that open / close the libraries selection
export function ChatLibrariesSelection({ selectedLibrariesIds, setSelectedLibrariesIds }: ChatLibrariesSelectionProps) {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const open = Boolean(anchorEl);
  const id = open ? "chat-libraries-popover" : undefined;

  return (
    <>
      {/* Icon button to open the popover */}
      <Tooltip title="Select Libraries that will be available to the agent">
        <Badge badgeContent={selectedLibrariesIds.length > 0 ? selectedLibrariesIds.length : undefined} color="primary">
          <IconButton sx={{ fontSize: "1.6rem", padding: "8px" }} onClick={handleClick}>
            <LibraryBooksIcon fontSize="inherit" />
          </IconButton>
        </Badge>
      </Tooltip>

      {/* Popover card */}
      <Popover
        id={id}
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{
          vertical: "top",
          horizontal: "center",
        }}
        transformOrigin={{
          vertical: "bottom",
          horizontal: "center",
        }}
        slotProps={{
          paper: {
            sx: {
              borderRadius: 4,
            },
          },
        }}
      >
        <LibrariesSelectionCard
          selectedLibrariesIds={selectedLibrariesIds}
          setSelectedLibrariesIds={setSelectedLibrariesIds}
        />
      </Popover>
    </>
  );
}

export interface LibrariesSelectionCardProps {
  selectedLibrariesIds: string[];
  setSelectedLibrariesIds: (ids: string[]) => void;
}

// List of libraries with search and selection
export function LibrariesSelectionCard({ selectedLibrariesIds, setSelectedLibrariesIds }: LibrariesSelectionCardProps) {
  const theme = useTheme();
  const { data: libraries } = useListTagsKnowledgeFlowV1TagsGetQuery();
  const [search, setSearch] = useState("");
  const [hoveredLibrary, setHoveredLibrary] = useState<string | null>(null);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const handleLibraryToggle = (id: string) => {
    setSelectedLibrariesIds(
      selectedLibrariesIds.includes(id)
        ? selectedLibrariesIds.filter((libId) => libId !== id)
        : [...selectedLibrariesIds, id],
    );
  };

  const filteredLibraries = libraries
    ?.filter((lib: Tag) => lib.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name));

  return (
    <Box sx={{ width: "380px", height: "406px", display: "flex", flexDirection: "column" }}>
      {/* Searchbar */}
      <Box sx={{ mx: 2, mt: 2, mb: 1 }}>
        <TextField
          autoFocus
          label="Search libraries"
          variant="outlined"
          size="small"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          fullWidth
        />
      </Box>

      {/* List of libraries */}
      <Stack
        sx={{
          overflowY: "auto",
          overflowX: "hidden",
          scrollbarWidth: "thin",
          px: 1,
        }}
      >
        {filteredLibraries?.map((lib: Tag) => (
          <Box
            sx={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              borderRadius: 2,
              transition: "background 0.2s",
              cursor: "pointer",
              "&:hover": {
                background: theme.palette.action.hover,
              },
              // Ensure minHeight for better click/hover area
              minHeight: 40,
            }}
            key={lib.id}
            onMouseEnter={(e) => {
              setHoveredLibrary(lib.id);
              setAnchorEl(e.currentTarget);
            }}
            onMouseLeave={() => {
              setHoveredLibrary(null);
              setAnchorEl(null);
            }}
            onClick={() => handleLibraryToggle(lib.id)}
          >
            <Checkbox
              checked={selectedLibrariesIds.includes(lib.id)}
              tabIndex={-1}
              disableRipple
              sx={{ mr: 1 }}
              onClick={(e) => e.stopPropagation()} // Prevent double toggle when clicking checkbox
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

            {/* Tooltip */}
            {hoveredLibrary === lib.id && anchorEl && (
              <Tooltip
                open
                title={
                  <>
                    <Typography color="inherit">{lib.name}</Typography>
                    {lib.description && (
                      <Typography color="inherit" fontWeight="light" fontSize=".95rem" fontStyle="italic">
                        {lib.description}
                      </Typography>
                    )}
                  </>
                }
                placement="right"
                disableInteractive
                slotProps={{
                  popper: {
                    modifiers: [
                      {
                        name: "eventListeners",
                        options: { scroll: false },
                      },
                    ],
                  },
                }}
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
