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
import { Box, Typography, useTheme } from "@mui/material";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import { useMemo, type ReactNode } from "react";

import type { TagWithItemsId } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { TagNode } from "../../utils/tagTree";

type TagTreeListProps = {
  tree: TagNode | null;
  emptyText?: string;
  getChildren?: (node: TagNode) => TagNode[];
  renderLabel?: (node: TagNode, tag?: TagWithItemsId) => ReactNode;
  renderActions?: (tag: TagWithItemsId, node: TagNode) => ReactNode;
};

const defaultGetChildren = (node: TagNode): TagNode[] => {
  const children = Array.from(node.children.values());
  children.sort((a, b) => a.name.localeCompare(b.name));
  return children;
};

const collectExpanded = (node: TagNode, getChildren: (n: TagNode) => TagNode[], acc: string[] = []): string[] => {
  for (const child of getChildren(node)) {
    if (child.children.size > 0) acc.push(child.full);
    collectExpanded(child, getChildren, acc);
  }
  return acc;
};

export const TagTreeList = ({
  tree,
  emptyText = "No items",
  getChildren = defaultGetChildren,
  renderLabel,
  renderActions,
}: TagTreeListProps) => {
  const theme = useTheme();
  const expandedItems = useMemo(() => (tree ? collectExpanded(tree, getChildren) : []), [tree, getChildren]);

  if (!tree || tree.children.size === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ pb: 0.5 }}>
        {emptyText}
      </Typography>
    );
  }

  const renderTree = (node: TagNode): ReactNode[] =>
    getChildren(node).map((child) => {
      const primaryTag = child.tagsHere?.[0];
      const hasChildren = child.children.size > 0;
      const label = renderLabel ? (
        renderLabel(child, primaryTag)
      ) : (
        <Typography
          variant="body2"
          noWrap
          title={primaryTag?.name ?? child.name}
          color={primaryTag ? "text.primary" : "text.secondary"}
        >
          {primaryTag?.name ?? child.name}
        </Typography>
      );
      const actions = primaryTag && renderActions ? renderActions(primaryTag, child) : null;

      return (
        <TreeItem
          key={child.full}
          itemId={child.full}
          sx={{
            "& .MuiTreeItem-content": {
              width: "100%",
              py: 0.25,
              pr: 0.5,
            },
            "& .TagTreeList-actions": {
              opacity: 0,
              transition: "opacity 160ms ease",
            },
            "& .TagTreeList-row:hover .TagTreeList-actions": {
              opacity: 1,
            },
            "& .MuiTreeItem-content.Mui-focused, & .MuiTreeItem-content.Mui-selected": {
              backgroundColor: "transparent",
            },
          }}
          label={
            <Box
              className="TagTreeList-row"
              sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, width: "100%" }}
            >
              {hasChildren ? <FolderOpenOutlinedIcon fontSize="small" /> : <FolderOutlinedIcon fontSize="small" />}
              <Box sx={{ minWidth: 0, flex: 1 }}>{label}</Box>
              {actions && (
                <Box className="TagTreeList-actions" sx={{ display: "flex", gap: 0.5 }}>
                  {actions}
                </Box>
              )}
            </Box>
          }
        >
          {renderTree(child)}
        </TreeItem>
      );
    });

  return (
    <SimpleTreeView
      expandedItems={expandedItems}
      slots={{ expandIcon: KeyboardArrowRightIcon, collapseIcon: KeyboardArrowDownIcon }}
      sx={{
        "& .MuiTreeItem-group": {
          marginLeft: theme.spacing(1.5),
          paddingLeft: theme.spacing(1.5),
        },
        "& .MuiTreeItem-content .MuiTreeItem-label": {
          flex: 1,
          width: "100%",
          overflow: "visible",
        },
      }}
    >
      {renderTree(tree)}
    </SimpleTreeView>
  );
};
