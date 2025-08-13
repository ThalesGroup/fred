// ResourceLibraryList.tsx
// Copyright Thales 2025

import * as React from "react";
import AddIcon from "@mui/icons-material/Add";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import UploadIcon from "@mui/icons-material/Upload";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import UnfoldLessIcon from "@mui/icons-material/UnfoldLess";
import { Box, Breadcrumbs, Button, Card, Chip, Link, Typography, IconButton, Tooltip } from "@mui/material";
import {
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  ResourceKind,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  Resource,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTree, TagNode, findNode } from "../tags/tagTree";
import { useTranslation } from "react-i18next";
import { useResourceCommands } from "./useResourceCommands";
import { ResourceLibraryTree } from "./ResourceLibraryTree";
import { LibraryCreateDrawer } from "../../common/LibraryCreateDrawer";
import { PromptEditorModal } from "./PromptEditorModal";
import { TemplateEditorModal } from "./TemplateEditorModal";
import { ResourcePreviewModal } from "./ResourcePreviewModal";
import { ResourceImportDrawer } from "./ResourceImportDrawer";

/** Small i18n helper */
const useKindLabels = (kind: "prompt" | "template") => {
  const { t } = useTranslation();
  return {
    one: t(`resource.kind.${kind}.one`),
    other: t(`resource.kind.${kind}.other`),
  };
};

type Props = { kind: ResourceKind };

export default function ResourceLibraryList({ kind }: Props) {
  const { t } = useTranslation();
  const { one: typeOne, other: typePlural } = useKindLabels(kind);

  /** ---------------- State ---------------- */
  const [expanded, setExpanded] = React.useState<string[]>([]);
  const [selectedFolder, setSelectedFolder] = React.useState<string | undefined>(undefined);
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = React.useState(false);
  const [openCreateResource, setOpenCreateResource] = React.useState(false);
  const [uploadTargetTagId, setUploadTargetTagId] = React.useState<string | null>(null);
  const [previewing, setPreviewing] = React.useState<Resource | null>(null);
  const [editing, setEditing] = React.useState<Resource | null>(null);

  /** ---------------- Data fetching ---------------- */
  // 1) Tags for this kind (prompt | template)
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
    {
      kind,
    },
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
      {/* Top toolbar */}
      <Box display="flex" alignItems="center" justifyContent="space-between">
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

        <Box display="flex" gap={1}>
          <Button
            variant="outlined"
            startIcon={<AddIcon />}
            onClick={() => setIsCreateDrawerOpen(true)}
            sx={{ borderRadius: "8px" }}
          >
            {t("resourceLibrary.createLibrary")}
          </Button>
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={handleOpenCreate}
            disabled={!selectedFolder}
            sx={{ borderRadius: "8px" }}
          >
            {t("resourceLibrary.createResource", { typeOne })}
          </Button>
          <Button variant="contained" startIcon={<UploadIcon />} disabled={!selectedFolder} onClick={openImportDrawer}>
            {t("resourceLibrary.importResource", { typeOne })}
          </Button>
        </Box>
      </Box>

      {/* Loading & error */}
      {isLoading && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography variant="body2">{t("promptLibrary.loadingLibraries")}</Typography>
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
              resources={allResources}
              onRemoveFromLibrary={removeFromLibrary}
              onPreview={handlePreview} // ← pass down
              onEdit={handleEdit} // ← pass down
            />
          </Box>
        </Card>
      )}

      {/* Create modals */}
      {kind === "template" ? (
        <TemplateEditorModal
          isOpen={openCreateResource}
          onClose={() => setOpenCreateResource(false)}
          onSave={(payload) => {
            if (!uploadTargetTagId) return;
            createResource(payload, uploadTargetTagId);
            setOpenCreateResource(false);
          }}
        />
      ) : (
        <PromptEditorModal
          isOpen={openCreateResource}
          onClose={() => setOpenCreateResource(false)}
          onSave={(payload) => {
            if (!uploadTargetTagId) return;
            createResource(payload, uploadTargetTagId);
            setOpenCreateResource(false);
          }}
        />
      )}

      {/* Preview modal */}
      <ResourcePreviewModal open={!!previewing} resource={previewing} onClose={() => setPreviewing(null)} />

      {/* Edit modals (use same UIs; they pass-through YAML if present) */}
      {editing &&
        (kind === "template" ? (
          <TemplateEditorModal
            isOpen={!!editing}
            onClose={() => setEditing(null)}
            initial={{
              name: editing.name ?? "",
              description: editing.description ?? "",
              // Pass YAML to body; modal will detect YAML and keep it intact
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
            }}
          />
        ) : (
          <PromptEditorModal
            isOpen={!!editing}
            onClose={() => setEditing(null)}
            initial={
              {
                name: editing.name ?? "",
                description: editing.description ?? "",
                yaml: editing.content, // the prompt modal accepts yaml/body similarly
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
            }}
          />
        ))}

      <ResourceImportDrawer
        kind={kind}
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onImportComplete={() => {
          // refresh lists after import
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
