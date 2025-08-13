// components/prompts/PromptLibraryTree.tsx
import * as React from "react";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import { Box } from "@mui/material";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { TagNode } from "../tags/tagTree";
import { Prompt, TagWithItemsId } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { PromptRowCompact } from "./PromptLibraryRow";

type Props = {
  tree: TagNode;
  expanded: string[];
  setExpanded: (ids: string[]) => void;
  selectedFolder?: string;
  setSelectedFolder: (full: string) => void;
  getChildren: (n: TagNode) => TagNode[];
  prompts: Prompt[];
  onPreview?: (p: Prompt) => void;
  onEdit?: (p: Prompt) => void;
  onRemoveFromLibrary?: (p: Prompt, tag: TagWithItemsId) => void;
};

export function PromptLibraryTree({
  tree,
  expanded,
  setExpanded,
  selectedFolder,
  setSelectedFolder,
  getChildren,
  prompts,
  onPreview,
  onEdit,
  onRemoveFromLibrary,
}: Props) {
  const renderTree = (n: TagNode): React.ReactNode[] =>
    getChildren(n).map((c) => {
      const isExpanded = expanded.includes(c.full);
      const isSelected = selectedFolder === c.full;

      // prompts whose prompt.tags contains any tag that ends here (c.tagsHere)
      const promptsInFolder = prompts.filter((p) =>
        p.tags?.some((tagId) => c.tagsHere?.some((t) => t.id === tagId)),
      );

      const hereTag = c.tagsHere?.[0]; // primary tag for this folder

      return (
        <TreeItem
          key={c.full}
          itemId={c.full}
          label={
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 1,
                px: 0.5,
                borderRadius: 0.5,
                bgcolor: isSelected ? "action.selected" : "transparent",
              }}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedFolder(c.full);
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                {isExpanded ? <FolderOpenOutlinedIcon fontSize="small" /> : <FolderOutlinedIcon fontSize="small" />}
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
              </Box>
            </Box>
          }
        >
          {c.children.size ? renderTree(c) : null}

          {promptsInFolder.map((p) => (
            <TreeItem
              key={p.id}
              itemId={p.id}
              label={
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 0.5 }}>
                  <PromptRowCompact
                    prompt={p}
                    onPreview={onPreview}
                    onEdit={onEdit}
                    onRemoveFromLibrary={
                      hereTag ? (pp) => onRemoveFromLibrary?.(pp, hereTag) : undefined
                    }
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
      slots={{ expandIcon: KeyboardArrowRightIcon, collapseIcon: KeyboardArrowDownIcon }}
    >
      {renderTree(tree)}
    </SimpleTreeView>
  );
}
