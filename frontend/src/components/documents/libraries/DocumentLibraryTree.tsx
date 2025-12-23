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
import { Box, Button, Checkbox, IconButton, Skeleton, Tooltip } from "@mui/material";
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

/** Docs linked to any of the provided tag ids (deduped). */
function getDocsForTags(tagIds: string[], docsByTagId: Record<string, DocumentMetadata[]>): DocumentMetadata[] {
  if (!tagIds.length) return [];
  const seen = new Set<string>();
  const out: DocumentMetadata[] = [];
  for (const tagId of tagIds) {
    const docs = docsByTagId[tagId] || [];
    for (const doc of docs) {
      const uid = doc.identity.document_uid;
      if (seen.has(uid)) continue;
      seen.add(uid);
      out.push(doc);
    }
  }
  return out;
}

/** All docs in a node’s subtree (node + descendants, deduped). */
function docsInSubtree(
  root: TagNode,
  docsByTagId: Record<string, DocumentMetadata[]>,
  getChildren: (n: TagNode) => TagNode[],
): DocumentMetadata[] {
  const stack: TagNode[] = [root];
  const out: DocumentMetadata[] = [];
  const seen = new Set<string>();

  while (stack.length) {
    const cur = stack.pop()!;
    const tagIds = (cur.tagsHere ?? []).map((t) => t.id).filter(Boolean);
    for (const doc of getDocsForTags(tagIds, docsByTagId)) {
      const uid = doc.identity.document_uid;
      if (seen.has(uid)) continue;
      seen.add(uid);
      out.push(doc);
    }
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
  downloadingDocUid?: string | null;
  onToggleRetrievable: (doc: DocumentMetadata) => void;
  onRemoveFromLibrary: (doc: DocumentMetadata, tag: TagWithItemsId) => void;
  onDeleteFolder?: (tag: TagWithItemsId) => void;
  /** docUid -> tag to delete from (selection context) */
  selectedDocs: Record<string, TagWithItemsId>;
  setSelectedDocs: React.Dispatch<React.SetStateAction<Record<string, TagWithItemsId>>>;
  documentsByTagId: Record<string, DocumentMetadata[]>;
  selectedFolderTotal?: number;
  perTagTotals?: Record<string, number>;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onLoadAll?: () => void;
  isLoadingMore?: boolean;
  canDeleteDocument?: boolean;
  canDeleteFolder?: boolean;
  ownerNamesById?: Record<string, string>;
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
  downloadingDocUid,
  onToggleRetrievable,
  onRemoveFromLibrary,
  onDeleteFolder,
  selectedDocs,
  setSelectedDocs,
  documentsByTagId,
  selectedFolderTotal,
  perTagTotals,
  hasMore = false,
  onLoadMore,
  onLoadAll,
  isLoadingMore = false,
  canDeleteDocument = true,
  canDeleteFolder = true,
  ownerNamesById,
}: DocumentLibraryTreeProps) {
  const { t } = useTranslation();
  const [shareTarget, setShareTarget] = React.useState<TagNode | null>(null);

  const { feature_flags } = getConfig();

  const handleCloseShareDialog = React.useCallback(() => {
    setShareTarget(null);
  }, []);

  // Precompute totals per node using cached totals when available (recursive on children).
  const totalsByNode = React.useMemo(() => {
    const m = new Map<string, number>();

    const compute = (node: TagNode): number => {
      if (m.has(node.full)) return m.get(node.full)!;
      const tag = getPrimaryTag(node);
      const tagId = tag?.id;
      const selfCount = tagId ? perTagTotals?.[tagId] ?? documentsByTagId[tagId]?.length ?? 0 : 0;
      let childSum = 0;
      for (const child of getChildren(node)) {
        childSum += compute(child);
      }
      const total = selfCount + childSum;
      m.set(node.full, total);
      return total;
    };

    if (tree) {
      compute(tree);
    }
    return m;
  }, [tree, perTagTotals, documentsByTagId, getChildren]);

  /** Select/unselect all docs in a folder’s subtree (by that folder’s primary tag). */
  const toggleFolderSelection = React.useCallback(
    (node: TagNode) => {
      const tag = getPrimaryTag(node);
      if (!tag) return;

      const subtree = docsInSubtree(node, documentsByTagId, getChildren);
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

      const tagIdsHere = (c.tagsHere ?? []).map((t) => t.id).filter(Boolean);
      const directDocs = getDocsForTags(tagIdsHere, documentsByTagId);
      const folderTag = getPrimaryTag(c);

      // Folder tri-state against THIS folder’s tag.
      const subtreeDocs = docsInSubtree(c, documentsByTagId, getChildren);
      const eligibleDocs = folderTag
        ? subtreeDocs.filter((d) => (d.tags?.tag_ids ?? []).includes(folderTag.id))
        : [];
      const cachedTotal = folderTag ? perTagTotals?.[folderTag.id] : undefined;
      const aggregatedTotal = totalsByNode.get(c.full);
      const totalDocCount =
        isSelected && selectedFolderTotal !== undefined
          ? selectedFolderTotal
          : aggregatedTotal ?? cachedTotal ?? new Set(subtreeDocs.map((d) => d.identity.document_uid)).size;
      const totalForTag = folderTag
        ? isSelected && selectedFolderTotal !== undefined
          ? selectedFolderTotal
          : cachedTotal ?? eligibleDocs.length
        : 0;
      const selectedForTag = folderTag
        ? eligibleDocs.filter((d) => selectedDocs[d.identity.document_uid]?.id === folderTag.id).length
        : 0;

      const folderChecked = totalForTag > 0 && selectedForTag === totalForTag;
      const folderIndeterminate = selectedForTag > 0 && selectedForTag < totalForTag;

      const canBeDeleted = !!folderTag && !!onDeleteFolder && canDeleteFolder;
      const ownerName = folderTag ? ownerNamesById?.[folderTag.owner_id] : undefined;

      // When not selected and we never loaded docs for this tag, avoid showing 0 as if known.
      const hasDataForTag = folderTag
        ? Boolean(documentsByTagId[folderTag.id]?.length) || perTagTotals?.[folderTag.id] !== undefined
        : false;
      const displayCount =
        !isSelected && !hasDataForTag && totalDocCount === 0 ? "…" : String(totalDocCount);

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
                <Tooltip key={`${c.name}_count`} title={`${displayCount} Documents`} arrow>
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
                    {displayCount}
                  </Box>
                </Tooltip>
              </Box>

              {/* Right: owner + share + delete */}
              <Box sx={{ ml: "auto", display: "flex", alignItems: "center" }}>
                {feature_flags.is_rebac_enabled && ownerName && (
                  <Tooltip title={t("documentLibraryTree.ownerTooltip", { name: ownerName })}>
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
                  </Tooltip>
                )}
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
                      isDownloading={downloadingDocUid === doc.identity.document_uid}
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
          {isSelected && hasMore && (
            <Box sx={{ width: "100%", pl: 5, pr: 0.5, pb: 1, display: "flex", flexDirection: "column", gap: 1 }}>
              {!isLoadingMore && (
                <>
                  <Button
                    size="small"
                    variant="contained"
                    onClick={(e) => {
                      e.stopPropagation();
                      onLoadMore?.();
                    }}
                    sx={{
                      width: "100%",
                      alignSelf: "stretch",
                      textTransform: "none",
                      justifyContent: "center",
                      borderRadius: 1,
                      boxShadow: "none",
                      bgcolor: "primary.main",
                      color: "primary.contrastText",
                      "&:hover": { bgcolor: "primary.dark" },
                    }}
                  >
                    {t("documentLibrary.loadMore", "Load more")}
                  </Button>
                  <Button
                    size="small"
                    variant="text"
                    onClick={(e) => {
                      e.stopPropagation();
                      onLoadAll?.();
                    }}
                    sx={{
                      width: "100%",
                      alignSelf: "stretch",
                      textTransform: "none",
                      justifyContent: "center",
                    }}
                  >
                    {t("documentLibrary.loadAll", "Load all")}
                  </Button>
                </>
              )}

              {isLoadingMore ? (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                  {Array.from({ length: 3 }).map((_, idx) => (
                    <Box key={idx} sx={{ display: "flex", alignItems: "center", gap: 1, pl: 1.25, pr: 0.5 }}>
                      <Skeleton animation="pulse" variant="rounded" width={18} height={18} />
                      <Box
                        sx={{
                          display: "grid",
                          gridTemplateColumns: "minmax(0, 2fr) auto auto auto auto auto auto auto",
                          alignItems: "center",
                          columnGap: 2,
                          width: "100%",
                          px: 1,
                          py: 0.75,
                          borderRadius: 1,
                          border: "1px solid",
                          borderColor: "divider",
                          bgcolor: "background.paper",
                        }}
                      >
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                          <Skeleton animation="pulse" variant="circular" width={20} height={20} />
                          <Skeleton animation="pulse" variant="text" width="55%" />
                          <Skeleton animation="pulse" variant="rounded" width={32} height={18} />
                        </Box>
                        <Skeleton animation="pulse" variant="circular" width={22} height={22} />
                        <Skeleton animation="pulse" variant="circular" width={22} height={22} />
                        <Skeleton animation="pulse" variant="circular" width={22} height={22} />
                        <Box sx={{ display: "flex", gap: 0.5 }}>
                          {["success.light", "success.light", "success.light", "grey.400", "grey.500"].map(
                            (color, bubbleIdx) => (
                              <Skeleton
                                key={bubbleIdx}
                                animation="pulse"
                                variant="circular"
                                width={18}
                                height={18}
                                sx={{ bgcolor: color, opacity: 0.65 }}
                              />
                            ),
                          )}
                        </Box>
                        <Skeleton animation="pulse" variant="text" width={64} />
                        <Skeleton animation="pulse" variant="circular" width={24} height={24} />
                        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, justifySelf: "end" }}>
                          <Skeleton animation="pulse" variant="circular" width={24} height={24} />
                          <Skeleton animation="pulse" variant="circular" width={24} height={24} />
                        </Box>
                      </Box>
                    </Box>
                  ))}
                </Box>
              ) : null}
            </Box>
          )}
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
