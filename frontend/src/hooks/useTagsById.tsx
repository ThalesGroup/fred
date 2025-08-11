// src/components/documents/hooks/useTagsById.ts
import * as React from "react";
import { TagType, TagWithItemsId, useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export function useTagsById(tagIds: string[] | undefined) {
  const [getTag] = useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery();
  const [cache, setCache] = React.useState<Record<string, TagWithItemsId>>({});

  React.useEffect(() => {
    if (!tagIds || tagIds.length === 0) return;

    const missing = tagIds.filter((id) => !cache[id]);
    if (missing.length === 0) return;

    let cancelled = false;
    (async () => {
      const updates: Record<string, TagWithItemsId> = {};
      await Promise.all(
        missing.map(async (id) => {
          try {
            const tag = await getTag({ tagId: id }).unwrap();
            updates[id] = tag;
          } catch {
            // fallback ghost tag
            updates[id] = {
              id,
              name: id,
              description: null,
              created_at: "",
              updated_at: "",
              owner_id: "",
              type: "document" as TagType,
              item_ids: [],
            };
          }
        }),
      );
      if (!cancelled) setCache((prev) => ({ ...prev, ...updates }));
    })();

    return () => {
      cancelled = true;
    };
  }, [tagIds, getTag]); // do not include cache in deps

  return cache;
}
