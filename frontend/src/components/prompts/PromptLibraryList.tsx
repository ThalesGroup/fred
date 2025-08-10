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
import { Box, Breadcrumbs, Button, Card, Chip, Link, Typography } from "@mui/material";
import {
  useSearchPromptsKnowledgeFlowV1PromptsSearchPostMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTree, TagNode, findNode } from "../tags/tagTree";
import { useTranslation } from "react-i18next";
import { usePromptCommands } from "./usePromptCommands";
import { PromptLibraryTree } from "./PromptLibraryTree";
import { LibraryCreateDrawer } from "../../common/LibraryCreateDrawer";
import { EditPromptModal } from "./PromptEditor";

export default function PromptLibraryList() {
  /** get our internalization library for english or french */
  const { t } = useTranslation();

  /** Expanded folder paths in the TreeView */
  const [expanded, setExpanded] = React.useState<string[]>([]);

  /** Currently selected folder full path (undefined = root) */
  const [selectedFolder, setSelectedFolder] = React.useState<string | undefined>(undefined);

  /** Whether the create-library drawer is open */
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = React.useState(false);

  const [openCreatePrompt, setOpenCreatePrompt] = React.useState(false);
  const [uploadTargetTagId, setUploadTargetTagId] = React.useState<string | null>(null);

  /** Fetch all tags of type "prompt" to build the folder tree */
  const {
    data: tags,
    isLoading,
    isError,
    refetch,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "prompt", limit: 100, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );

  const [fetchAllPrompts, { data: allPrompts }] = useSearchPromptsKnowledgeFlowV1PromptsSearchPostMutation();

  React.useEffect(() => {
    fetchAllPrompts({ filters: {} });
  }, [fetchAllPrompts]);
  /** Build the TagNode tree from the flat list of tags */
  const tree = React.useMemo<TagNode | null>(() => (tags ? buildTree(tags) : null), [tags]);

  // after your selectedTagIds memo

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
  const { removeFromLibrary, createPrompt } = usePromptCommands({
    refetchTags: refetch,
    refetchPrompts: () => fetchAllPrompts({ filters: {} }),
  });

  return (
    <Box display="flex" flexDirection="column" gap={2}>
      {/* Breadcrumb navigation and create-library button */}
      {/* Toolbar with both actions */}
      <Box display="flex" alignItems="center" justifyContent="space-between">
        <Breadcrumbs>
          <Chip
            label={t("promptLibrary.documents")}
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
            {t("promptLibrary.createLibrary")}
          </Button>
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={() => {
              if (!selectedFolder) return;
              const node = findNode(tree, selectedFolder);
              const firstTagId = node?.tagsHere?.[0]?.id;
              if (firstTagId) {
                setUploadTargetTagId(firstTagId);
                setOpenCreatePrompt(true);
              }
            }}
            disabled={!selectedFolder} // disable if no folder selected
            sx={{ borderRadius: "8px" }}
          >
            {t("promptLibrary.uploadInLibrary")}
          </Button>
        </Box>
      </Box>

      {/* Loading state */}
      {isLoading && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography variant="body2">{t("promptLibrary.loadingLibraries")}</Typography>
        </Card>
      )}

      {/* Error state */}
      {isError && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography color="error">{t("promptLibrary.failedToLoad")}</Typography>
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
              {t("promptLibrary.folders")}
            </Typography>
            <Tooltip title={allExpanded ? t("promptLibrary.collapseAll") : t("promptLibrary.expandAll")}>
              <IconButton size="small" onClick={() => setAllExpanded(!allExpanded)} disabled={!tree}>
                {allExpanded ? <UnfoldLessIcon fontSize="small" /> : <UnfoldMoreIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          </Box>

          {/* Recursive folder rendering */}
          <Box px={1} pb={1}>
            <PromptLibraryTree
              tree={tree}
              expanded={expanded}
              setExpanded={setExpanded}
              selectedFolder={selectedFolder}
              setSelectedFolder={setSelectedFolder}
              getChildren={getChildren}
              prompts={allPrompts ?? []}
              onRemoveFromLibrary={removeFromLibrary}
            />
          </Box>
          {/* ⬇️ Document list appears under the tree */}
        </Card>
      )}
      <EditPromptModal
        isOpen={openCreatePrompt}
        prompt={null}
        onClose={() => setOpenCreatePrompt(false)}
        onSave={(p) => {
          if (uploadTargetTagId) {
            createPrompt(p, uploadTargetTagId);
            setOpenCreatePrompt(false);
          }
        }}
        getSuggestion={async () => {
          const res = await fetch("/api/ai/suggest-prompt");
          return (await res.json()).suggestion;
        }}
      />
      {/* Create-library drawer */}
      <LibraryCreateDrawer
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
        onLibraryCreated={async () => {
          await refetch();
        }}
        mode="prompts"
        currentPath={selectedFolder} // undefined for root-level creation
      />
    </Box>
  );
}
