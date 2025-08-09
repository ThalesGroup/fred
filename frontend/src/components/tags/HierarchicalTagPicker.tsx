// src/components/HierarchicalTagPicker.tsx
import { Button, Chip, Breadcrumbs, Link, Typography, CircularProgress, Grid2 } from "@mui/material";
import { TagType, TagWithItemsId, useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTagTree, TagNode } from "./TagsUtils";

// ⬇️ CHANGE this import to your actual generated hook for GET /tags
// e.g. import { useTagsGetQuery } from "@/generated/openapi";

type Props = {
  tagType?: TagType;                 // "document" | "prompt"
  pathPrefix: string | undefined;    // e.g. "Sales/HR"
  onChangePrefix: (next?: string) => void;
  onSelectTag?: (tag: TagWithItemsId) => void;
};

export default function HierarchicalTagPicker({
  tagType = "document",
  pathPrefix,
  onChangePrefix,
  onSelectTag,
}: Props) {

  const { data: allTags, isLoading, isError } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: tagType,
    limit: 5000,
    offset: 0,
  });
  if (isLoading || !allTags) return <CircularProgress size={24} />;
  if (isError) return <Typography color="error">Failed to load tags.</Typography>;


  const tree = buildTagTree(allTags);
  const crumbs = (pathPrefix || "").split("/").filter(Boolean);

  // Walk to node for current prefix
  let node: TagNode = tree;
  for (const seg of crumbs) {
    const next = node.children.get(seg);
    if (!next) break;
    node = next;
  }

  const childFolders = Array.from(node.children.values()).sort((a, b) => a.name.localeCompare(b.name));

  const handleCrumbClick = (idx: number) => {
    if (idx < 0) return onChangePrefix(undefined);
    const next = crumbs.slice(0, idx + 1).join("/");
    onChangePrefix(next || undefined);
  };

  return (
    <Grid2 container spacing={2}>
      <Grid2 size={{xs: 12}}>
        <Breadcrumbs>
          <Link component="button" onClick={() => onChangePrefix(undefined)}>All</Link>
          {crumbs.map((c, i) => (
            <Link key={i} component="button" onClick={() => handleCrumbClick(i)}>
              {c}
            </Link>
          ))}
        </Breadcrumbs>
      </Grid2>

      <Grid2 size={{xs: 12}}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Folders</Typography>
        {childFolders.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No sub-folders.</Typography>
        ) : (
          childFolders.map((f) => (
            <Button key={f.full} variant="outlined" size="small" sx={{ mr: 1, mb: 1 }}
              onClick={() => onChangePrefix(f.full)}>
              {f.name}
            </Button>
          ))
        )}
      </Grid2>

      <Grid2 size={{xs: 12}}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Tags here</Typography>
        {node.tags.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No tags at this level.</Typography>
        ) : (
          node.tags
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((t) => (
              <Chip
                key={t.id}
                label={t.name}
                onClick={onSelectTag ? () => onSelectTag(t) : undefined}
                sx={{ mr: 1, mb: 1 }}
              />
            ))
        )}
      </Grid2>
    </Grid2>
  );
}
