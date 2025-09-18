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
