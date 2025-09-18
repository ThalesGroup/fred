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
  Resource,
  ResourceKind,
  TagWithItemsId,
  useCreateResourceKnowledgeFlowV1ResourcesPostMutation,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useUpdateResourceKnowledgeFlowV1ResourcesResourceIdPutMutation,
  useLazyGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";
import { useTranslation } from "react-i18next";

type ResourceRefresher = {
  refetchTags?: () => Promise<any> | void;
  refetchResources?: () => Promise<any> | void;
};

/** Payload shape produced by both modals (Prompt & Template) */
type CreateInput = {
  content: string;
  name?: string;
  description?: string;
  labels?: string[];
};

/** Editable fields for update */
type UpdateInput = {
  content?: string;
  name?: string;
  description?: string;
  labels?: string[];
};

export function useResourceCommands(kind: ResourceKind, { refetchTags, refetchResources }: ResourceRefresher = {}) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();

  const [createResourceMutation] = useCreateResourceKnowledgeFlowV1ResourcesPostMutation();
  const [updateResourceMutation] = useUpdateResourceKnowledgeFlowV1ResourcesResourceIdPutMutation();
  const [triggerGetResource] = useLazyGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery();
  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();

  const refresh = useCallback(async () => {
    await Promise.all([refetchTags?.(), refetchResources?.()]);
  }, [refetchTags, refetchResources]);

  /** Create resource in the selected library. `kind` is injected here. */
  const createResource = useCallback(
    async (payload: CreateInput, targetTagId: string) => {
      try {
        await createResourceMutation({
          libraryTagId: targetTagId,
          resourceCreate: {
            kind, // injected (prompt | template)
            content: payload.content,
            name: payload.name,
            description: payload.description,
            labels: payload.labels,
          },
        }).unwrap();

        await refresh();
        showSuccess?.({
          summary: t("resourceLibrary.createSuccess") || "Created",
          detail: t("resourceLibrary.createDetail", { typeOne: kind }) || "Resource added to the library.",
        });
      } catch (e: any) {
        showError?.({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to create resource.",
        });
      }
    },
    [createResourceMutation, refresh, showSuccess, showError, t, kind],
  );

  /** Update resource fields (content/name/description/labels). */
  const updateResource = useCallback(
    async (resourceId: string, patch: UpdateInput) => {
      try {
        await updateResourceMutation({
          resourceId,
          resourceUpdate: {
            content: patch.content,
            name: patch.name,
            description: patch.description,
            labels: patch.labels,
          },
        }).unwrap();

        await refresh();
        showSuccess?.({
          summary: t("resourceLibrary.updateSuccess") || "Updated",
          detail: t("resourceLibrary.updateDetail", { typeOne: kind }) || "Resource updated.",
        });
      } catch (e: any) {
        showError?.({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to update resource.",
        });
      }
    },
    [updateResourceMutation, refresh, showSuccess, showError, t, kind],
  );

  /**
   * Optional fetch to support preview (or to re-fetch before editing).
   * If you’re already passing the full resource down, you don’t need this.
   */
  const getResource = useCallback(
    async (resourceId: string) => {
      try {
        const res = await triggerGetResource({ resourceId }).unwrap();
        return res;
      } catch (e: any) {
        showError?.({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to fetch resource.",
        });
        throw e;
      }
    },
    [triggerGetResource, showError, t],
  );

  /**
   * Remove a resource from ONE library (current tag system).
   * When you migrate membership off tags, replace with a resource update.
   */
  const removeFromLibrary = useCallback(
    async (resource: Resource, tag: TagWithItemsId) => {
      try {
        const newItemIds = (tag.item_ids || []).filter((id) => id !== resource.id);
        await updateTag({
          tagId: tag.id,
          tagUpdate: {
            name: tag.name,
            description: tag.description,
            type: tag.type,
            item_ids: newItemIds,
          },
        }).unwrap();

        await refresh();
        showSuccess?.({
          summary: t("resourceLibrary.removeSuccess") || "Removed",
          detail: t("resourceLibrary.removeDetail", { typeOne: kind }) || "Resource removed from the library.",
        });
      } catch (e: any) {
        showError?.({
          summary: t("validation.error") || "Error",
          detail: e?.data?.detail || e?.message || "Failed to remove from library.",
        });
      }
    },
    [updateTag, refresh, showSuccess, showError, t, kind],
  );

  return { createResource, updateResource, getResource, removeFromLibrary };
}
