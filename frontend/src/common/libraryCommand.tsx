// Copyright Thales 2025
import { useCallback } from "react";
import { TagNode } from "../components/tags/tagTree";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";
import { useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useTranslation } from "react-i18next";

export type ItemWithTags = { tags?: string[] | null };

function collectTaggedNodes(root: TagNode): TagNode[] {
  const out: TagNode[] = [];
  const dfs = (n: TagNode) => {
    if (n.tagsHere?.[0]) out.push(n);
    for (const ch of n.children.values()) dfs(ch);
  };
  dfs(root);
  return out;
}
const depthOf = (full: string) => (full ? full.split("/").length : 0);

type UseCascadeDeleteParams<T extends ItemWithTags> = {
  allItems: T[];
  getTags?: (item: T) => string[];

  selectedFolder?: string;
  setSelectedFolder: (full: string | undefined) => void;
  expanded: string[];
  setExpanded: (ids: string[]) => void;

  refetchTags: () => Promise<any> | any;
  refetchItems: () => Promise<any> | any;

  /** i18n key suffix for the item label: "documentLabel" | "promptLabel" */
  itemKey: "documentLabel" | "promptLabel";
};

export function useCascadeDeleteLibrary<T extends ItemWithTags>({
  allItems,
  getTags = (i: T) => (i.tags ?? []) as string[],
  selectedFolder,
  setSelectedFolder,
  expanded,
  setExpanded,
  refetchTags,
  refetchItems,
  itemKey,
}: UseCascadeDeleteParams<T>) {
  const { t } = useTranslation();
  const itemLabel = t(`common.${itemKey}`); // <- now defined
  const { showConfirmationDialog } = useConfirmationDialog();
  const [deleteTag] = useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation();

  const handleDeleteFolder = useCallback(
    (node: TagNode) => {
      const nodesToDelete = collectTaggedNodes(node);
      if (nodesToDelete.length === 0) return;

      const tagIdsToDelete = new Set(nodesToDelete.map((n) => n.tagsHere![0].id));

      const touchedCount = allItems.filter((it) => getTags(it).some((id) => tagIdsToDelete.has(id))).length;
      const orphanedCount = allItems.filter((it) => {
        const tags = getTags(it);
        return tags.length > 0 && tags.every((id) => tagIdsToDelete.has(id));
      }).length;

      const libCount = nodesToDelete.length;
      showConfirmationDialog({
        title: t("libraryDelete.title", { full: node.full }),
        message: t("libraryDelete.message", {
          libCount,
          touchedCount,
          orphanedCount,
          itemLabel,
        }),
        onConfirm: async () => {
          const ordered = [...nodesToDelete].sort((a, b) => depthOf(b.full) - depthOf(a.full));
          for (const n of ordered) {
            const tagId = n.tagsHere![0].id;
            await deleteTag({ tagId }).unwrap();
          }

          if (selectedFolder && (selectedFolder === node.full || selectedFolder.startsWith(node.full + "/"))) {
            setSelectedFolder(undefined);
          }
          setExpanded(expanded.filter((id) => !id.startsWith(node.full)));

          await refetchTags();
          await refetchItems();
        },
      });
    },
    [
      allItems,
      getTags,
      deleteTag,
      expanded,
      setExpanded,
      selectedFolder,
      setSelectedFolder,
      refetchTags,
      refetchItems,
      itemLabel,
      t,
    ],
  );

  return { handleDeleteFolder };
}
