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

import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import PersonAddAltIcon from "@mui/icons-material/PersonAddAlt";
import { Box, Checkbox, IconButton } from "@mui/material";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { getConfig } from "../../common/config";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";

import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
import { TagNode } from "../../shared/utils/tagTree";
import { Resource, TagWithItemsId } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryShareDialog } from "../documents/libraries/sharing/DocumentLibraryShareDialog";
import { ResourceRowCompact } from "./ResourceRowCompact";

/* --------------------------------------------------------------------------
 * Helpers (mirrors DocumentLibraryTree)
 * -------------------------------------------------------------------------- */

function getPrimaryTag(n: TagNode): TagWithItemsId | undefined {
  return n.tagsHere?.[0];
}

/** Resource belongs directly to this node (has one of this node's tag ids). */
function resourceBelongsToNode(r: Resource, node: TagNode): boolean {
  const idsAtNode = (node.tagsHere ?? []).map((t) => t.id);
  const tagIds = (r as any).library_tags ?? (r as any).tag_ids ?? [];
  return Array.isArray(tagIds) && tagIds.some((id) => idsAtNode.includes(id));
}

/** All resources in a node’s subtree (node + descendants). */
function resourcesInSubtree(root: TagNode, all: Resource[], getChildren: (n: TagNode) => TagNode[]): Resource[] {
  const stack: TagNode[] = [root];
  const out: Resource[] = [];
  while (stack.length) {
    const cur = stack.pop()!;
    for (const r of all) if (resourceBelongsToNode(r, cur)) out.push(r);
    for (const ch of getChildren(cur)) stack.push(ch);
  }
  return out;
}

/* --------------------------------------------------------------------------
 * Component
 * -------------------------------------------------------------------------- */

type Props = {
  tree: TagNode;
  expanded: string[];
  setExpanded: (ids: string[]) => void;
  selectedFolder: string | null;
  setSelectedFolder: (full: string | null) => void;
  getChildren: (n: TagNode) => TagNode[];
  resources: Resource[];
  onPreview?: (p: Resource) => void;
  onEdit?: (p: Resource) => void;
  onRemoveFromLibrary?: (p: Resource, tag: TagWithItemsId) => void;
  onDeleteFolder?: (tag: TagWithItemsId) => void;
  canDeleteFolder?: boolean;
  ownerNamesById?: Record<string, string>;

  /** NEW: selection for bulk delete — mirrors DocumentLibraryTree
   * map: resourceId(string) -> tag to delete from (selection context)
   */
  selectedItems?: Record<string, TagWithItemsId>;
  setSelectedItems?: React.Dispatch<React.SetStateAction<Record<string, TagWithItemsId>>>;
};

export function ResourceLibraryTree({
  tree,
  expanded,
  setExpanded,
  selectedFolder,
  setSelectedFolder,
  getChildren,
  resources,
  onPreview,
  onEdit,
  onRemoveFromLibrary,
  onDeleteFolder,
  canDeleteFolder = true,
  ownerNamesById,
  selectedItems = {},
  setSelectedItems,
}: Props) {
  const { t } = useTranslation();
  /** Select/unselect all resources in a folder’s subtree (by that folder’s primary tag). */
  const toggleFolderSelection = React.useCallback(
    (node: TagNode) => {
      if (!setSelectedItems) return;
      const tag = getPrimaryTag(node);
      if (!tag) return;

      const subtree = resourcesInSubtree(node, resources, getChildren);
      const eligible = subtree.filter(
        (r) => resourceBelongsToNode(r, node) && (r as any).library_tags?.includes(tag.id),
      );
      if (eligible.length === 0) return;

      setSelectedItems((prev) => {
        const anySelectedHere = eligible.some((r) => prev[String(r.id)]?.id === tag.id);
        const next = { ...prev };
        if (anySelectedHere) {
          eligible.forEach((r) => {
            const rid = String(r.id);
            if (next[rid]?.id === tag.id) delete next[rid];
          });
        } else {
          eligible.forEach((r) => {
            next[String(r.id)] = tag;
          });
        }
        return next;
      });
    },
    [resources, getChildren, setSelectedItems],
  );

  const [shareTarget, setShareTarget] = React.useState<TagNode | null>(null);

  const { feature_flags } = getConfig();

  const handleCloseShareDialog = React.useCallback(() => {
    setShareTarget(null);
  }, []);

  /** Recursive renderer. */
  const renderTree = (n: TagNode): React.ReactNode[] =>
    getChildren(n).map((c) => {
      const isExpanded = expanded.includes(c.full);
      const isSelected = selectedFolder === c.full;

      const hereTag = getPrimaryTag(c);

      // Resources directly in this folder
      const resourcesHere = resources.filter((r) => resourceBelongsToNode(r, c));

      // Folder tri-state against THIS folder’s tag.
      const subtree = resourcesInSubtree(c, resources, getChildren);
      const eligible = hereTag ? subtree.filter((r) => (r as any).library_tags?.includes(hereTag.id)) : [];
      const totalForTag = eligible.length;
      const selectedForTag = hereTag
        ? eligible.filter((r) => selectedItems[String(r.id)]?.id === hereTag.id).length
        : 0;

      const folderChecked = totalForTag > 0 && selectedForTag === totalForTag;
      const folderIndeterminate = selectedForTag > 0 && selectedForTag < totalForTag;

      const canBeDeleted = !!hereTag && !!onDeleteFolder && canDeleteFolder;
      const ownerName = hereTag ? ownerNamesById?.[hereTag.owner_id] : undefined;

      return (
        <TreeItem
          key={c.full}
          itemId={c.full}
          label={
            <Box
              sx={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 1,
                px: 0.5,
                borderRadius: 0.5,
                bgcolor: isSelected ? "action.selected" : "transparent",
              }}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFolder(isSelected ? null : c.full);
              }}
            >
              {/* Left: tri-state + folder icon + name */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flex: 1 }}>
                <Checkbox
                  size="small"
                  indeterminate={folderIndeterminate}
                  checked={folderChecked}
                  disabled={!hereTag || !setSelectedItems}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleFolderSelection(c);
                  }}
                  onMouseDown={(e) => e.stopPropagation()}
                />
                {isExpanded ? <FolderOpenOutlinedIcon fontSize="small" /> : <FolderOutlinedIcon fontSize="small" />}
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
              </Box>

              {/* Right: owner + share + delete */}
              <Box sx={{ ml: "auto", display: "flex", alignItems: "center" }}>
                {feature_flags.is_rebac_enabled && ownerName && (
                  <SimpleTooltip title={t("documentLibraryTree.ownerTooltip", { name: ownerName })}>
                    <Box
                      sx={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 0.5,
                        px: 0.75,
                        py: 0.25,
                        borderRadius: 999,
                        bgcolor: "action.hover",
                        color: "text.secondary",
                        fontSize: "0.75rem",
                        mr: 0.5,
                      }}
                    >
                      <Box
                        sx={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          bgcolor: "primary.main",
                          flexShrink: 0,
                        }}
                      />
                      <span style={{ whiteSpace: "nowrap" }}>{ownerName}</span>
                    </Box>
                  </SimpleTooltip>
                )}
                {feature_flags.is_rebac_enabled && (
                  <SimpleTooltip
                    title={t("documentLibraryTree.shareFolder")}
                    // ATTENTION enterTouchDelay={10}
                  >
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (hereTag) setShareTarget(c);
                      }}
                    >
                      <PersonAddAltIcon fontSize="small" />
                    </IconButton>
                  </SimpleTooltip>
                )}
                <SimpleTooltip
                  title={
                    canBeDeleted ? t("documentLibraryTree.deleteFolder") : t("documentLibraryTree.deleteFolderDisabled")
                  }
                  // ATTENTION enterTouchDelay={10}
                >
                  <DeleteIconButton
                    size="small"
                    disabled={!canBeDeleted}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteFolder(hereTag);
                    }}
                  />
                </SimpleTooltip>
              </Box>
            </Box>
          }
        >
          {/* Child folders */}
          {c.children.size ? renderTree(c) : null}

          {/* Resources directly in this folder */}
          {resourcesHere.map((r) => {
            const rid = String(r.id);
            const tag = hereTag; // context tag for row selection/delete
            const isSelectedHere = tag ? selectedItems[rid]?.id === tag.id : false;

            return (
              <TreeItem
                key={rid}
                itemId={rid}
                label={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 0.5 }}>
                    <Checkbox
                      size="small"
                      disabled={!tag || !setSelectedItems}
                      checked={!!isSelectedHere}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!tag || !setSelectedItems) return;
                        setSelectedItems((prev) => {
                          const next = { ...prev };
                          if (next[rid]?.id === tag.id) delete next[rid];
                          else next[rid] = tag;
                          return next;
                        });
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                    />

                    <ResourceRowCompact
                      resource={r}
                      onPreview={onPreview}
                      onEdit={onEdit}
                      onRemoveFromLibrary={
                        tag && onRemoveFromLibrary ? (rr) => onRemoveFromLibrary(rr, tag) : undefined
                      }
                    />
                  </Box>
                }
              />
            );
          })}
        </TreeItem>
      );
    });

  return (
    <>
      <SimpleTreeView
        sx={{
          "& .MuiTreeItem-content .MuiTreeItem-label": { flex: 1, width: "100%", overflow: "visible" },
        }}
        expandedItems={expanded}
        onExpandedItemsChange={(_, ids) => setExpanded(ids as string[])}
        slots={{ expandIcon: KeyboardArrowRightIcon, collapseIcon: KeyboardArrowDownIcon }}
      >
        {renderTree(tree)}
      </SimpleTreeView>
      <DocumentLibraryShareDialog
        open={!!shareTarget}
        tag={shareTarget?.tagsHere?.[0]}
        onClose={handleCloseShareDialog}
      />
    </>
  );
}
