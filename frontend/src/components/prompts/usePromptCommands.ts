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

import { useCallback } from "react";
import {
  Prompt,
  TagWithItemsId,
  useCreatePromptKnowledgeFlowV1PromptsPostMutation,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useSearchPromptsKnowledgeFlowV1PromptsSearchPostMutation,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";
import { useTranslation } from "react-i18next";

type PromptRefreshers = {
  refetchTags?: () => Promise<any>;
  refetchPrompts?: () => Promise<any>;
};

export function usePromptCommands({ refetchTags, refetchPrompts }: PromptRefreshers = {}) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const [] = useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery();

  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();
  const [fetchAllPrompts] = useSearchPromptsKnowledgeFlowV1PromptsSearchPostMutation();
   const [createPromptMutation] = useCreatePromptKnowledgeFlowV1PromptsPostMutation();

  const refresh = useCallback(async () => {
    await Promise.all([refetchTags?.(), refetchPrompts ? refetchPrompts() : fetchAllPrompts({ filters: {} })]);
  }, [refetchTags, refetchPrompts, fetchAllPrompts]);

  // Remove a prompt from ONE library (remove tag id from prompt.tags)
  const removeFromLibrary = useCallback(
    async (prompt: Prompt, tag: TagWithItemsId) => {
      try {
        const newItemIds = (tag.item_ids || []).filter((id) => id !== prompt.id);
        await updateTag({
          tagId: tag.id,
          tagUpdate: {
            name: tag.name,
            description: tag.description,
            type: tag.type,
            item_ids: newItemIds,
          },
        }).unwrap();
        await refresh?.();
        showSuccess?.({
          summary: t("promptLibrary.removeSuccess") || "Removed",
          detail: t("promptLibrary.removedOneDocument") || "Document removed from the library.",
        });
      } catch (e: any) {
        showError?.({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to remove from library.",
        });
      }
    },
    [updateTag, refresh, showSuccess, showError, t],
  );

  const createPrompt = useCallback(
    async (newPrompt: Prompt, targetTagId: string) => {
      try {
        await createPromptMutation({
          prompt: { ...newPrompt, tags: [targetTagId] },
        }).unwrap();
        await refresh();
        showSuccess({
          summary: t("promptLibrary.createSuccess") || "Created",
          detail: t("promptLibrary.promptCreated") || "Prompt added to the library.",
        });
      } catch (e: any) {
        showError({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to create prompt.",
        });
      }
    },
    [createPromptMutation, refresh, showSuccess, showError, t],
  );
  
  return { removeFromLibrary, createPrompt };
}
