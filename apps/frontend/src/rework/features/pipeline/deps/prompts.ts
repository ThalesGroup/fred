// Copyright Thales 2026
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

import { useMemo } from "react";
import { enhancedControlPlaneApi } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PromptsDeps } from "../scenarios/promptsScenario";
import { useApiRead, useApiDispatch } from "./api";

/** Prompt validation uses the same generated requests and complete catalogs as the product. */
export function usePromptsDeps(spaceId: string | undefined): PromptsDeps {
  const dispatch = useApiDispatch();
  const read = useApiRead();
  return useMemo(() => {
    const cp = enhancedControlPlaneApi.endpoints;
    return {
      resolveSpaceId: async () => {
        if (!spaceId) throw new Error("Select a Weaver space in the Prompts section before running this scenario");
        const spaces = await read(cp.mySpaces, undefined);
        if (!spaces.some((space) => space.id === spaceId))
          throw new Error("Selected prompt scenario space is no longer available; select a Weaver space again");
        return spaceId;
      },
      createPrompt: (args) => dispatch(cp.createPrompt.initiate(args)).unwrap(),
      updatePrompt: (args) => dispatch(cp.updatePrompt.initiate(args)).unwrap(),
      readPrompt: (args) => read(cp.getPrompt, args),
      deletePrompt: async (args) => {
        await dispatch(cp.deletePrompt.initiate(args)).unwrap();
      },
      listPrompts: async (spaceId) => (await read(cp.listPrompts, { spaceId })).items,
      setFavorite: async (spaceId, promptId, favorite) => {
        const endpoint = favorite ? cp.addPromptFavorite : cp.removePromptFavorite;
        await dispatch(endpoint.initiate({ spaceId, promptId })).unwrap();
      },
      createCategory: (args) => dispatch(cp.createPromptCategory.initiate(args)).unwrap(),
      renameCategory: (args) => dispatch(cp.renamePromptCategory.initiate(args)).unwrap(),
      listCategories: async (spaceId) => (await read(cp.listPromptCategories, { spaceId })).items,
      deleteCategory: async (args) => {
        await dispatch(cp.deletePromptCategory.initiate(args)).unwrap();
      },
      marketplaceCount: async (spaceId) => {
        const spaces = await read(cp.mySpaces, undefined);
        const organizationId = spaces.find((space) => space.id === spaceId)?.organization_id;
        if (!organizationId) throw new Error("Prompt marketplace organization unavailable");
        return (await read(cp.publishedPrompts, { marketplaceSpaceId: organizationId })).items.length;
      },
    };
  }, [spaceId, dispatch, read]);
}
