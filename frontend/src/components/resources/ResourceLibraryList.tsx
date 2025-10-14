// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import AddIcon from "@mui/icons-material/Add";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import UnfoldLessIcon from "@mui/icons-material/UnfoldLess";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import UploadIcon from "@mui/icons-material/Upload";
import { Box, Breadcrumbs, Button, Card, Chip, IconButton, Link, TextField, Tooltip, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { LibraryCreateDrawer } from "../../common/LibraryCreateDrawer";
import { useTagCommands } from "../../common/useTagCommands";
import { usePermissions } from "../../security/usePermissions";
import {
  Resource,
  ResourceKind,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";
import { buildTree, findNode, TagNode } from "../tags/tagTree";
import { ChatContextEditorModal } from "./ChatContextEditorModal";
import { PromptEditorModal } from "./PromptEditorModal";
import { ResourceImportDrawer } from "./ResourceImportDrawer";
import { ResourceLibraryTree } from "./ResourceLibraryTree";
import { ResourcePreviewModal } from "./ResourcePreviewModal";
import { TemplateEditorModal } from "./TemplateEditorModal";
import { useResourceCommands } from "./useResourceCommands";

/** Small i18n helper */
export const useKindLabels = (kind: "prompt" | "template" | "chat-context") => {
  const { t } = useTranslation();
  return {
    one: t(`resource.kind.${kind}.one`),
    other: t(`resource.kind.${kind}.other`),
  };
};

/** Helpers mirroring documents */
const getResourceTagIds = (r: Resource): string[] => {
  // Accept several shapes, stay defensive
  // - r.tag_ids: string[]
  // - r.tags: Array<{ id: string } | string>
  // - r.labels: Record<string, string>  (ignored here)
  const fromTagIds = (r as any).tag_ids;
  if (Array.isArray(fromTagIds)) return fromTagIds as string[];
  const fromTags = (r as any).tags;
  if (Array.isArray(fromTags)) {
    return fromTags.map((t: any) => (typeof t === "string" ? t : t?.id)).filter(Boolean);
  }
  return [];
};

const matchesResourceByName = (r: Resource, q: string) => {
  const name = r.name ?? "";
  const desc = r.description ?? "";
  const query = q.toLowerCase();
  return name.toLowerCase().includes(query) || desc.toLowerCase().includes(query);
};

const resHasAnyTag = (r: Resource, tagIds: string[]) => {
  const ids = getResourceTagIds(r);
  return ids.some((id) => tagIds.includes(id));
};

type Props = { kind: ResourceKind };

export default function ResourceLibraryList({ kind }: Props) {
  const { t } = useTranslation();
  const { one: typeOne, other: typePlural } = useKindLabels(kind);
  const { showConfirmationDialog } = useConfirmationDialog();

  /** ---------------- State ---------------- */
  const [expanded, setExpanded] = React.useState<string[]>([]);
  const [selectedFolder, setSelectedFolder] = React.useState<string | null>(null);
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = React.useState(false);
  const [openCreateResource, setOpenCreateResource] = React.useState(false);
  const [uploadTargetTagId, setUploadTargetTagId] = React.useState<string | null>(null);
  const [previewing, setPreviewing] = React.useState<Resource | null>(null);
  const [editing, setEditing] = React.useState<Resource | null>(null);

  // NEW: search + multi-select (mirrors Documents)
  const [query, setQuery] = React.useState<string>("");
  // map: resourceId -> TagWithItemsId (the library tag in which it was selected)
  const [selectedItems, setSelectedItems] = React.useState<Record<string, TagWithItemsId>>({});
  const selectedCount = React.useMemo(() => Object.keys(selectedItems).length, [selectedItems]);
  const clearSelection = React.useCallback(() => setSelectedItems({}), []);

  // RBAC utils
  const { can } = usePermissions();
  const canCreateTag = can("tag", "create");
  const canCreateResource = can("resource", "create");

  /** ---------------- Data fetching ---------------- */
  // 1) Tags for this kind (prompt | template | porfile)
  const {
    data: allTags,
    isLoading,
    isError,
    refetch: refetchTags,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: kind, limit: 10000, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );

  // 2) All resources of this kind
  const { data: allResources = [], refetch: refetchResources } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery(
    { kind },
  );

  // 3) Build tree
  const tree = React.useMemo<TagNode | null>(() => (allTags ? buildTree(allTags) : null), [allTags]);

  /** ---------------- Commands (create/update/remove) ---------------- */
  const { createResource, updateResource, removeFromLibrary /*, getResource*/ } = useResourceCommands(kind, {
    refetchTags,
    refetchResources,
  });

  /** ---------------- Derived helpers ---------------- */
  const getChildren = React.useCallback(
    (n: TagNode) => {
      const arr = Array.from(n.children.values());
      arr.sort((a, b) => a.name.localeCompare(b.name));
      return arr;
    },
    [kind],
  );

  const setAllExpanded = (expand: boolean) => {
    if (!tree) return;
    const ids: string[] = [];
    const walk = (n: TagNode) => {
      for (const c of getChildren(n)) {
        ids.push(c.full);
        if (c.children.size) walk(c);
      }
    };
    walk(tree);
    setExpanded(expand ? ids : []);
  };
  const allExpanded = React.useMemo(() => expanded.length > 0, [expanded]);

  const [isImportOpen, setIsImportOpen] = React.useState(false);

  const openImportDrawer = () => {
    if (!selectedFolder) return;
    const node = findNode(tree, selectedFolder);
    const firstTagId = node?.tagsHere?.[0]?.id;
    if (!firstTagId) return;
    setUploadTargetTagId(firstTagId);
    setIsImportOpen(true);
  };

  /** ---------------- NEW: search & auto-expand on matches ---------------- */
  const filteredResources = React.useMemo<Resource[]>(() => {
    const q = query.trim();
    if (!q) return allResources;
    return allResources.filter((r) => matchesResourceByName(r, q));
  }, [allResources, query]);

  React.useEffect(() => {
    if (!tree) return;
    const q = query.trim();
    if (!q) return;

    const nextExpanded = new Set<string>();

    const nodeHasMatch = (n: TagNode): boolean => {
      const hereTagIds = (n.tagsHere ?? []).map((t) => t.id);
      const hereMatch = filteredResources.some((r) => resHasAnyTag(r, hereTagIds));
      const childMatch = Array.from(n.children.values()).map(nodeHasMatch).some(Boolean);
      const has = hereMatch || childMatch;
      if (has && n.full !== tree.full) nextExpanded.add(n.full);
      return has;
    };

    nodeHasMatch(tree);
    setExpanded(Array.from(nextExpanded));
  }, [tree, query, filteredResources]);

  /** ---------------- NEW: delete support (single + bulk) ---------------- */
  const removeOneWithConfirm = React.useCallback(
    (res: Resource, tag: TagWithItemsId) => {
      const name = res.name || String(res.id);
      showConfirmationDialog({
        title: t("resourceLibrary.confirmRemoveTitle"),
        message: t("resourceLibrary.confirmRemoveMessage", { res: name, folder: tag.name }),
        onConfirm: () => {
          void removeFromLibrary(res, tag);
        },
      });
    },
    [showConfirmationDialog, removeFromLibrary, t],
  );

  const bulkRemoveFromLibrary = React.useCallback(() => {
    const entries = Object.entries(selectedItems);
    if (entries.length === 0) return;

    showConfirmationDialog({
      title: t("resourceLibrary.confirmBulkRemoveTitle") || "Remove selected?",
      onConfirm: async () => {
        const byId = new Map<string | number, Resource>(allResources.map((r) => [r.id, r]));
        for (const [resId, tag] of entries) {
          const res = byId.get(resId) || byId.get(Number(resId));
          if (!res) continue;
          // eslint-disable-next-line no-await-in-loop
          await removeFromLibrary(res, tag);
        }
        setSelectedItems({});
      },
    });
  }, [selectedItems, allResources, removeFromLibrary, showConfirmationDialog, t]);

  const { confirmDeleteFolder } = useTagCommands({
    refetchTags,
    refetchDocs: refetchResources, // reuse for resources
  });
  const handleDeleteFolder = React.useCallback(
    (tag: TagWithItemsId) => {
      // Pass the state reset function as the onSuccess callback
      confirmDeleteFolder(tag, () => {
        // This runs only after the user confirms AND the deletion is successful
        setSelectedFolder(null);
      });
    },
    [confirmDeleteFolder, setSelectedFolder],
  );
  /** ---------------- Handlers ---------------- */
  const handleOpenCreate = React.useCallback(() => {
    if (!selectedFolder) return;
    const node = findNode(tree, selectedFolder);
    const firstTagId = node?.tagsHere?.[0]?.id;
    if (!firstTagId) return;
    setUploadTargetTagId(firstTagId);
    setOpenCreateResource(true);
  }, [selectedFolder, tree]);

  const handlePreview = React.useCallback((r: Resource) => {
    setPreviewing(r);
    // If you want fresh data: await getResource(r.id).then(setPreviewing)
  }, []);

  const handleEdit = React.useCallback((r: Resource) => {
    setEditing(r);
  }, []);

  React.useEffect(() => {
    // close create modal if user switches kind tab
    setOpenCreateResource(false);
  }, [kind]);

  /** ---------------- Render ---------------- */
  return (
    <Box display="flex" flexDirection="column" gap={2}>
      {/* Top toolbar (mirrors Documents — now includes search) */}
      <Box display="flex" alignItems="center" justifyContent="space-between" gap={2} flexWrap="wrap">
        <Breadcrumbs>
          <Chip
            label={t("resourceLibrary.title", { typePlural })}
            icon={<FolderOutlinedIcon />}
            onClick={() => setSelectedFolder(undefined)}
            clickable
            sx={{ fontWeight: 500 }}
          />
          {selectedFolder?.split("/").map((c, i, arr) => (
            <Link key={i} component="button" onClick={() => setSelectedFolder(arr.slice(0, i + 1).join("/"))}>
              {c}
            </Link>
          ))}
        </Breadcrumbs>

        {/* Search */}
        <TextField
          size="small"
          placeholder={t("resourceLibrary.searchPlaceholder", { typeOne }) || "Search resources…"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          sx={{ minWidth: 260 }}
        />

        <Box display="flex" gap={1}>
          <Button
            variant="outlined"
            startIcon={<AddIcon />}
            onClick={canCreateTag ? () => setIsCreateDrawerOpen(true) : undefined}
            disabled={!canCreateTag}
            sx={{ borderRadius: "8px" }}
          >
            {t("resourceLibrary.createLibrary")}
          </Button>
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={canCreateResource && selectedFolder ? handleOpenCreate : undefined}
            disabled={!canCreateResource || !selectedFolder}
            sx={{ borderRadius: "8px" }}
          >
            {t("resourceLibrary.createResource", { typeOne })}
          </Button>
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={canCreateResource && selectedFolder ? openImportDrawer : undefined}
            disabled={!canCreateResource || !selectedFolder}
          >
            {t("resourceLibrary.importResource", { typeOne })}
          </Button>
        </Box>
      </Box>

      {/* NEW: Bulk actions bar (mirrors Documents) */}
      {selectedCount > 0 && (
        <Card sx={{ p: 1, borderRadius: 2, display: "flex", alignItems: "center", gap: 2 }}>
          <Typography variant="body2">
            {selectedCount} {t("resourceLibrary.selected") || "selected"}
          </Typography>
          <Button size="small" variant="outlined" onClick={clearSelection}>
            {t("resourceLibrary.clearSelection") || "Clear selection"}
          </Button>
          <Button size="small" variant="contained" color="error" onClick={bulkRemoveFromLibrary}>
            {t("resourceLibrary.bulkRemoveFromLibrary") || "Remove from library"}
          </Button>
        </Card>
      )}

      {/* Loading & error */}
      {isLoading && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography variant="body2">{t("resourceLibrary.loadingLibraries")}</Typography>
        </Card>
      )}
      {isError && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography color="error">{t("resourceLibrary.failedToLoad")}</Typography>
          <Button onClick={() => refetchTags()} sx={{ mt: 1 }} size="small" variant="outlined">
            {t("dialogs.retry")}
          </Button>
        </Card>
      )}

      {/* Tree */}
      {!isLoading && !isError && tree && (
        <Card sx={{ borderRadius: 3 }}>
          {/* Tree header */}
          <Box display="flex" alignItems="center" justifyContent="space-between" px={1} py={0.5}>
            <Typography variant="subtitle2" color="text.secondary">
              {t("resourceLibrary.folders")}
            </Typography>
            <Tooltip title={allExpanded ? t("resourceLibrary.collapseAll") : t("resourceLibrary.expandAll")}>
              <IconButton size="small" onClick={() => setAllExpanded(!allExpanded)} disabled={!tree}>
                {allExpanded ? <UnfoldLessIcon fontSize="small" /> : <UnfoldMoreIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          </Box>

          {/* Recursive rendering */}
          <Box px={1} pb={1}>
            <ResourceLibraryTree
              tree={tree}
              expanded={expanded}
              setExpanded={setExpanded}
              selectedFolder={selectedFolder}
              setSelectedFolder={setSelectedFolder}
              getChildren={getChildren}
              resources={filteredResources}
              onRemoveFromLibrary={removeOneWithConfirm} // NEW: confirm wrapper
              onPreview={handlePreview}
              onEdit={handleEdit}
              // NEW: selection + folder deletion
              selectedItems={selectedItems}
              setSelectedItems={setSelectedItems}
              onDeleteFolder={handleDeleteFolder}
            />
          </Box>
        </Card>
      )}

      {/* Create modals */}
      {kind === "template" && (
        <TemplateEditorModal
          isOpen={openCreateResource}
          onClose={() => setOpenCreateResource(false)}
          onSave={async (payload) => {
            if (!uploadTargetTagId) return;
            await createResource(payload, uploadTargetTagId);
            setOpenCreateResource(false);
            await Promise.all([refetchTags(), refetchResources()]);
          }}
        />
      )}
      {kind === "prompt" && (
        <PromptEditorModal
          isOpen={openCreateResource}
          onClose={() => setOpenCreateResource(false)}
          onSave={async (payload) => {
            if (!uploadTargetTagId) return;
            await createResource(payload, uploadTargetTagId);
            setOpenCreateResource(false);
            await Promise.all([refetchTags(), refetchResources()]);
          }}
        />
      )}
      {kind === "chat-context" && (
        <ChatContextEditorModal
          isOpen={openCreateResource}
          onClose={() => setOpenCreateResource(false)}
          onSave={async (payload) => {
            if (!uploadTargetTagId) return;
            await createResource(payload, uploadTargetTagId);
            setOpenCreateResource(false);
            await Promise.all([refetchTags(), refetchResources()]);
          }}
        />
      )}

      {/* Preview modal */}
      <ResourcePreviewModal open={!!previewing} resource={previewing} onClose={() => setPreviewing(null)} />
      {/* Edit modals (pass-through YAML if present) */}
      {editing &&
        (kind === "template" ? (
          <TemplateEditorModal
            isOpen={!!editing}
            onClose={() => setEditing(null)}
            initial={{
              name: editing.name ?? "",
              description: editing.description ?? "",
              body: editing.content,
            }}
            onSave={async (payload) => {
              await updateResource(editing.id, {
                content: payload.content,
                name: payload.name,
                description: payload.description,
                labels: payload.labels,
              });
              setEditing(null);
              await Promise.all([refetchTags(), refetchResources()]);
            }}
          />
        ) : kind === "prompt" ? (
          <PromptEditorModal
            isOpen={!!editing}
            onClose={() => setEditing(null)}
            initial={
              {
                name: editing.name ?? "",
                description: editing.description ?? "",
                yaml: editing.content,
              } as any
            }
            onSave={async (payload) => {
              await updateResource(editing.id, {
                content: payload.content,
                name: payload.name,
                description: payload.description,
                labels: payload.labels,
              });
              setEditing(null);
              await Promise.all([refetchTags(), refetchResources()]);
            }}
          />
        ) : kind === "chat-context" ? (
          <ChatContextEditorModal
            isOpen={!!editing}
            onClose={() => setEditing(null)}
            initial={{
              name: editing.name ?? "",
              description: editing.description ?? "",
              yaml: editing.content, // on laisse passer le YAML existant si présent
              labels: (editing as any)?.labels ?? [],
            }}
            onSave={async (payload) => {
              await updateResource(editing.id, {
                content: payload.content,
                name: payload.name,
                description: payload.description,
                labels: payload.labels,
              });
              setEditing(null);
              await Promise.all([refetchTags(), refetchResources()]);
            }}
          />
        ) : null)}

      {/* Import drawer */}
      <ResourceImportDrawer
        kind={kind}
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onImportComplete={() => {
          refetchTags();
          refetchResources();
        }}
        libraryTagId={uploadTargetTagId}
      />

      {/* Create-library drawer */}
      <LibraryCreateDrawer
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
        onLibraryCreated={async () => {
          await refetchTags();
        }}
        mode={kind}
        currentPath={selectedFolder}
      />
    </Box>
  );
}
