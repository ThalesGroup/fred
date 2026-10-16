// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useParams } from "react-router-dom";
import ResourceExplorer from "@shared/organisms/ResourceExplorer/ResourceExplorer.tsx";
import TablePagination from "@shared/molecules/TablePagination/TablePagination.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import {
  useLazyListDocumentsQuery,
  useLazyListFoldersQuery,
  type Document,
  type Folder,
} from "../../../../slices/fredManager/fredManagerOpenApi";
import { useMySpacesQuery } from "../../../../slices/fredManager/fredManagerApiEnhancements";
import styles from "./TeamResourcesPage.module.css";
import nameStyles from "@shared/molecules/DocumentNameCell/DocumentNameCell.module.css";
import { fileIconSpec, FOLDER_ICON } from "../../../utils/fileIconSpec.ts";
import rowStyles from "./DocumentWorkspace/DocumentWorkspace.module.css";

const PAGE_SIZE = 50;
type Cursor = Pick<Document, "id" | "name"> | undefined;

export default function TeamResourcesPage() {
  const { teamId = "" } = useParams();
  // Historical aliases are not manager space identifiers.
  if (!/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(teamId)) {
    return <Navigate to="/home" replace />;
  }
  return <SpaceResources key={teamId} spaceId={teamId} />;
}

function SpaceResources({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const memberships = useMySpacesQuery();
  const personal = !!memberships.currentData?.find((s) => s.id === spaceId)?.personal_owner;
  const [trail, setTrail] = useState<Folder[]>([]);
  const [cursors, setCursors] = useState<Cursor[]>([undefined]);
  const [page, setPage] = useState(0);
  const folderId = trail[trail.length - 1]?.id;
  const cursor = cursors[page];
  const navigate = (next: Folder[]) => {
    setTrail(next);
    setCursors([undefined]);
    setPage(0);
  };
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>
            {t(personal ? "rework.resources.pageTitlePersonal" : "rework.resources.pageTitle")}
          </h1>
          <p className={styles.subtitle}>
            {t(personal ? "rework.resources.pageSubtitlePersonal" : "rework.resources.pageSubtitle")}
          </p>
        </div>
      </header>
      <div className={styles.panel}>
        <div className={styles.workspace}>
          <ResourcePage
            key={`${spaceId}/${folderId ?? "root"}/${page}/${cursor?.id ?? "first"}`}
            spaceId={spaceId}
            folderId={folderId}
            cursor={cursor}
            page={page}
            breadcrumb={{
              segments: [
                { label: t("rework.sidebar.team.menu.resources"), onClick: () => navigate([]) },
                ...trail.map((folder, index) => ({
                  label: folder.name,
                  onClick: () => navigate(trail.slice(0, index + 1)),
                })),
              ],
              canGoBack: trail.length > 0,
              onBack: () => navigate(trail.slice(0, -1)),
              backLabel: t("rework.back"),
            }}
            onFolder={(folder) => navigate([...trail, folder])}
            onPage={setPage}
            onNext={(last) => {
              setCursors([...cursors.slice(0, page + 1), { id: last.id, name: last.name }]);
              setPage(page + 1);
            }}
          />
        </div>
      </div>
    </div>
  );
}

function ResourcePage({
  spaceId,
  folderId,
  cursor,
  page,
  breadcrumb,
  onFolder,
  onPage,
  onNext,
}: {
  spaceId: string;
  folderId?: string;
  cursor: Cursor;
  page: number;
  breadcrumb: import("@shared/organisms/ResourceExplorer/ResourceExplorer.tsx").ResourceExplorerBreadcrumbProps;
  onFolder: (folder: Folder) => void;
  onPage: (page: number) => void;
  onNext: (last: Document) => void;
}) {
  const { t } = useTranslation();
  const [loadFolders, folders] = useLazyListFoldersQuery();
  const [loadDocuments, documents] = useLazyListDocumentsQuery();
  const [attempt, setAttempt] = useState(0);
  const [ready, setReady] = useState(false);
  // A keyed mount begins uninitialized even when RTK has cached this page.
  // Re-entering always verifies current authority before showing any rows.
  const load = useCallback(
    () => [
      loadFolders({ id: spaceId, parentId: folderId }),
      loadDocuments({ id: spaceId, folderId, afterId: cursor?.id, afterName: cursor?.name, limit: PAGE_SIZE + 1 }),
    ],
    [spaceId, folderId, cursor?.id, cursor?.name, loadFolders, loadDocuments],
  );
  useEffect(() => {
    let active = true;
    let requests: ReturnType<typeof load> = [];
    const refresh = async () => {
      while (active) {
        requests = load();
        const results = await Promise.all(requests);
        if (!active) return;
        // RTK may deduplicate against a request started by an abandoned mount
        // (including StrictMode cleanup). Only this entry's own reads may render.
        if (results.every((result, index) => result.requestId === requests[index].requestId)) {
          setReady(true);
          return;
        }
        requests.forEach((request) => request.unsubscribe());
      }
    };
    void refresh();
    return () => {
      active = false;
      requests.forEach((request) => {
        request.abort();
        request.unsubscribe();
      });
    };
  }, [load, attempt]);
  const loading =
    !ready || folders.isUninitialized || documents.isUninitialized || folders.isFetching || documents.isFetching;
  const errors = [folders.error, documents.error].filter(Boolean);
  const failed = errors.length > 0;
  const status = (code: number) => errors.some((e) => e && "status" in e && e.status === code);
  const errorKey = status(403) ? "denied" : status(404) ? "missing" : "unavailable";
  const docs = documents.currentData?.slice(0, PAGE_SIZE) ?? [];
  const rows: (Folder | Document)[] =
    loading || failed ? [] : [...(page === 0 ? (folders.currentData ?? []) : []), ...docs];
  return (
    <ResourceExplorer<Folder | Document>
      breadcrumb={breadcrumb}
      selectable={false}
      loading={loading}
      loadingMessage={t("rework.resources.loading")}
      empty={failed || rows.length === 0}
      emptyMessage={
        failed ? (
          <div role="alert">
            <p>{t(`rework.resources.managerRead.${errorKey}`)}</p>
            <Button
              color="primary"
              variant="text"
              size="small"
              onClick={() => {
                setReady(false);
                setAttempt((value) => value + 1);
              }}
            >
              {t("rework.bootstrap.reload")}
            </Button>
          </div>
        ) : (
          t("rework.resources.empty.folder")
        )
      }
      rows={rows}
      rowKey={(row) => row.id}
      columns={[
        {
          label: t("rework.resources.columns.name"),
          size: "minmax(8rem, 2fr)",
          cellRenderer: (row) =>
            "mime" in row ? (
              <span className={nameStyles.nameCell}>
                <span
                  className={nameStyles.rowIcon}
                  style={{ color: fileIconSpec(row.name.split(".").pop()?.toLowerCase()).color }}
                >
                  <Icon category="outlined" type={fileIconSpec(row.name.split(".").pop()?.toLowerCase()).type} />
                </span>
                <span>{row.name}</span>
              </span>
            ) : (
              <button type="button" className={rowStyles.nameButton} onClick={() => onFolder(row)}>
                <span className={rowStyles.rowIcon} style={{ color: FOLDER_ICON.color }}>
                  <Icon category="outlined" type="folder" filled />
                </span>
                <span>{row.name}</span>
              </button>
            ),
        },
        {
          label: t("rework.resources.columns.size"),
          size: "minmax(0, 6.5rem)",
          cellRenderer: (row) => ("mime" in row ? formatBytes(row.size) : "-"),
        },
      ]}
      paginationFooter={
        !loading && !failed && (rows.length > 0 || page > 0) ? (
          <TablePagination
            currentPage={page}
            currentPageLabel={t("rework.resources.managerRead.page", { page: page + 1 })}
            hasNext={(documents.currentData?.length ?? 0) > PAGE_SIZE}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[]}
            labels={{
              first: t("dataTable.pagination.first"),
              prev: t("dataTable.pagination.prev"),
              next: t("dataTable.pagination.next"),
            }}
            onFirst={() => onPage(0)}
            onPrev={() => onPage(page - 1)}
            onNext={() => {
              if (docs.length) onNext(docs[docs.length - 1]);
            }}
          />
        ) : undefined
      }
    />
  );
}
