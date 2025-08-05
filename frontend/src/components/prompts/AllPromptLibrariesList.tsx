import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import FolderIcon from "@mui/icons-material/Folder";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import {
  Box,
  Button,
  Card,
  Checkbox,
  IconButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Tooltip,
} from "@mui/material";
import dayjs from "dayjs";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  TagWithItemsId,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { EmptyState } from "../EmptyState";
import InvisibleLink from "../InvisibleLink";
import { TableSkeleton } from "../TableSkeleton";
import { LibraryCreateDrawer } from "../documents/LibraryCreateDrawer";

export function AllPromptLibrariesList() {
  const { t } = useTranslation();
  const {
    data: libraries,
    refetch: refetchLibraries,
    isLoading,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "prompt" },
    {
      refetchOnMountOrArgChange: true,
    },
  );
  const [deleteTag] = useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation();

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [menuLibraryId, setMenuLibraryId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<string>("lastUpdate");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = useState(false);

  const allSelected = libraries && selectedIds.length === libraries.length && libraries.length > 0;

  const handleSortChange = (column: string) => {
    if (sortBy === column) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDirection("asc");
    }
  };

  const sortedLibraries = React.useMemo(() => {
    if (!libraries) return [];
    const libs = [...libraries];
    return libs.sort((a, b) => {
      let aVal, bVal;
      switch (sortBy) {
        case "name":
          aVal = a.name.toLowerCase();
          bVal = b.name.toLowerCase();
          break;
        case "documents":
          aVal = a.item_ids ? a.item_ids.length : 0;
          bVal = b.item_ids ? b.item_ids.length : 0;
          break;
        case "lastUpdate":
        default:
          aVal = new Date(a.updated_at).getTime();
          bVal = new Date(b.updated_at).getTime();
          break;
      }
      if (sortDirection === "asc") {
        return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      } else {
        return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
      }
    });
  }, [libraries, sortBy, sortDirection]);

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]));
  };

  const handleToggleAll = (checked: boolean) => {
    if (checked && libraries) {
      setSelectedIds(libraries.map((lib) => lib.id));
    } else {
      setSelectedIds([]);
    }
  };

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, id: string) => {
    setMenuAnchor(event.currentTarget);
    setMenuLibraryId(id);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
    setMenuLibraryId(null);
  };

  const handleDelete = async (id: string) => {
    handleMenuClose();
    await deleteTag({ tagId: id });
    await refetchLibraries();
  };

  return (
    <>
      <Box sx={{ mb: 2, display: "flex", justifyContent: "flex-end" }}>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setIsCreateDrawerOpen(true)}
          sx={{ borderRadius: "8px" }}
        >
          {t("promptLibrariesList.createLibrary")}
        </Button>
      </Box>

      <Card sx={{ borderRadius: 4, p: 2 }}>
        {isLoading ? (
          <TableSkeleton
            columns={[
              { padding: "checkbox" },
              { width: 200, hasIcon: true },
              { width: 100 },
              { width: 120 },
              { width: 100 },
            ]}
          />
        ) : sortedLibraries && sortedLibraries.length > 0 ? (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox checked={allSelected} onChange={(e) => handleToggleAll(e.target.checked)} />
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>
                    <TableSortLabel
                      active={sortBy === "name"}
                      direction={sortBy === "name" ? sortDirection : "asc"}
                      onClick={() => handleSortChange("name")}
                    >
                      {t("promptLibrariesList.libraryName")}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>
                    <TableSortLabel
                      active={sortBy === "documents"}
                      direction={sortBy === "documents" ? sortDirection : "asc"}
                      onClick={() => handleSortChange("documents")}
                    >
                      {t("promptLibrariesList.prompts")}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>
                    <TableSortLabel
                      active={sortBy === "lastUpdate"}
                      direction={sortBy === "lastUpdate" ? sortDirection : "desc"}
                      onClick={() => handleSortChange("lastUpdate")}
                    >
                      {t("promptLibrariesList.lastUpdate")}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }} align="right">
                    {t("promptLibrariesList.actions")}
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedLibraries.map((library) => (
                  <PromptLibraryRow
                    key={library.id}
                    library={library}
                    selected={selectedIds.includes(library.id)}
                    onToggleSelect={() => handleToggleSelect(library.id)}
                    onMenuOpen={handleMenuOpen}
                  />
                ))}
              </TableBody>
            </Table>
            <Menu
              anchorEl={menuAnchor}
              open={Boolean(menuAnchor)}
              onClose={handleMenuClose}
              anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
              transformOrigin={{ vertical: "top", horizontal: "right" }}
            >
              <MenuItem onClick={() => menuLibraryId && handleDelete(menuLibraryId)}>
                <ListItemIcon>
                  <DeleteIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText>{t("promptLibrariesList.delete")}</ListItemText>
              </MenuItem>
            </Menu>
          </TableContainer>
        ) : (
          <EmptyState
            icon={<FolderOpenIcon />}
            title={t("promptLibrariesList.noLibrariesFound")}
            description={t("promptLibrariesList.noLibrariesFoundDescription")}
            actionButton={{
              label: t("promptLibrariesList.createLibrary"),
              onClick: () => setIsCreateDrawerOpen(true),
              startIcon: <AddIcon />,
            }}
          />
        )}
      </Card>

      <LibraryCreateDrawer
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
        onLibraryCreated={refetchLibraries}
        mode="prompts"
      />
    </>
  );
}

function formatLastUpdate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 1) {
    return "Today";
  } else if (diffDays === 1) {
    return "1 day ago";
  } else if (diffDays < 30) {
    return `${diffDays} days ago`;
  } else {
    // Use local date display (e.g. 23/02/25)
    return dayjs(date).format("L");
  }
}

function PromptLibraryRow({
  library,
  selected,
  onToggleSelect,
  onMenuOpen,
}: {
  library: TagWithItemsId;
  selected: boolean;
  onToggleSelect: () => void;
  onMenuOpen: (event: React.MouseEvent<HTMLElement>, id: string) => void;
}) {
  const { t } = useTranslation();
  const documentCount = library.item_ids ? library.item_ids.length : 0;
  const lastUpdateLabel = formatLastUpdate(library.updated_at);
  const lastUpdateTooltip = new Date(library.updated_at).toLocaleString();

  return (
    <TableRow hover>
      <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={selected} onChange={onToggleSelect} />
      </TableCell>
      <TableCell sx={{ fontWeight: 500 }}>
        <Tooltip title={library.description || ""}>
          <span>
            <InvisibleLink
              to={library.type === "prompt" ? `/promptLibrary/${library.id}` : `/documentLibrary/${library.id}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                color: "inherit",
              }}
            >
              <FolderIcon fontSize="small" />
              {library.name}
            </InvisibleLink>
          </span>
        </Tooltip>
      </TableCell>
      <TableCell>
        {documentCount < 2
          ? t("promptLibrariesList.documentCountSingular", { count: documentCount })
          : t("promptLibrariesList.documentCountPlural", { count: documentCount })}
      </TableCell>
      <TableCell>
        <Tooltip title={lastUpdateTooltip} arrow>
          <span>{lastUpdateLabel}</span>
        </Tooltip>
      </TableCell>
      <TableCell align="right" onClick={(e) => e.stopPropagation()}>
        <IconButton size="small" onClick={(e) => onMenuOpen(e, library.id)}>
          <MoreVertIcon />
        </IconButton>
      </TableCell>
    </TableRow>
  );
}
