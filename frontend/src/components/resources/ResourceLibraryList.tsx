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
 * This component renders the "Prompt Libraries" view for the knowledge flow app.
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
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  ResourceKind,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTree, TagNode, findNode } from "../tags/tagTree";
import { useTranslation } from "react-i18next";
import { useResourceCommands } from "./useResourceCommands";
import { ResourceLibraryTree } from "./ResourceLibraryTree";
import { LibraryCreateDrawer } from "../../common/LibraryCreateDrawer";
import { PromptEditorModal } from "./PromptEditorModal";
import { TemplateEditorModal } from "./TemplateEditorModal";

const useKindLabels = (kind: "prompt" | "template") => {
  const { t } = useTranslation();
  const one = t(`resource.kind.${kind}.one`);
  const other = t(`resource.kind.${kind}.other`);
  return { one, other };
};
// Accept kind prop to ensure this component is typed correctly
type Props = {
  kind: ResourceKind;
};

export default function ResourceLibraryList({ kind }: Props) {
  console.log("ResourceLibraryList rendered with kind:", kind);
  const { one: typeOne, other: typePlural } = useKindLabels(kind);
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

  // 1) Query tags filtered by the current resource kind ("prompt" | "template")
  const {
    data: allTags,
    isLoading,
    isError,
    refetch: refetchTags,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: kind, limit: 10000, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );
  // 2) Query all resources of the current kind
  const { data: allResources, refetch: refetchResources } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({
    kind,
  });

  /** Build the TagNode tree from the flat list of tags */
  const tree = React.useMemo<TagNode | null>(() => (allTags ? buildTree(allTags) : null), [allTags]);

  // after your selectedTagIds memo

  /** Return sorted list of direct children for a given node */
  const getChildren = React.useCallback(
    (n: TagNode) => {
      const arr = Array.from(n.children.values());
      arr.sort((a, b) => a.name.localeCompare(b.name));
      return arr;
    },
    [kind],
  );

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
  const { removeFromLibrary, createResource } = useResourceCommands(kind, {
    refetchTags: refetchTags,
    refetchResources: refetchResources,
  });
  React.useEffect(() => {
    setOpenCreatePrompt(false);
  }, [kind]);
  return (
    <Box display="flex" flexDirection="column" gap={2}>
      {/* Breadcrumb navigation and create-library button */}
      {/* Toolbar with both actions */}
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
            {t("resourceLibrary.uploadInLibrary", { typeOne })}
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
          <Typography color="error">{t("resourceLibrary.failedToLoad")}</Typography>
          <Button onClick={() => refetchTags()} sx={{ mt: 1 }} size="small" variant="outlined">
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
              {t("resourceLibrary.folders")}
            </Typography>
            <Tooltip title={allExpanded ? t("resourceLibrary.collapseAll") : t("resourceLibrary.expandAll")}>
              <IconButton size="small" onClick={() => setAllExpanded(!allExpanded)} disabled={!tree}>
                {allExpanded ? <UnfoldLessIcon fontSize="small" /> : <UnfoldMoreIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          </Box>

          {/* Recursive folder rendering */}
          <Box px={1} pb={1}>
            <ResourceLibraryTree
              tree={tree}
              expanded={expanded}
              setExpanded={setExpanded}
              selectedFolder={selectedFolder}
              setSelectedFolder={setSelectedFolder}
              getChildren={getChildren}
              resources={allResources ?? []}
              onRemoveFromLibrary={removeFromLibrary}
            />
          </Box>
          {/* ⬇️ Document list appears under the tree */}
        </Card>
      )}
      {kind === "template" ? (
        <TemplateEditorModal
          isOpen={openCreatePrompt}
          onClose={() => setOpenCreatePrompt(false)}
          onSave={(payload) => {
            if (uploadTargetTagId) {
              // payload is ResourceCreate-like { name?, description?, content }
              createResource(payload, uploadTargetTagId);
              setOpenCreatePrompt(false);
            }
          }}
        />
      ) : (
        <PromptEditorModal
          isOpen={openCreatePrompt}
          onClose={() => setOpenCreatePrompt(false)}
          onSave={(payload) => {
            if (!uploadTargetTagId) return;
            createResource(payload, uploadTargetTagId); // ← same call
            setOpenCreatePrompt(false);
          }}
        />
      )}

      {/* Create-library drawer */}
      <LibraryCreateDrawer
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
        onLibraryCreated={async () => {
          await refetchTags();
        }}
        mode={kind}
        currentPath={selectedFolder} // undefined for root-level creation
      />
    </Box>
  );
}
