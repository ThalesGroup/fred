// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import Checkbox from "@shared/atoms/Checkbox/Checkbox.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { FOLDER_ICON, fileIconSpec } from "../../../../utils/fileIconSpec.ts";
import Select from "@shared/molecules/Select/Select";
import { useLazyEntriesQuery, useMySpacesQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Directory, Entry, Folder } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { DocumentLibrarySelection } from "./documentLibrarySelection";
import styles from "./DocumentLibraryScopePicker.module.css";

interface DocumentLibraryScopePickerProps {
  /** Canonical Weaver space id, never the personal/team URL alias. */
  spaceId: string;
  value: DocumentLibrarySelection;
  /** Folder and document changes are committed together, including exclusions. */
  onChange: (value: DocumentLibrarySelection) => void;
  disabled?: boolean;
  disableLibrarySelection?: boolean;
  showDocuments?: boolean;
  /** Hide documents; the directory endpoint still returns mixed entries. */
  foldersOnly?: boolean;
}

const ROOT = "";
const PAGE_SIZE = 100;

export function DocumentLibraryScopePicker(props: DocumentLibraryScopePickerProps) {
  // Discard navigation and in-flight selection work on a space change.
  return <ScopePicker key={props.spaceId} {...props} />;
}

function ScopePicker(props: DocumentLibraryScopePickerProps) {
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const [browsedSpaceId, setBrowsedSpaceId] = useState(props.spaceId);
  const owner = context.currentData?.find((space) => space.id === props.spaceId);
  const spaces = owner?.path.flatMap((id) => context.currentData?.find((space) => space.id === id) ?? []) ?? [];
  const browsedSpace = spaces.find((space) => space.id === browsedSpaceId);
  if (context.isError || (!context.isFetching && !owner)) {
    return (
      <p role="alert" className={styles.stateText}>
        {t("rework.weaverAgents.scopeUnavailable")}
      </p>
    );
  }
  if (!owner)
    return (
      <p role="status" className={styles.stateText}>
        {t("rework.loading")}
      </p>
    );
  return (
    <div className={styles.tree}>
      {spaces.length > 1 && (
        <Select
          size="small"
          compact
          label={t("chatbot.documentScopePanel.space")}
          value={browsedSpace?.id ?? props.spaceId}
          options={spaces.map((space) => ({ key: space.id, value: space.id, label: space.name }))}
          onChange={setBrowsedSpaceId}
        />
      )}
      <SpacePicker key={browsedSpace?.id ?? props.spaceId} {...props} spaceId={browsedSpace?.id ?? props.spaceId} />
    </div>
  );
}

function SpacePicker({
  spaceId,
  value,
  onChange,
  disabled = false,
  disableLibrarySelection = false,
  showDocuments = true,
  foldersOnly = false,
}: DocumentLibraryScopePickerProps) {
  const { t } = useTranslation();
  const [browse] = useLazyEntriesQuery();
  const [directories, setDirectories] = useState<Record<string, Directory>>({});
  const [expanded, setExpanded] = useState<string[]>([]);
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [selectionError, setSelectionError] = useState(false);
  const mounted = useRef(true);
  // Scope ids are sets: new objects, ordering and duplicate ids do not change
  // the selection. Track committed transitions as well as the current value so
  // changing A -> B -> A (or disabling then re-enabling) still cancels old work.
  const selectionKey = JSON.stringify([[...new Set(value.folderIds)].sort(), [...new Set(value.documentIds)].sort()]);
  const current = useRef({ selectionKey, disabled, disableLibrarySelection, onChange, revision: 0 });
  useLayoutEffect(() => {
    const previous = current.current;
    const changed =
      previous.selectionKey !== selectionKey ||
      previous.disabled !== disabled ||
      previous.disableLibrarySelection !== disableLibrarySelection;
    current.current = {
      selectionKey,
      disabled,
      disableLibrarySelection,
      onChange,
      revision: previous.revision + Number(changed),
    };
  }, [selectionKey, disabled, disableLibrarySelection, onChange]);
  const selecting = useRef(false);
  const loadingIds = useRef(new Set<string>());
  const requests = useRef(new Set<ReturnType<typeof browse>>());

  useEffect(() => {
    mounted.current = true;
    const pending = requests.current;
    return () => {
      mounted.current = false;
      // StrictMode replays mount effects synchronously. Let that replay keep
      // its pending read; abort only when this space really stays unmounted.
      queueMicrotask(() => {
        if (!mounted.current) pending.forEach((request) => request.abort());
      });
    };
  }, []);

  const page = useCallback(
    async (parentId: string, offset: number) => {
      if (!mounted.current || !spaceId) throw new Error("Picker is no longer active");
      const request = browse({
        id: spaceId,
        parentId: parentId || undefined,
        offset,
        limit: PAGE_SIZE,
        order: "name_asc",
      });
      requests.current.add(request);
      try {
        const result = await request.unwrap();
        if (!mounted.current) throw new Error("Picker is no longer active");
        return result;
      } finally {
        requests.current.delete(request);
      }
    },
    [browse, spaceId],
  );

  const load = useCallback(
    async (parentId: string, offset = 0) => {
      if (loadingIds.current.has(parentId)) return;
      loadingIds.current.add(parentId);
      setLoading((prev) => ({ ...prev, [parentId]: true }));
      setErrors((prev) => ({ ...prev, [parentId]: false }));
      try {
        const result = await page(parentId, offset);
        setDirectories((prev) => ({
          ...prev,
          [parentId]: { ...result, items: offset ? [...(prev[parentId]?.items ?? []), ...result.items] : result.items },
        }));
      } catch {
        if (mounted.current) setErrors((prev) => ({ ...prev, [parentId]: true }));
      } finally {
        loadingIds.current.delete(parentId);
        if (mounted.current) setLoading((prev) => ({ ...prev, [parentId]: false }));
      }
    },
    [page],
  );

  useEffect(() => {
    if (spaceId) void load(ROOT);
  }, [load, spaceId]);

  // Selection uses fresh, complete directories, never just the visible page.
  // Offset pagination has no snapshot token: reject detectable concurrent edits.
  const allEntries = async (parentId: string): Promise<Entry[]> => {
    const entries: Entry[] = [];
    let total: number | undefined;
    do {
      const result = await page(parentId, entries.length);
      if (total !== undefined && result.total !== total) throw new Error("Directory changed");
      total = result.total;
      if (!result.items.length && entries.length < total) throw new Error("Incomplete directory");
      entries.push(...result.items);
    } while (entries.length < total);
    if (entries.length !== total || new Set(entries.map((entry) => entry.data.id)).size !== total) {
      throw new Error("Directory changed");
    }
    return entries;
  };

  const change = async (resolve: () => Promise<DocumentLibrarySelection>) => {
    if (disabled || selecting.current) return;
    const revision = current.current.revision;
    const isCurrent = () => mounted.current && revision === current.current.revision;
    selecting.current = true;
    setBusy(true);
    setSelectionError(false);
    try {
      const next = await resolve();
      if (isCurrent()) current.current.onChange(next);
    } catch {
      if (isCurrent()) setSelectionError(true);
    } finally {
      selecting.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const toggleFolder = (folder: Folder) => {
    if (disableLibrarySelection) return;
    void change(async () => {
      // Swift selects every existing sub-folder. Each selected folder covers
      // its direct documents; it is not a recursive server-side scope.
      const folderIds = new Set<string>([folder.id]);
      const documentIds = new Set<string>();
      const queue = [folder.id];
      for (let index = 0; index < queue.length; index++) {
        for (const entry of await allEntries(queue[index])) {
          if (entry.kind === "folder" && !folderIds.has(entry.data.id)) {
            folderIds.add(entry.data.id);
            queue.push(entry.data.id);
          } else if (entry.kind === "document") documentIds.add(entry.data.id);
        }
      }
      // Decide from the complete subtree, not the partially loaded checkbox.
      // A restored partial scope is filled; a complete scope is cleared. Opening
      // folders (or fetching more pages) cannot change the meaning of this click.
      const allSelected = [...folderIds].every((id) => value.folderIds.includes(id));
      return {
        folderIds: allSelected
          ? value.folderIds.filter((id) => !folderIds.has(id))
          : [...new Set([...value.folderIds, ...folderIds])],
        documentIds: value.documentIds.filter((id) => !documentIds.has(id)),
      };
    });
  };

  const toggleDocument = (id: string, parentId: string, checked: boolean) => {
    const covered = value.folderIds.includes(parentId);
    if (covered && disableLibrarySelection) return;
    void change(async () => {
      if (checked) return { ...value, documentIds: [...new Set([...value.documentIds, id])] };
      if (!covered) return { ...value, documentIds: value.documentIds.filter((uid) => uid !== id) };
      // There is no exclusion field. Keep child folders selected and replace
      // only the direct parent by ALL its other documents, as Swift did.
      const siblings = (await allEntries(parentId))
        .filter((entry) => entry.kind === "document")
        .map((entry) => entry.data.id);
      return {
        folderIds: value.folderIds.filter((uid) => uid !== parentId),
        documentIds: [...new Set([...value.documentIds, ...siblings])].filter((uid) => uid !== id),
      };
    });
  };

  const folderState = (id: string): { checked: boolean; partial: boolean; unknown: boolean } => {
    if (!value.folderIds.length && !value.documentIds.length) {
      return { checked: false, partial: false, unknown: false };
    }
    const own = value.folderIds.includes(id);
    const directory = directories[id];
    const children = directory?.items ?? [];
    const subfolders = children.filter((entry) => entry.kind === "folder").map((entry) => folderState(entry.data.id));
    // All pages of this directory AND all descendant directories are required
    // before claiming a complete subtree. A restored id alone only covers its
    // direct documents; it says nothing about selected/excluded subfolders.
    const unknown =
      !directory ||
      loading[id] ||
      errors[id] ||
      new Set(children.map((entry) => entry.data.id)).size !== directory.total ||
      subfolders.some((child) => child.unknown);
    const hasDocument = children.some(
      (entry) => entry.kind === "document" && value.documentIds.includes(entry.data.id),
    );
    const checked = !unknown && own && subfolders.every((child) => child.checked);
    return {
      checked,
      // Unlocated restored picks can belong to an unloaded descendant. Show an
      // explicitly unknown mixed state instead of claiming either all or none.
      partial:
        !checked && (unknown || own || hasDocument || subfolders.some((child) => child.checked || child.partial)),
      unknown,
    };
  };

  const renderDirectory = (parentId: string): ReactNode => {
    const directory = directories[parentId];
    const items = directory?.items ?? [];
    return (
      <ul className={styles.tree} aria-busy={loading[parentId] || busy}>
        {items.map((entry) => {
          const { id, name } = entry.data;
          if (entry.kind === "folder") {
            const isExpanded = expanded.includes(id);
            const state = folderState(id);
            return (
              <li key={id} className={styles.node}>
                <div
                  className={styles.nodeRow}
                  title={state.unknown ? t("rework.weaverAgents.documentSelectionUnknown") : undefined}
                >
                  <button
                    type="button"
                    className={styles.nodeTrigger}
                    aria-label={`${isExpanded ? t("rework.collapse") : t("rework.expand")} ${name}`}
                    aria-expanded={isExpanded}
                    onClick={() => {
                      setExpanded((prev) => (isExpanded ? prev.filter((item) => item !== id) : [...prev, id]));
                      if (!isExpanded && !directories[id]) void load(id);
                    }}
                  />
                  <span className={`${styles.expandIcon} material-symbols-outlined`} aria-hidden>
                    {isExpanded ? "expand_more" : "chevron_right"}
                  </span>
                  <Checkbox
                    className={styles.checkbox}
                    aria-label={name}
                    checked={state.checked}
                    indeterminate={state.partial}
                    aria-description={state.unknown ? t("rework.weaverAgents.documentSelectionUnknown") : undefined}
                    disabled={disabled || busy || disableLibrarySelection}
                    onChange={() => toggleFolder(entry.data)}
                  />
                  <span className={styles.folderIcon} style={{ color: FOLDER_ICON.color }} aria-hidden>
                    <Icon category="outlined" type={FOLDER_ICON.type} filled={FOLDER_ICON.filled} />
                  </span>
                  <span className={styles.nodeMeta}>
                    <span className={styles.nodeLabel} title={name}>
                      {name}
                    </span>
                  </span>
                </div>
                {isExpanded && <div className={styles.nodeChildren}>{renderDirectory(id)}</div>}
              </li>
            );
          }
          if (foldersOnly) return null;
          const covered = value.folderIds.includes(parentId);
          const spec = fileIconSpec(name.split(".").pop()?.toLowerCase());
          return (
            <li key={id} className={styles.documentItem}>
              {showDocuments && (
                <Checkbox
                  className={styles.checkbox}
                  aria-label={name}
                  checked={covered || value.documentIds.includes(id)}
                  disabled={disabled || busy || (covered && disableLibrarySelection)}
                  onChange={(event) => toggleDocument(id, parentId, event.target.checked)}
                />
              )}
              <span className={styles.documentIcon} style={{ color: spec.color }} aria-hidden>
                <Icon category="outlined" type={spec.type} filled={spec.filled} />
              </span>
              <span className={styles.documentName} title={name}>
                {name}
              </span>
            </li>
          );
        })}
        {loading[parentId] && <li className={styles.loadingText}>{t("rework.loading")}</li>}
        {errors[parentId] && (
          <li role="alert" className={styles.stateText}>
            {t("common.loadingError")}{" "}
            <Button
              type="button"
              color="primary"
              variant="text"
              size="small"
              onClick={() => void load(parentId, items.length)}
            >
              {t("common.retry")}
            </Button>
          </li>
        )}
        {!loading[parentId] && !errors[parentId] && directory && items.length < directory.total && (
          <li>
            <Button
              type="button"
              color="primary"
              variant="text"
              size="small"
              onClick={() => void load(parentId, items.length)}
            >
              {t("dataHub.loadMore")}
            </Button>
          </li>
        )}
        {directory?.total === 0 && <li className={styles.stateText}>{t("common.noData")}</li>}
      </ul>
    );
  };

  if (!spaceId) return <p className={styles.stateText}>{t("rework.weaverAgents.scopeUnavailable")}</p>;
  return (
    <div className={styles.tree}>
      <div className={styles.selectionSummary}>
        <span>
          {t("chatbot.composerSettings.librariesCount", { count: value.folderIds.length })},{" "}
          {t("chatbot.composerSettings.documentsCount", { count: value.documentIds.length })}
        </span>
        <Button
          type="button"
          color="primary"
          variant="text"
          size="small"
          disabled={
            disabled || busy || (!value.documentIds.length && (disableLibrarySelection || !value.folderIds.length))
          }
          onClick={() => onChange({ folderIds: disableLibrarySelection ? value.folderIds : [], documentIds: [] })}
        >
          {t("chatbot.documentScopePanel.clearSelection")}
        </Button>
      </div>
      {busy && (
        <p role="status" className={styles.loadingText}>
          {t("rework.loading")}
        </p>
      )}
      {selectionError && (
        <p role="alert" className={styles.stateText}>
          {t("rework.weaverAgents.documentSelectionFailed")}
        </p>
      )}
      {renderDirectory(ROOT)}
    </div>
  );
}
