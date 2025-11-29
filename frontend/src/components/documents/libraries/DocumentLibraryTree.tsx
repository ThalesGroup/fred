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

import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import PersonAddAltIcon from "@mui/icons-material/PersonAddAlt";
import { Box, Checkbox, IconButton, Tooltip } from "@mui/material";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import * as React from "react";
import { useTranslation } from "react-i18next";

import { getConfig } from "../../../common/config";
import type { DocumentMetadata, TagWithItemsId } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { TagNode } from "../../tags/tagTree";
import { DocumentRowCompact } from "./DocumentLibraryRow";
import { DocumentLibraryShareDialog } from "./sharing/DocumentLibraryShareDialog";

/* --------------------------------------------------------------------------
 * Helpers
 * -------------------------------------------------------------------------- */

function getPrimaryTag(n: TagNode): TagWithItemsId | undefined {
  return n.tagsHere?.[0];
}

/** Doc belongs directly to this node (has one of this node's tag ids). */
function docBelongsToNode(doc: DocumentMetadata, node: TagNode): boolean {
  const idsAtNode = (node.tagsHere ?? []).map((t) => t.id);
  const docTagIds = doc.tags?.tag_ids ?? [];
  return docTagIds.some((id) => idsAtNode.includes(id));
}

/** All docs in a node’s subtree (node + descendants). */
function docsInSubtree(
  root: TagNode,
  allDocs: DocumentMetadata[],
  getChildren: (n: TagNode) => TagNode[],
): DocumentMetadata[] {
  const stack: TagNode[] = [root];
  const out: DocumentMetadata[] = [];
  while (stack.length) {
    const cur = stack.pop()!;
    for (const d of allDocs) if (docBelongsToNode(d, cur)) out.push(d);
    for (const ch of getChildren(cur)) stack.push(ch);
  }
  return out;
}

/* --------------------------------------------------------------------------
 * Component
 * -------------------------------------------------------------------------- */

interface DocumentLibraryTreeProps {
  tree: TagNode;
  expanded: string[];
  setExpanded: (ids: string[]) => void;
  selectedFolder: string | null;
  setSelectedFolder: (full: string | null) => void;
  getChildren: (n: TagNode) => TagNode[];
  documents: DocumentMetadata[];
  onPreview: (doc: DocumentMetadata) => void;
  onPdfPreview: (doc: DocumentMetadata) => void;
  onDownload: (doc: DocumentMetadata) => void;
  onToggleRetrievable: (doc: DocumentMetadata) => void;
  onRemoveFromLibrary: (doc: DocumentMetadata, tag: TagWithItemsId) => void;
  onDeleteFolder?: (tag: TagWithItemsId) => void;
  /** docUid -> tag to delete from (selection context) */
  selectedDocs: Record<string, TagWithItemsId>;
  setSelectedDocs: React.Dispatch<React.SetStateAction<Record<string, TagWithItemsId>>>;
  canDeleteDocument?: boolean;
  canDeleteFolder?: boolean;
}

export function DocumentLibraryTree({
  tree,
  expanded,
  setExpanded,
  selectedFolder,
  setSelectedFolder,
  getChildren,
  documents,
  onPreview,
  onPdfPreview,
  onDownload,
  onToggleRetrievable,
  onRemoveFromLibrary,
  onDeleteFolder,
  selectedDocs,
  setSelectedDocs,
  canDeleteDocument = true,
  canDeleteFolder = true,
}: DocumentLibraryTreeProps) {
  const { t } = useTranslation();
  const [shareTarget, setShareTarget] = React.useState<TagNode | null>(null);

  const { feature_flags } = getConfig();

  const handleCloseShareDialog = React.useCallback(() => {
    setShareTarget(null);
  }, []);

  /** Select/unselect all docs in a folder’s subtree (by that folder’s primary tag). */
  const toggleFolderSelection = React.useCallback(
    (node: TagNode) => {
      const tag = getPrimaryTag(node);
      if (!tag) return;

      const subtree = docsInSubtree(node, documents, getChildren);
      const eligible = subtree.filter((d) => (d.tags?.tag_ids ?? []).includes(tag.id));
      if (eligible.length === 0) return;

      setSelectedDocs((prev) => {
        const anySelectedHere = eligible.some((d) => prev[d.identity.document_uid]?.id === tag.id);
        const next = { ...prev };
        if (anySelectedHere) {
          eligible.forEach((d) => {
            const id = d.identity.document_uid;
            if (next[id]?.id === tag.id) delete next[id];
          });
        } else {
          eligible.forEach((d) => {
            next[d.identity.document_uid] = tag;
          });
        }
        return next;
      });
    },
    [documents, getChildren, setSelectedDocs],
  );

  /** Recursive renderer. */
  const renderTree = (n: TagNode): React.ReactNode[] =>
    getChildren(n).map((c) => {
      const isExpanded = expanded.includes(c.full);
      const isSelected = selectedFolder === c.full;

      const directDocs = documents.filter((doc) => docBelongsToNode(doc, c));
      const folderTag = getPrimaryTag(c);

      // Folder tri-state against THIS folder’s tag.
      const subtreeDocs = docsInSubtree(c, documents, getChildren);
      const eligibleDocs = folderTag
        ? subtreeDocs.filter((d) => (d.tags?.tag_ids ?? []).includes(folderTag.id))
        : [];
      const totalDocCount = new Set(subtreeDocs.map((d) => d.identity.document_uid)).size;
      const totalForTag = eligibleDocs.length;
      const selectedForTag = folderTag
        ? eligibleDocs.filter((d) => selectedDocs[d.identity.document_uid]?.id === folderTag.id).length
        : 0;

      const folderChecked = totalForTag > 0 && selectedForTag === totalForTag;
      const folderIndeterminate = selectedForTag > 0 && selectedForTag < totalForTag;

      const canBeDeleted = !!folderTag && !!onDeleteFolder && canDeleteFolder;

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
                setSelectedFolder(isSelected ? null : c.full); // toggle
              }}
            >
              {/* Left: tri-state + folder icon + name + count */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, flex: 1 }}>
                <Checkbox
                  size="small"
                  indeterminate={folderIndeterminate}
                  checked={folderChecked}
                  disabled={!folderTag}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleFolderSelection(c);
                  }}
                  onMouseDown={(e) => e.stopPropagation()}
                />
                {isExpanded ? <FolderOpenOutlinedIcon fontSize="small" /> : <FolderOutlinedIcon fontSize="small" />}
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                <Tooltip key={`${c.name}_count`} title={`${totalDocCount} Documents`} arrow>
                  <Box
                    sx={{
                      bgcolor: "#e0e0e0",
                      color: "#757575",
                      width: "auto",
                      height: 18,
                      paddingLeft: 1.2,
                      paddingRight: 1.2,
                      borderRadius: 25,
                      fontSize: "0.6rem",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {totalDocCount}
                  </Box>
                </Tooltip>
              </Box>

              {/* Right: share + delete */}
              <Box sx={{ ml: "auto", display: "flex", alignItems: "center" }}>
                {feature_flags.is_rebac_enabled && (
                  <Tooltip title={t("documentLibraryTree.shareFolder")} enterTouchDelay={10}>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (folderTag) setShareTarget(c);
                      }}
                    >
                      <PersonAddAltIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip
                  title={
                    canBeDeleted ? t("documentLibraryTree.deleteFolder") : t("documentLibraryTree.deleteFolderDisabled")
                  }
                  enterTouchDelay={10}
                >
                  {/* span needed to trigger tooltip when IconButton is disabled */}
                  <span style={{ display: "inline-flex" }}>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!canBeDeleted || !folderTag || !onDeleteFolder) return;
                        onDeleteFolder(folderTag);
                      }}
                      disabled={!canBeDeleted}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </Box>
            </Box>
          }
        >
          {/* Child folders */}
          {c.children.size ? renderTree(c) : null}

          {/* Documents directly in this folder */}
          {directDocs.map((doc) => {
            const docId = doc.identity.document_uid;
            const tag = folderTag; // context tag for row selection/delete
            const isSelectedHere = tag ? selectedDocs[docId]?.id === tag.id : false;

            return (
              <TreeItem
                key={docId}
                itemId={docId}
                label={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 0.5 }}>
                    <Checkbox
                      size="small"
                      disabled={!tag}
                      checked={!!isSelectedHere}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!tag) return;
                        setSelectedDocs((prev) => {
                          const next = { ...prev };
                          if (next[docId]?.id === tag.id) delete next[docId];
                          else next[docId] = tag;
                          return next;
                        });
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                    />

                    <DocumentRowCompact
                      doc={doc}
                      onPreview={onPreview}
                      onPdfPreview={onPdfPreview}
                      onDownload={onDownload}
                      onRemoveFromLibrary={(d) => {
                        if (!canDeleteDocument || !tag) return;
                        onRemoveFromLibrary(d, tag);
                      }}
                      onToggleRetrievable={onToggleRetrievable}
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
