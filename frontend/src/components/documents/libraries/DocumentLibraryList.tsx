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

/**
 *
 * This component renders the "Document Libraries" view for the knowledge flow app.
 * It displays a hierarchical folder structure (libraries) in a collapsible TreeView
 * using MUI X SimpleTreeView (MIT community edition). It supports:
 *
 *  - Breadcrumb navigation for the currently selected folder.
 *  - Creating new libraries at the top-level or inside the selected folder.
 *  - Expanding/collapsing all folders at once.
 *  - Persistent highlighting of the selected folder.
 *
 * The actual recursive folder rendering logic is delegated to DocumentLibraryTree.tsx
 * to keep this file focused on data fetching, state management, and layout.
 *
 * Data:
 *  - Uses useListAllTagsKnowledgeFlowV1TagsGetQuery() to fetch all tags of type "document".
 *  - Tags are built into a tree structure using buildTree() from ../tags/utils.
 *
 * State:
 *  - expanded: array of folder full paths currently expanded in the TreeView.
 *  - selectedFolder: the folder currently selected in the UI (affects create target).
 *  - isCreateDrawerOpen: controls visibility of LibraryCreateDrawer for creating new libraries.
 *
 */

import * as React from "react";
import AddIcon from "@mui/icons-material/Add";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import UploadIcon from "@mui/icons-material/Upload";
import { IconButton, Tooltip } from "@mui/material";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import UnfoldLessIcon from "@mui/icons-material/UnfoldLess";
import { LibraryCreateDrawer } from "../../../common/LibraryCreateDrawer";
import { Box, Breadcrumbs, Button, Card, Chip, Link, Typography } from "@mui/material";
import {
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTree, TagNode, findNode } from "../../tags/tagTree";
import { useTranslation } from "react-i18next";
import { DocumentLibraryTree } from "./DocumentLibraryTree";
import { DocumentUploadDrawer } from "./DocumentUploadDrawer";
import { useDocumentCommands } from "../common/useDocumentCommands";
import { useCascadeDeleteLibrary } from "../../../common/libraryCommand";

export default function DocumentLibraryList() {
  /** get our internalization library for english or french */
  const { t } = useTranslation();
  /** Expanded folder paths in the TreeView */
  const [expanded, setExpanded] = React.useState<string[]>([]);

  /** Currently selected folder full path (undefined = root) */
  const [selectedFolder, setSelectedFolder] = React.useState<string | undefined>(undefined);

  /** Whether the create-library drawer is open */
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = React.useState(false);

  const [openUploadDrawer, setOpenUploadDrawer] = React.useState(false);
  const [uploadTargetTagId, setUploadTargetTagId] = React.useState<string | null>(null);

  /** Fetch all tags of type "document" to build the folder tree */
  const {
    data: tags,
    isLoading,
    isError,
    refetch,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", limit: 100, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );

  const [fetchAllDocuments, { data: allDocuments }] =
    useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation();

  React.useEffect(() => {
    fetchAllDocuments({ filters: {} });
  }, [fetchAllDocuments]);
  /** Build the TagNode tree from the flat list of tags */
  const tree = React.useMemo<TagNode | null>(() => (tags ? buildTree(tags) : null), [tags]);

  /** Return sorted list of direct children for a given node */
  const getChildren = React.useCallback((n: TagNode) => {
    const arr = Array.from(n.children.values());
    arr.sort((a, b) => a.name.localeCompare(b.name));
    return arr;
  }, []);

  /**
   * Expand or collapse the entire tree
   * @param expand - if true, expand all folders; if false, collapse all
   */
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

  /** Whether the tree is fully expanded */
  const allExpanded = React.useMemo(() => expanded.length > 0, [expanded]);

  /** the toggle retrievable handler */
  const { toggleRetrievable, removeFromLibrary, preview } = useDocumentCommands({
    refetchTags: refetch,
    refetchDocs: () => fetchAllDocuments({ filters: {} }),
  });

  const { handleDeleteFolder } = useCascadeDeleteLibrary({
    allItems: allDocuments ?? [],
    // getTags: (d: DocumentMetadata) => d.tags ?? [], // default works already
    selectedFolder,
    setSelectedFolder,
    expanded,
    setExpanded,
    refetchTags: refetch,
    refetchItems: () => fetchAllDocuments({ filters: {} }),
    itemKey: "documentLabel",
  });
  return (
    <Box display="flex" flexDirection="column" gap={2}>
      {/* Breadcrumb navigation and create-library button */}
      {/* Toolbar with both actions */}
      <Box display="flex" alignItems="center" justifyContent="space-between">
        <Breadcrumbs>
          <Chip
            label={t("documentLibrariesList.documents")}
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
            {t("documentLibrariesList.createLibrary")}
          </Button>
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={() => {
              if (!selectedFolder) return; // or handle root uploads
              const node = findNode(tree, selectedFolder);
              const firstTagId = node?.tagsHere?.[0]?.id;
              if (firstTagId) {
                setUploadTargetTagId(firstTagId);
                setOpenUploadDrawer(true);
              }
            }}
            disabled={!selectedFolder} // disable if no folder selected
            sx={{ borderRadius: "8px" }}
          >
            {t("documentLibrary.uploadInLibrary")}
          </Button>
        </Box>
      </Box>

      {/* Loading state */}
      {isLoading && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography variant="body2">{t("documentLibrary.loadingLibraries")}</Typography>
        </Card>
      )}

      {/* Error state */}
      {isError && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography color="error">{t("documentLibrary.failedToLoad")}</Typography>
          <Button onClick={() => refetch()} sx={{ mt: 1 }} size="small" variant="outlined">
            {t("dialogs.retry")}
          </Button>
        </Card>
      )}

      {/* Folder tree */}
      {!isLoading && !isError && tree && (
        <Card sx={{ borderRadius: 3 }}>
          {/* Tree header with expand/collapse all control */}
          <Box display="flex" alignItems="center" justifyContent="space-between" px={1} py={0.5}>
            <Typography variant="subtitle2" color="text.secondary">
              {t("documentLibrary.folders")}
            </Typography>
            <Tooltip
              title={allExpanded ? t("documentLibrariesList.collapseAll") : t("documentLibrariesList.expandAll")}
            >
              <IconButton size="small" onClick={() => setAllExpanded(!allExpanded)} disabled={!tree}>
                {allExpanded ? <UnfoldLessIcon fontSize="small" /> : <UnfoldMoreIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          </Box>

          {/* Recursive folder rendering */}
          <Box px={1} pb={1}>
            <DocumentLibraryTree
              tree={tree}
              expanded={expanded}
              setExpanded={setExpanded}
              selectedFolder={selectedFolder}
              setSelectedFolder={setSelectedFolder}
              getChildren={getChildren}
              documents={allDocuments ?? []}
              onPreview={preview}
              onToggleRetrievable={toggleRetrievable}
              onRemoveFromLibrary={removeFromLibrary}
              onDeleteFolder={handleDeleteFolder}
            />
          </Box>
          {/* ⬇️ Document list appears under the tree */}
        </Card>
      )}

      <DocumentUploadDrawer
        isOpen={openUploadDrawer}
        onClose={() => setOpenUploadDrawer(false)}
        onUploadComplete={async () => {
          await refetch(); // reload all tags
          await fetchAllDocuments({ filters: {} }); // reload all documents
        }}
        metadata={{ tags: [uploadTargetTagId] }}
      />

      {/* Create-library drawer */}
      <LibraryCreateDrawer
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
        onLibraryCreated={async () => {
          await refetch();
        }}
        mode="documents"
        currentPath={selectedFolder} // undefined for root-level creation
      />
    </Box>
  );
}
