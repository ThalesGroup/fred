// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.

import * as React from "react";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import { Box } from "@mui/material";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { TagNode } from "../../tags/tagTree";
import { DocumentRowCompact } from "./DocumentLibraryRow";
import { DocumentMetadata, TagWithItemsId } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface DocumentLibraryTreeProps {
  tree: TagNode;
  expanded: string[];
  setExpanded: (ids: string[]) => void;
  selectedFolder?: string;
  setSelectedFolder: (full: string) => void;
  getChildren: (n: TagNode) => TagNode[];
  documents: DocumentMetadata[];
  onPreview: (doc: DocumentMetadata) => void;
  onToggleRetrievable: (doc: DocumentMetadata) => void;
  onRemoveFromLibrary: (doc: DocumentMetadata, tag: TagWithItemsId) => void;
}

type Props = DocumentLibraryTreeProps;

export function DocumentLibraryTree({
  tree,
  expanded,
  setExpanded,
  selectedFolder,
  setSelectedFolder,
  getChildren,
  documents,
  onPreview,
  onToggleRetrievable,
  onRemoveFromLibrary,
}: Props) {
  const renderTree = (n: TagNode): React.ReactNode[] =>
    getChildren(n).map((c) => {
      const isExpanded = expanded.includes(c.full);
      const isSelected = selectedFolder === c.full;
      // Documents belonging directly to this folder (i.e., matching this folder's own tag id)
      const docsInFolder = documents.filter((doc) =>
        doc.tags.tag_ids?.some((tagId) => c.tagsHere?.some((t) => t.id === tagId)),
      );

      return (
        <TreeItem
          key={c.full}
          itemId={c.full}
          label={
            <Box
              // Parent row: on hover we reveal actions on the right
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 1,
                px: 0.5,
                borderRadius: 0.5,
                bgcolor: isSelected ? "action.selected" : "transparent",
                "&:hover .folder-actions": { opacity: 1 },
              }}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFolder(c.full);
              }}
            >
              {/* Left: icon + name */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                {isExpanded ? <FolderOpenOutlinedIcon fontSize="small" /> : <FolderOutlinedIcon fontSize="small" />}
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
              </Box>
            </Box>
          }
        >
          {/* Child folders */}
          {c.children.size ? renderTree(c) : null}

          {/* Documents inside this folder */}
          {docsInFolder.map((doc) => (
            <TreeItem
              key={doc.identity.document_uid}
              itemId={doc.identity.document_uid}
              label={
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    px: 0.5,
                    cursor: "pointer",
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    // TODO: wire to your preview handler if you have one
                    // handleDocumentPreview(doc)
                    console.log("Open document:", doc);
                  }}
                >
                  <DocumentRowCompact
                    doc={doc}
                    onPreview={(d) => onPreview(d)}
                    onRemoveFromLibrary={(d) => {
                      console.log("Remove from library:", d);
                      const tag = c.tagsHere?.[0];
                      if (tag) onRemoveFromLibrary(d, tag);
                    }}
                    onToggleRetrievable={(d) => onToggleRetrievable(d)}
                  />
                </Box>
              }
            />
          ))}
        </TreeItem>
      );
    });
    
  return (
    <SimpleTreeView
      expandedItems={expanded}
      onExpandedItemsChange={(_, ids) => setExpanded(ids as string[])}
      slots={{
        expandIcon: KeyboardArrowRightIcon,
        collapseIcon: KeyboardArrowDownIcon,
      }}
    >
      {renderTree(tree)}
    </SimpleTreeView>
  );
}
