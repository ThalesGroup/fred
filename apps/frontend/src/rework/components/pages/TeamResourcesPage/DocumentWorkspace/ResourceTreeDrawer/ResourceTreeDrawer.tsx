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

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { OptionModel } from "@models/Option.model.ts";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { documentDisplayName } from "@shared/molecules/DocumentNameCell/documentNaming.ts";
import { fileIconSpec, FOLDER_ICON } from "../../../../../utils/fileIconSpec.ts";
import type { TagNode } from "../../../../../../shared/utils/tagTree.ts";
import type { DocumentMetadata } from "../../../../../../slices/legacyKnowledgeFlow/knowledgeFlowOpenApi.ts";
import styles from "./ResourceTreeDrawer.module.css";

const TREE_PAGE_SIZE = 50;
const TREE_INDENT = 8;

type Page = { documents: DocumentMetadata[]; total: number; loading: boolean; error: boolean };
type SharedPage = { docs: DocumentMetadata[]; total: number; offset: number; loaded: boolean; loading: boolean };
type DocumentPatch = { retrievable?: boolean; labels?: string[] };
export type TreeAction = "rename" | "download" | "searchable" | "relaunch" | "delete" | "labels";
type MenuTarget = { kind: "folder"; node: TagNode } | { kind: "document"; doc: DocumentMetadata; tagId: string };

export interface ResourceTreeDrawerProps {
  root: TagNode;
  rootLabel: string;
  rootFull: string | null;
  refreshVersion: number;
  sharedPages: Record<string, SharedPage>;
  documentPatches: Record<string, DocumentPatch>;
  reuseSharedPages: boolean;
  currentTagId: string | null;
  currentFull: string | null;
  onNavigate: (full: string | null) => void;
  onPreview: (doc: DocumentMetadata) => void;
  folderOptions: (node: TagNode) => OptionModel<TreeAction>[];
  fileOptions: (doc: DocumentMetadata) => OptionModel<TreeAction>[];
  getFolderDropProps: (node: TagNode) => React.HTMLAttributes<HTMLDivElement>;
  onFolderAction: (node: TagNode, action: TreeAction) => void;
  onFileAction: (doc: DocumentMetadata, tagId: string, action: TreeAction) => void;
  browseDocuments: (
    tagId: string,
    offset: number,
    limit: number,
  ) => Promise<{
    documents?: DocumentMetadata[];
    total?: number;
  }>;
}

/** A folder tree with bounded, on-demand document pages beside the main table. */
export default function ResourceTreeDrawer({
  root,
  rootLabel,
  rootFull,
  refreshVersion,
  sharedPages,
  documentPatches,
  reuseSharedPages,
  currentTagId,
  currentFull,
  onNavigate,
  onPreview,
  folderOptions,
  fileOptions,
  getFolderDropProps,
  onFolderAction,
  onFileAction,
  browseDocuments,
}: ResourceTreeDrawerProps) {
  const { t } = useTranslation();
  const [panelOpen, setPanelOpen] = useState(true);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set([root.full]));
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; target: MenuTarget } | null>(null);
  const contextRef = useRef<HTMLDivElement>(null);
  const contextTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [pages, setPages] = useState<Record<string, Page>>({});
  const requestIds = useRef(new Map<string, number>());
  const sharedPagesRef = useRef(sharedPages);
  sharedPagesRef.current = sharedPages;
  const requestGeneration = useRef(0);

  // A new tag snapshot can add or remove documents. Keep expansion, but discard
  // pages from the old snapshot so open folders fetch their current contents.
  useEffect(() => {
    requestGeneration.current += 1;
    setPages({});
  }, [refreshVersion, rootFull]);

  useEffect(() => {
    const full = currentFull ?? rootFull ?? "";
    const ancestors = full.split("/").filter(Boolean).slice(0, -1);
    setExpanded((previous) => {
      const next = new Set(previous);
      next.add(root.full);
      let path = "";
      for (const part of ancestors) {
        path = path ? `${path}/${part}` : part;
        next.add(path);
      }
      return next;
    });
  }, [currentFull, rootFull, root.full]);

  const loadPage = useCallback(
    async (tagId: string, offset: number) => {
      const generation = requestGeneration.current;
      const requestId = (requestIds.current.get(tagId) ?? 0) + 1;
      requestIds.current.set(tagId, requestId);
      setPages((previous) => ({
        ...previous,
        [tagId]: {
          documents: offset ? (previous[tagId]?.documents ?? sharedPagesRef.current[tagId]?.docs ?? []) : [],
          total: previous[tagId]?.total ?? sharedPagesRef.current[tagId]?.total ?? 0,
          loading: true,
          error: false,
        },
      }));
      try {
        const result = await browseDocuments(tagId, offset, TREE_PAGE_SIZE);
        if (requestGeneration.current !== generation || requestIds.current.get(tagId) !== requestId) return;
        setPages((previous) => ({
          ...previous,
          [tagId]: {
            documents: offset
              ? [
                  ...(previous[tagId]?.documents ?? sharedPagesRef.current[tagId]?.docs ?? []),
                  ...(result.documents ?? []),
                ]
              : (result.documents ?? []),
            total: result.total ?? 0,
            loading: false,
            error: false,
          },
        }));
      } catch {
        if (requestGeneration.current !== generation || requestIds.current.get(tagId) !== requestId) return;
        setPages((previous) => ({
          ...previous,
          [tagId]: { ...(previous[tagId] ?? { documents: [], total: 0 }), loading: false, error: true },
        }));
      }
    },
    [browseDocuments],
  );

  const openTagIds = useMemo(() => {
    if (!panelOpen) return [];
    const ids: string[] = [];
    const visit = (node: TagNode) => {
      if (!expanded.has(node.full)) return;
      const tagId = node.tagsHere[0]?.id;
      if (tagId) ids.push(tagId);
      node.children.forEach(visit);
    };
    visit(root);
    return ids;
  }, [panelOpen, expanded, root]);
  useEffect(() => {
    for (const tagId of openTagIds) {
      if (pages[tagId]) continue;
      // After a tag refresh, pages cached for other folders can describe the old snapshot.
      const canReuseShared = reuseSharedPages && (refreshVersion === 0 || tagId === currentTagId);
      if (canReuseShared) {
        const shared = sharedPages[tagId];
        if (shared?.offset === 0 && (shared.loaded || shared.loading)) continue;
        if (tagId === currentTagId) continue;
      }
      void loadPage(tagId, 0);
    }
  }, [openTagIds, pages, loadPage, sharedPages, reuseSharedPages, currentTagId, refreshVersion]);

  const contextOptions = contextMenu
    ? contextMenu.target.kind === "folder"
      ? folderOptions(contextMenu.target.node)
      : fileOptions(contextMenu.target.doc)
    : [];

  useEffect(() => {
    if (!contextMenu) return;
    contextRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    const dismiss = (event: PointerEvent) => {
      if (!contextRef.current?.contains(event.target as Node)) setContextMenu(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      contextTriggerRef.current?.focus();
      setContextMenu(null);
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
    };
  }, [contextMenu]);

  const showContext = (event: React.MouseEvent, target: MenuTarget) => {
    const options = target.kind === "folder" ? folderOptions(target.node) : fileOptions(target.doc);
    if (options.length === 0) return;
    event.preventDefault();
    contextTriggerRef.current =
      (event.target as Element).closest<HTMLButtonElement>("button") ??
      event.currentTarget.querySelector<HTMLButtonElement>("button[title]");
    setContextMenu({ x: event.clientX, y: event.clientY, target });
  };

  const chooseContext = (action: TreeAction) => {
    if (!contextMenu) return;
    contextTriggerRef.current?.focus();
    if (contextMenu.target.kind === "folder") onFolderAction(contextMenu.target.node, action);
    else onFileAction(contextMenu.target.doc, contextMenu.target.tagId, action);
    setContextMenu(null);
  };

  const toggle = (full: string) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(full)) next.delete(full);
      else next.add(full);
      return next;
    });
  };

  const renderNode = (node: TagNode, depth: number, label = node.name): ReactNode => {
    const isExpanded = expanded.has(node.full);
    const isCurrent = (currentFull ?? rootFull ?? "") === node.full;
    const tagId = node.tagsHere[0]?.id;
    const shared =
      tagId && reuseSharedPages && (refreshVersion === 0 || tagId === currentTagId) ? sharedPages[tagId] : undefined;
    const page =
      tagId && pages[tagId]
        ? pages[tagId]
        : shared && shared.offset === 0 && shared.loaded
          ? { documents: shared.docs, total: shared.total, loading: shared.loading, error: false }
          : undefined;
    const children = [...node.children.values()].sort((a, b) => a.name.localeCompare(b.name));
    return (
      <li key={node.full || "root"}>
        <div
          className={`${styles.row} ${isCurrent ? styles.current : ""}`}
          style={{ paddingLeft: `${depth * TREE_INDENT + 4}px` }}
          onContextMenu={(event) => showContext(event, { kind: "folder", node })}
          {...getFolderDropProps(node)}
        >
          <IconButton
            variant="icon"
            size="2xs"
            icon={{ category: "outlined", type: isExpanded ? "expand_more" : "chevron_right" }}
            aria-label={t(isExpanded ? "rework.resources.tree.collapse" : "rework.resources.tree.expand", {
              name: label,
            })}
            aria-expanded={isExpanded}
            onClick={(event) => {
              if (event.detail <= 1) toggle(node.full);
            }}
          />
          <button
            type="button"
            className={styles.name}
            title={label}
            aria-current={isCurrent ? "page" : undefined}
            onClick={(event) => {
              if (event.detail <= 1 && !isCurrent) onNavigate(node.full === root.full ? rootFull : node.full);
            }}
            onDoubleClick={() => toggle(node.full)}
          >
            <span className={styles.icon} style={{ color: FOLDER_ICON.color }}>
              <Icon category="outlined" type={FOLDER_ICON.type} filled={FOLDER_ICON.filled} />
            </span>
            <span className={styles.label}>{label}</span>
          </button>
        </div>
        {isExpanded && (
          <ul className={styles.list}>
            {children.map((child) => renderNode(child, depth + 1))}
            {page?.documents.map((doc) => {
              const uid = doc.identity.document_uid;
              const patch = documentPatches[uid];
              const currentDoc = patch
                ? {
                    ...doc,
                    source: {
                      ...doc.source,
                      ...(patch.retrievable !== undefined && { retrievable: patch.retrievable }),
                    },
                    labels: patch.labels ?? doc.labels,
                  }
                : doc;
              const name = documentDisplayName(currentDoc);
              const icon = fileIconSpec(currentDoc.file?.file_type);
              return (
                <li key={uid}>
                  <button
                    type="button"
                    className={`${styles.file} ${selectedFile === uid ? styles.selectedFile : ""}`}
                    style={{ paddingLeft: `${(depth + 1) * TREE_INDENT + 28}px` }}
                    title={name}
                    onClick={() => setSelectedFile(uid)}
                    onDoubleClick={() => onPreview(currentDoc)}
                    onContextMenu={(event) => {
                      setSelectedFile(uid);
                      showContext(event, { kind: "document", doc: currentDoc, tagId: tagId! });
                    }}
                  >
                    <span className={styles.icon} style={{ color: icon.color }}>
                      <Icon category="outlined" type={icon.type} filled={icon.filled} />
                    </span>
                    <span className={styles.label}>{name}</span>
                  </button>
                </li>
              );
            })}
            {page?.error && (
              <li>
                <button
                  type="button"
                  className={styles.more}
                  onClick={() => void loadPage(tagId!, page.documents.length)}
                >
                  {t("rework.resources.tree.retry")}
                </button>
              </li>
            )}
            {page && !page.error && page.documents.length < page.total && (
              <li>
                <button
                  type="button"
                  className={styles.more}
                  disabled={page.loading}
                  onClick={() => void loadPage(tagId!, page.documents.length)}
                >
                  {t("rework.resources.tree.loadMore")}
                </button>
              </li>
            )}
          </ul>
        )}
      </li>
    );
  };

  return (
    <InlineDrawer
      open={panelOpen}
      onOpen={() => setPanelOpen(true)}
      onClose={() => setPanelOpen(false)}
      layout="rail"
      title={t("rework.resources.tree.title")}
      railIcon={{ category: "outlined", type: "folder" }}
      railExpandLabel={t("rework.resources.tree.openPanel")}
      railCollapseLabel={t("rework.resources.tree.closePanel")}
      resizeLabel={t("rework.resources.tree.resize")}
      resizable={{ persistKey: "team-resources:tree", minWidth: 180, maxWidth: 420, maxViewportFraction: 0.35 }}
      width="260px"
      background="var(--surface-container)"
      flushBody
    >
      {panelOpen && (
        <nav className={styles.tree} aria-label={t("rework.resources.tree.title")}>
          <ul className={styles.list}>{renderNode(root, 0, rootLabel)}</ul>
        </nav>
      )}
      {contextMenu &&
        createPortal(
          <div
            ref={contextRef}
            className={styles.contextMenu}
            role="menu"
            aria-label={
              contextMenu.target.kind === "folder"
                ? contextMenu.target.node.name
                : documentDisplayName(contextMenu.target.doc)
            }
            style={{
              left: Math.max(0, Math.min(contextMenu.x, window.innerWidth - 240)),
              top: Math.max(0, Math.min(contextMenu.y, window.innerHeight - contextOptions.length * 36 - 8)),
            }}
            onKeyDown={(event) => {
              if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
              event.preventDefault();
              const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
              const current = items.indexOf(document.activeElement as HTMLButtonElement);
              const direction = event.key === "ArrowDown" ? 1 : -1;
              items[(current + direction + items.length) % items.length]?.focus();
            }}
          >
            {contextOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                role="menuitem"
                className={styles.contextAction}
                data-destructive={option.destructive || undefined}
                disabled={option.disabled}
                title={option.tooltip}
                onClick={() => chooseContext(option.value)}
              >
                {option.icon && <Icon {...option.icon} />}
                <span>{option.label}</span>
              </button>
            ))}
          </div>,
          document.body,
        )}
    </InlineDrawer>
  );
}
