// useResourceCommands.ts
// Copyright Thales 2025

import { useCallback } from "react";
import {
  Resource,
  ResourceKind,
  TagWithItemsId,
  useCreateResourceKnowledgeFlowV1ResourcesPostMutation,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
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

export function useResourceCommands(
  kind: ResourceKind,
  { refetchTags, refetchResources }: ResourceRefresher = {},
) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();

  const [createResourceMutation] = useCreateResourceKnowledgeFlowV1ResourcesPostMutation();
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
            kind, // <-- injected from the view (prompt | template)
            content: payload.content,
            name: payload.name,
            description: payload.description,
            labels: payload.labels,
          },
        }).unwrap();

        await refresh();
        showSuccess?.({
          summary: t("resourceLibrary.createSuccess") || "Created",
          detail:
            t("resourceLibrary.createDetail", { typeOne: kind }) ||
            "Resource added to the library.",
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

  /**
   * Remove a resource from ONE library.
   * NOTE: This currently updates the Tag (removes the resource id from tag.item_ids),
   * which matches your current UI. When you migrate membership off tags, switch this
   * to an `updateResource` call that clears/changes the resource’s library.
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
          detail:
            t("resourceLibrary.removeDetail", { typeOne: kind }) ||
            "Resource removed from the library.",
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

  return { createResource, removeFromLibrary };
}
