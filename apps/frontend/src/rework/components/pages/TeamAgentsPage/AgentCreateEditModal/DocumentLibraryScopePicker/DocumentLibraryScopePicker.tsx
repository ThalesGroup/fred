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

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap";
import { buildTree, type TagNode } from "../../../../../../shared/utils/tagTree";
import type { DocumentMetadata } from "../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  TagType,
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./DocumentLibraryScopePicker.module.css";

interface DocumentLibraryScopePickerProps {
  teamId?: string;
  selectedTagIds: string[];
  onChange: (tagIds: string[]) => void;
  selectedDocumentUids?: string[];
  onDocumentsChange?: (documentUids: string[]) => void;
  disableLibrarySelection?: boolean;
}

function findPrimaryTagId(node: TagNode): string | null {
  return node.tagsHere?.[0]?.id ?? null;
}

function collectTagIds(node: TagNode): string[] {
  const ids = new Set<string>();
  const walk = (current: TagNode) => {
    current.tagsHere?.forEach((tag) => ids.add(tag.id));
    current.children.forEach((child) => walk(child));
  };
  walk(node);
  return Array.from(ids);
}

export function DocumentLibraryScopePicker({
  teamId,
  selectedTagIds,
  onChange,
  selectedDocumentUids,
  onDocumentsChange,
  disableLibrarySelection = false,
}: DocumentLibraryScopePickerProps) {
  const { t } = useTranslation();
  const { activeTeam } = useFrontendBootstrap();
  const isPersonalTeam = !teamId || teamId === activeTeam?.id;
  const [expanded, setExpanded] = useState<string[]>([]);
  const [documentsByTagId, setDocumentsByTagId] = useState<Record<string, DocumentMetadata[]>>({});
  const [loadingTagIds, setLoadingTagIds] = useState<Record<string, boolean>>({});

  const { data: allTags = [], isLoading } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document" as TagType,
    limit: 10000,
    offset: 0,
    ownerFilter: isPersonalTeam ? "personal" : "team",
    teamId: isPersonalTeam ? undefined : teamId,
  });
  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const documentSelectionEnabled = Array.isArray(selectedDocumentUids) && typeof onDocumentsChange === "function";

  const tree = useMemo(() => buildTree(allTags), [allTags]);

  const setTagLoading = useCallback((tagId: string, loading: boolean) => {
    setLoadingTagIds((prev) => {
      const next = { ...prev };
      if (loading) next[tagId] = true;
      else delete next[tagId];
      return next;
    });
  }, []);

  const loadDocumentsForTag = useCallback(
    async (tagId: string) => {
      if (documentsByTagId[tagId] || loadingTagIds[tagId]) return;
      setTagLoading(tagId, true);
      try {
        const response = await browseDocumentsByTag({
          browseDocumentsByTagRequest: {
            tag_id: tagId,
            offset: 0,
            limit: 20,
          },
        }).unwrap();
        setDocumentsByTagId((prev) => ({ ...prev, [tagId]: response.documents ?? [] }));
      } finally {
        setTagLoading(tagId, false);
      }
    },
    [browseDocumentsByTag, documentsByTagId, loadingTagIds, setTagLoading],
  );

  useEffect(() => {
    expanded.forEach((path) => {
      const node = path
        .split("/")
        .filter(Boolean)
        .reduce<TagNode | null>((current, segment) => current?.children.get(segment) ?? null, tree);
      const tagId = node ? findPrimaryTagId(node) : null;
      if (tagId) void loadDocumentsForTag(tagId);
    });
  }, [expanded, loadDocumentsForTag, tree]);

  const toggleExpand = (path: string) => {
    setExpanded((prev) => (prev.includes(path) ? prev.filter((item) => item !== path) : [...prev, path]));
  };

  const toggleNodeSelection = (node: TagNode) => {
    if (disableLibrarySelection) return;
    const tagIds = collectTagIds(node);
    const allSelected = tagIds.every((id) => selectedTagIds.includes(id));
    if (allSelected) {
      onChange(selectedTagIds.filter((id) => !tagIds.includes(id)));
      return;
    }
    onChange(Array.from(new Set([...selectedTagIds, ...tagIds])));
  };

  const toggleDocumentSelection = (documentUid: string, tagId: string | null, checked: boolean) => {
    if (!documentSelectionEnabled || !selectedDocumentUids || !onDocumentsChange) return;
    if (checked) {
      onDocumentsChange(Array.from(new Set([...selectedDocumentUids, documentUid])));
      return;
    }
    onDocumentsChange(selectedDocumentUids.filter((uid) => uid !== documentUid));
  };

  const renderNode = (node: TagNode): ReactNode[] =>
    Array.from(node.children.values())
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((child) => {
        const childTagIds = collectTagIds(child);
        const selectedCount = childTagIds.filter((id) => selectedTagIds.includes(id)).length;
        const isChecked = childTagIds.length > 0 && selectedCount === childTagIds.length;
        const isIndeterminate = selectedCount > 0 && selectedCount < childTagIds.length;
        const isExpanded = expanded.includes(child.full);
        const tagId = findPrimaryTagId(child);
        const docs = tagId ? (documentsByTagId[tagId] ?? []) : [];
        const isLoadingDocs = tagId ? Boolean(loadingTagIds[tagId]) : false;

        return (
          <li key={child.full} className={styles.node}>
            <div className={styles.nodeRow}>
              <button
                type="button"
                className={styles.expandButton}
                onClick={() => toggleExpand(child.full)}
                aria-label={isExpanded ? t("rework.collapse", "Collapse") : t("rework.expand", "Expand")}
              >
                <span className="material-symbols-outlined" aria-hidden>
                  {isExpanded ? "expand_more" : "chevron_right"}
                </span>
              </button>
              <input
                type="checkbox"
                className={styles.checkbox}
                checked={isChecked}
                disabled={disableLibrarySelection}
                ref={(input) => {
                  if (input) input.indeterminate = isIndeterminate;
                }}
                onChange={() => toggleNodeSelection(child)}
              />
              <span className={`${styles.folderIcon} material-symbols-outlined`} aria-hidden>
                {isExpanded ? "folder_open" : "folder"}
              </span>
              <div className={styles.nodeMeta}>
                <span className={styles.nodeLabel}>{child.name}</span>
                <span className={styles.nodeCount}>
                  {child.tagsHere?.[0]?.item_ids?.length ?? docs.length} {t("rework.documents", "documents")}
                </span>
              </div>
            </div>

            {isExpanded && (
              <div className={styles.nodeChildren}>
                {docs.length > 0 && (
                  <ul className={styles.documentList}>
                    {docs.map((doc) => {
                      const documentUid = doc.identity.document_uid;
                      const checked = selectedDocumentUids?.includes(documentUid) ?? false;
                      return (
                        <li key={documentUid} className={styles.documentItem}>
                          {documentSelectionEnabled ? (
                            <label className={styles.documentToggle}>
                              <input
                                type="checkbox"
                                className={styles.checkbox}
                                checked={checked}
                                onChange={(event) => toggleDocumentSelection(documentUid, tagId, event.target.checked)}
                              />
                              <span className={`${styles.documentIcon} material-symbols-outlined`} aria-hidden>
                                description
                              </span>
                              <span className={styles.documentName}>{doc.identity.document_name}</span>
                            </label>
                          ) : (
                            <>
                              <span className={`${styles.documentIcon} material-symbols-outlined`} aria-hidden>
                                description
                              </span>
                              <span className={styles.documentName}>{doc.identity.document_name}</span>
                            </>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {isLoadingDocs && <p className={styles.loadingText}>{t("rework.loading", "Loading...")}</p>}
                {renderNode(child)}
              </div>
            )}
          </li>
        );
      });

  if (isLoading) {
    return <div className={styles.stateText}>{t("rework.loading", "Loading...")}</div>;
  }

  if (tree.children.size === 0) {
    return <div className={styles.stateText}>{t("agentTuning.fields.library_binding.noLibraries")}</div>;
  }

  return <ul className={styles.tree}>{renderNode(tree)}</ul>;
}
