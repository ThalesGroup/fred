// Copyright Thales 2025
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
  Breadcrumbs,
  Link,
  Typography,
} from "@mui/material";
import dayjs from "dayjs";
import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  TagWithItemsId,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { EmptyState } from "../EmptyState";
import InvisibleLink from "../InvisibleLink";
import { TableSkeleton } from "../TableSkeleton";
import { LibraryCreateDrawer } from "./LibraryCreateDrawer";
import { collectDescendantTags, countDocsUnique } from "../tags/TagsUtils";

// --- small helper to build a tree ---
type TagNode = {
  name: string; // segment name
  full: string; // full path up to this node
  children: Map<string, TagNode>;
  tags: TagWithItemsId[]; // tags that end at this node
};

const getFullPath = (t: Pick<TagWithItemsId, "name" | "path">) =>
  t.path && t.path.trim() ? `${t.path}/${t.name}` : t.name;

const buildTagTree = (tags: TagWithItemsId[]) => {
  const root: TagNode = { name: "", full: "", children: new Map(), tags: [] };
  for (const t of tags) {
    const full = getFullPath(t);
    const parts = full.split("/").filter(Boolean);
    let cur = root;
    for (let i = 0; i < parts.length; i++) {
      const seg = parts[i];
      if (!cur.children.has(seg)) {
        const nextFull = i === 0 ? seg : `${cur.full}/${seg}`;
        cur.children.set(seg, { name: seg, full: nextFull, children: new Map(), tags: [] });
      }
      cur = cur.children.get(seg)!;
    }
    cur.tags.push(t);
  }
  return root;
};

export function AllDocumentLibrariesList() {
  const { t } = useTranslation();

  // NEW: current folder (breadcrumb)
  const [pathPrefix, setPathPrefix] = useState<string | undefined>(undefined);

  // Fetch ALL document tags (we’ll build a client-side tree)
  const {
    data: allLibraries,
    refetch: refetchLibraries,
    isLoading,
    isError,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", limit: 50, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );

  const [deleteTag] = useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation();

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [menuLibraryId, setMenuLibraryId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<string>("lastUpdate");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = useState(false);
  const [showHereDocs, setShowHereDocs] = useState(false);
  const [fetchHereDocs, { data: hereDocs, isLoading: docsLoading, error: docsError }] =
    useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation();

  // Build tree + locate node for current prefix
  const {
    node,
    childFolders,
    visibleLibraries,
    subfolderCounts, // NEW: map of child folder -> unique doc count
    hereCount, // NEW: total unique docs under current folder
    hereTagIds, // NEW: all descendant tag IDs under current folder
  } = useMemo(() => {
    if (!allLibraries) {
      return {
        node: null as TagNode | null,
        childFolders: [] as TagNode[],
        visibleLibraries: [] as TagWithItemsId[],
        subfolderCounts: new Map<string, number>(),
        hereCount: 0,
        hereTagIds: [] as string[],
      };
    }
    const tree = buildTagTree(allLibraries);
    const crumbs = (pathPrefix || "").split("/").filter(Boolean);
    let cur: TagNode = tree;
    for (const seg of crumbs) {
      const next = cur.children.get(seg);
      if (!next) break;
      cur = next;
    }
    const children = Array.from(cur.children.values()).sort((a, b) => a.name.localeCompare(b.name));

    // counts per child folder (unique docs)
    const subCounts = new Map<string, number>();
    for (const child of children) {
      const desc = collectDescendantTags(child);
      const { total } = countDocsUnique(desc);
      subCounts.set(child.full, total);
    }

    // aggregate for "here" (current folder)
    const hereDesc = collectDescendantTags(cur);
    const { total: hereTotal, ids } = countDocsUnique(hereDesc);

    return {
      node: cur,
      childFolders: children,
      visibleLibraries: cur.tags,
      subfolderCounts: subCounts,
      hereCount: hereTotal,
      hereTagIds: Array.from(new Set(hereDesc.map((t) => t.id))),
    };
  }, [allLibraries, pathPrefix]);

  const loadHereDocs = React.useCallback(() => {
    if (!hereTagIds.length) return;
    fetchHereDocs({
      filters: {
        tag_ids: hereTagIds, // <-- backend: return docs that have ANY of these tag IDs
        // optional: add more filters if your backend supports them, e.g. time range, author, etc.
        // created_gte: "...", created_lte: "..."
      },
    });
  }, [fetchHereDocs, hereTagIds]);
  const allSelected = visibleLibraries && selectedIds.length === visibleLibraries.length && visibleLibraries.length > 0;

  const handleSortChange = (column: string) => {
    if (sortBy === column) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDirection("asc");
    }
  };

  const sortedLibraries = useMemo(() => {
    const libs = [...(visibleLibraries || [])];
    return libs.sort((a, b) => {
      let aVal: any, bVal: any;
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
      if (sortDirection === "asc") return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
    });
  }, [visibleLibraries, sortBy, sortDirection]);

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]));
  };

  const handleToggleAll = (checked: boolean) => {
    if (checked && visibleLibraries) {
      setSelectedIds(visibleLibraries.map((lib) => lib.id));
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

  // Breadcrumb bits
  const crumbs = (pathPrefix || "").split("/").filter(Boolean);
  const goToCrumb = (idx: number) => {
    if (idx < 0) return setPathPrefix(undefined);
    const next = crumbs.slice(0, idx + 1).join("/");
    setPathPrefix(next || undefined);
    setSelectedIds([]); // reset selection on navigation
  };

  return (
    <>
      {/* Breadcrumb + New library button */}
      <Box sx={{ mb: 2, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Breadcrumbs>
          <Link component="button" onClick={() => goToCrumb(-1)}>
            All
          </Link>
          {crumbs.map((c, i) => (
            <Link key={i} component="button" onClick={() => goToCrumb(i)}>
              {c}
            </Link>
          ))}
        </Breadcrumbs>

        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setIsCreateDrawerOpen(true)}
          sx={{ borderRadius: "8px" }}
        >
          {t("documentLibrariesList.createLibrary")}
        </Button>
      </Box>

      {/* Child folders row */}
      <Box sx={{ mb: 2, display: "flex", flexWrap: "wrap", gap: 1, alignItems: "center" }}>
        {childFolders.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t("documentLibrariesList.noSubfolders")}
          </Typography>
        ) : (
          childFolders.map((f) => (
            <Button
              key={f.full}
              variant="outlined"
              size="small"
              startIcon={<FolderIcon fontSize="small" />}
              onClick={() => setPathPrefix(f.full)}
              sx={{ borderRadius: "16px" }}
            >
              {f.name} &nbsp;
              <Typography component="span" variant="caption" color="text.secondary">
                ({subfolderCounts.get(f.full) ?? 0})
              </Typography>
            </Button>
          ))
        )}

        {/* Right-aligned "Show documents here" */}
        <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="body2" color="text.secondary">
            TOTO {hereCount} {hereCount === 1 ? "document" : "documents"}
          </Typography>
          <Button
            variant={showHereDocs ? "outlined" : "contained"}
            size="small"
            onClick={() => {
              const next = !showHereDocs;
              setShowHereDocs(next);
              if (next) loadHereDocs();
            }}
            disabled={!hereTagIds.length}
            sx={{ borderRadius: "16px" }}
          >
            {showHereDocs ? t("common.hide") || "Hide" : t("common.show") || "Show"}{" "}
            {t("common.documents") || "documents"}
          </Button>
        </Box>
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
        ) : isError ? (
          <EmptyState
            icon={<FolderOpenIcon />}
            title={t("common.error") || "Error"}
            description={t("documentLibrariesList.loadError") || "Failed to load libraries."}
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
                      {t("documentLibrariesList.libraryName")}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>
                    <TableSortLabel
                      active={sortBy === "documents"}
                      direction={sortBy === "documents" ? sortDirection : "asc"}
                      onClick={() => handleSortChange("documents")}
                    >
                      {t("documentLibrariesList.documents")}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>
                    <TableSortLabel
                      active={sortBy === "lastUpdate"}
                      direction={sortBy === "lastUpdate" ? sortDirection : "desc"}
                      onClick={() => handleSortChange("lastUpdate")}
                    >
                      {t("documentLibrariesList.lastUpdate")}
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }} align="right">
                    {t("documentLibrariesList.actions")}
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedLibraries.map((library) => (
                  <DocumentLibraryRow
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
                <ListItemText>{t("documentLibrariesList.delete")}</ListItemText>
              </MenuItem>
            </Menu>
          </TableContainer>
        ) : (
          <EmptyState
            icon={<FolderOpenIcon />}
            title={t("documentLibrariesList.noLibrariesFound")}
            description={t("documentLibrariesList.noLibrariesFoundDescription")}
            actionButton={{
              label: t("documentLibrariesList.createLibrary"),
              onClick: () => setIsCreateDrawerOpen(true),
              startIcon: <AddIcon />,
            }}
          />
        )}
      </Card>
      {showHereDocs && (
        <Card sx={{ borderRadius: 4, p: 2, mt: 2 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>
            {pathPrefix ? `Documents under: ${pathPrefix}` : "All documents"}
          </Typography>

          {docsLoading ? (
            <Typography>Loading…</Typography>
          ) : docsError ? (
            <Typography color="error">Failed to load documents.</Typography>
          ) : hereDocs?.documents?.length ? (
            // TODO: replace with your real list component
            <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(hereDocs.documents, null, 2)}</pre>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No documents here.
            </Typography>
          )}
        </Card>
      )}

      {/* Option C: create under current folder */}
      <LibraryCreateDrawer
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
        onLibraryCreated={async () => {
          await refetchLibraries();
        }}
        mode="documents"
        currentPath={pathPrefix} // <- key line
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
    return dayjs(date).format("L");
  }
}

function DocumentLibraryRow({
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

  // Show full breadcrumb if path exists
  const displayName = library.path ? `${library.path}/${library.name}` : library.name;

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
              style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "inherit" }}
            >
              <FolderIcon fontSize="small" />
              {displayName}
            </InvisibleLink>
          </span>
        </Tooltip>
      </TableCell>
      <TableCell>
        {documentCount < 2
          ? t("documentLibrariesList.documentCountSingular", { count: documentCount })
          : t("documentLibrariesList.documentCountPlural", { count: documentCount })}
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
