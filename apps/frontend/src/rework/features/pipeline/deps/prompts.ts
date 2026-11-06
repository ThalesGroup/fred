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
import { useApiRead, useApiDispatch, type ApiDispatch, type ApiRead } from "./api";

const cp = enhancedControlPlaneApi.endpoints;

export async function countMarketplacePrompts(read: ApiRead, organizationId: string) {
  return (await read(cp.marketplaceEntries, { marketplaceSpaceId: organizationId, kind: "prompt" })).items.length;
}

/** Prompt validation uses the same generated requests and complete catalogs as the product. */
export function createPromptsDeps(
  dispatch: ApiDispatch,
  read: ApiRead,
  resolveSpaceId: PromptsDeps["resolveSpaceId"],
): PromptsDeps {
  return {
    resolveSpaceId,
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
  };
}

export function usePromptsDeps(spaceId: string | undefined): PromptsDeps {
  const dispatch = useApiDispatch();
  const read = useApiRead(dispatch);
  return useMemo(
    () => ({
      ...createPromptsDeps(dispatch, read, async () => {
        if (!spaceId) throw new Error("Select a Weaver space in the Prompts section before running this scenario");
        const spaces = await read(cp.mySpaces, undefined);
        if (!spaces.some((space) => space.id === spaceId))
          throw new Error("Selected prompt scenario space is no longer available; select a Weaver space again");
        return spaceId;
      }),
      marketplaceCount: async (spaceId: string) => {
        const spaces = await read(cp.mySpaces, undefined);
        const organizationId = spaces.find((space) => space.id === spaceId)?.organization_id;
        if (!organizationId) throw new Error("Prompt marketplace organization unavailable");
        return countMarketplacePrompts(read, organizationId);
      },
    }),
    [spaceId, dispatch, read],
  );
}
