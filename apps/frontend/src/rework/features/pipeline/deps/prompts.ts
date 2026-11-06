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
import { controlPlaneApi } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { PromptsDeps } from "../scenarios/promptsScenario";
import type { PipelineDeps } from "../types";
import { FRESH, useApiDispatch } from "./api";

/** Extends the shared base deps, so the page keeps one set of product hooks. */
export function usePromptsDeps(base: PipelineDeps): PromptsDeps {
  const dispatch = useApiDispatch();
  return useMemo(() => {
    const cp = controlPlaneApi.endpoints;
    const teamId = base.teamId;
    const body = (args: { name: string; text: string; categoryId?: string; command?: string }) => ({
      name: args.name,
      text: args.text,
      category_id: args.categoryId ?? null,
      command: args.command ?? null,
    });
    return {
      ...base,
      createPrompt: async (args) =>
        (
          await dispatch(
            cp.postTeamPromptControlPlaneV1TeamsTeamIdPromptsPost.initiate({ teamId, createPromptRequest: body(args) }),
          ).unwrap()
        ).id,
      updatePrompt: async (promptId, args) => {
        await dispatch(
          cp.putTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPut.initiate({
            teamId,
            promptId,
            updatePromptRequest: body(args),
          }),
        ).unwrap();
      },
      readPrompt: async (promptId) => {
        const prompt = await dispatch(
          cp.getTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGet.initiate({ teamId, promptId }, FRESH),
        ).unwrap();
        return { text: prompt.text, categoryId: prompt.category_id ?? null, favorite: prompt.is_favorite ?? false };
      },
      setFavorite: async (promptId, favorite) => {
        const endpoint = favorite
          ? cp.addTeamPromptFavoriteControlPlaneV1TeamsTeamIdPromptsPromptIdFavoritePut
          : cp.removeTeamPromptFavoriteControlPlaneV1TeamsTeamIdPromptsPromptIdFavoriteDelete;
        await dispatch(endpoint.initiate({ teamId, promptId })).unwrap();
      },
      listFavorites: async () =>
        (await dispatch(cp.getTeamPromptsControlPlaneV1TeamsTeamIdPromptsGet.initiate({ teamId }, FRESH)).unwrap())
          .filter((p) => p.is_favorite)
          .map((p) => p.id),
      listCommands: async () =>
        (
          await dispatch(
            cp.getTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGet.initiate({ teamId }, FRESH),
          ).unwrap()
        ).map((c) => ({ promptId: c.prompt_id, command: c.command })),
      createCategory: async (name) =>
        (
          await dispatch(
            cp.postTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPost.initiate({
              teamId,
              createPromptCategoryRequest: { name },
            }),
          ).unwrap()
        ).id,
      renameCategory: async (categoryId, name) => {
        await dispatch(
          cp.putTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPut.initiate({
            teamId,
            categoryId,
            updatePromptCategoryRequest: { name },
          }),
        ).unwrap();
      },
      listCategories: async () =>
        (
          await dispatch(
            cp.getTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGet.initiate({ teamId }, FRESH),
          ).unwrap()
        ).map((c) => ({ id: c.id, name: c.name })),
      deleteCategory: async (categoryId) => {
        await dispatch(
          cp.deleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDelete.initiate({
            teamId,
            categoryId,
          }),
        ).unwrap();
      },
      marketplaceCount: async () =>
        (
          await dispatch(
            cp.getMarketplacePromptsControlPlaneV1MarketplacePromptsGet.initiate(undefined, FRESH),
          ).unwrap()
        ).length,
    };
  }, [base, dispatch]);
}
