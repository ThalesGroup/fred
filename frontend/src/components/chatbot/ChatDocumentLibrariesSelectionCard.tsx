// components/chat/LibrariesSelectionTreeCard.tsx
import * as React from "react";
import { useMemo, useState, useCallback } from "react";
import { Box, Checkbox, TextField, Typography, useTheme } from "@mui/material";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { useTranslation } from "react-i18next";
import {
  TagType,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface ChatDocumentLibrariesSelectionCardProps {
  selectedLibrariesIds: string[];
  setSelectedLibrariesIds: (ids: string[]) => void;
  libraryType: TagType;
}

type Lib = Pick<TagWithItemsId, "id" | "name" | "path" | "description">;

type TagNode = {
  name: string; // segment label
  full: string; // e.g. "thales/six"
  children: Map<string, TagNode>;
  tagsHere: Lib[]; // real tags exactly at this node (usually 0 or 1)
};

function buildTree(libs: Lib[]): TagNode {
  const root: TagNode = { name: "", full: "", children: new Map(), tagsHere: [] };
  const ensure = (segs: string[]) => {
    let curr = root;
    let acc: string[] = [];
    for (const s of segs) {
      acc.push(s);
      const key = acc.join("/");
      if (!curr.children.has(s)) curr.children.set(s, { name: s, full: key, children: new Map(), tagsHere: [] });
      curr = curr.children.get(s)!;
    }
    return curr;
  };
  for (const t of libs) {
    const segs = (t.path ? t.path.split("/").filter(Boolean) : []).concat(t.name);
    const node = ensure(segs);
    node.tagsHere.push(t);
  }
  return root;
}

function collectDescendantIds(n: TagNode): Set<string> {
  const ids = new Set<string>();
  n.tagsHere.forEach((t) => ids.add(t.id));
  for (const ch of n.children.values()) collectDescendantIds(ch).forEach((id) => ids.add(id));
  return ids;
}

function computeCheck(n: TagNode, selected: Set<string>) {
  const ids = collectDescendantIds(n);
  if (ids.size === 0) return { checked: false, indeterminate: false, ids };
  let count = 0;
  ids.forEach((id) => selected.has(id) && count++);
  if (count === 0) return { checked: false, indeterminate: false, ids };
  if (count === ids.size) return { checked: true, indeterminate: false, ids };
  return { checked: false, indeterminate: true, ids };
}

function filterTree(root: TagNode, q: string): TagNode {
  if (!q) return root;
  const needle = q.toLowerCase();
  const dfs = (n: TagNode): TagNode | null => {
    const labelHit =
      n.name.toLowerCase().includes(needle) ||
      n.full.toLowerCase().includes(needle) ||
      n.tagsHere.some((t) => (t.description ?? "").toLowerCase().includes(needle));
    const keptChildren = new Map<string, TagNode>();
    for (const [k, ch] of n.children) {
      const fc = dfs(ch);
      if (fc) keptChildren.set(k, fc);
    }
    if (n.full === "" || labelHit || keptChildren.size > 0 || n.tagsHere.length > 0)
      return { ...n, children: keptChildren };
    return null;
  };
  return dfs(root) ?? { ...root, children: new Map() };
}

function collectAllKeys(n: TagNode, acc: string[] = []): string[] {
  for (const ch of n.children.values()) {
    acc.push(ch.full);
    collectAllKeys(ch, acc);
  }
  return acc;
}

export function ChatDocumentLibrariesSelectionCard({
  selectedLibrariesIds,
  setSelectedLibrariesIds,
  libraryType,
}: ChatDocumentLibrariesSelectionCardProps) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { data: libraries = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: libraryType });
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string[]>([]);

  const libs = useMemo<Lib[]>(
    () =>
      (libraries as any[]).map((x) => ({
        id: x.id,
        name: x.name,
        path: x.path ?? null,
        description: x.description ?? null,
      })),
    [libraries],
  );
  const tree = useMemo(() => buildTree(libs), [libs]);
  const filtered = useMemo(() => filterTree(tree, search), [tree, search]);
  const selected = useMemo(() => new Set(selectedLibrariesIds), [selectedLibrariesIds]);

  const label = libraryType === "document" ? t("chatbot.searchDocumentLibraries") : t("chatbot.searchPromptLibraries");

  const toggleIds = useCallback(
    (ids: Set<string>, force?: boolean) => {
      const next = new Set(selected);
      const allSelected = Array.from(ids).every((id) => next.has(id));
      const shouldSelect = force ?? !allSelected;
      if (shouldSelect) ids.forEach((id) => next.add(id));
      else ids.forEach((id) => next.delete(id));
      setSelectedLibrariesIds(Array.from(next));
    },
    [selected, setSelectedLibrariesIds],
  );

  const Row = ({ node }: { node: TagNode; isExpanded: boolean }) => {
    if (node.full === "") return null;
    const { checked, indeterminate, ids } = computeCheck(node, selected);
    const leaf = node.tagsHere[0];

    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          minHeight: 34,
          px: 0.5,
          pr: 1,
          gap: 1,
          borderRadius: 1,
          "&:hover": { background: theme.palette.action.hover, cursor: "pointer" },
        }}
        onClick={(e) => {
          e.stopPropagation();
          toggleIds(ids, !checked);
        }}
      >
        <Checkbox
          size="small"
          checked={checked}
          indeterminate={indeterminate}
          onClick={(e) => {
            e.stopPropagation();
            toggleIds(ids, !checked);
          }}
        />

        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" noWrap title={leaf?.name ?? node.name}>
            {leaf?.name ?? node.name}
          </Typography>
        </Box>
      </Box>
    );
  };

  const renderTree = (n: TagNode): React.ReactNode[] =>
    Array.from(n.children.values())
      .sort((a, b) => {
        const af = a.children.size > 0;
        const bf = b.children.size > 0;
        if (af !== bf) return af ? -1 : 1; // folders first
        return a.name.localeCompare(b.name);
      })
      .map((c) => {
        const isExpanded = search ? true : expanded.includes(c.full);
        return (
          <TreeItem key={c.full} itemId={c.full} label={<Row node={c} isExpanded={isExpanded} />}>
            {renderTree(c)}
          </TreeItem>
        );
      });

  const expandedWhenSearching = useMemo(() => collectAllKeys(filtered), [filtered]);
  return (
    <Box sx={{ width: 420, height: 460, display: "flex", flexDirection: "column" }}>
      <Box sx={{ mx: 2, mt: 2, mb: 1 }}>
        <TextField
          autoFocus
          label={label}
          variant="outlined"
          size="small"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          fullWidth
        />
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", overflowX: "hidden", px: 1, pb: 1.5 }}>
        <SimpleTreeView
          expandedItems={search ? expandedWhenSearching : expanded}
          onExpandedItemsChange={(_, ids) => setExpanded(ids as string[])}
          slots={{ expandIcon: KeyboardArrowRightIcon, collapseIcon: KeyboardArrowDownIcon }}
        >
          {renderTree(filtered)}
        </SimpleTreeView>
      </Box>
    </Box>
  );
}
