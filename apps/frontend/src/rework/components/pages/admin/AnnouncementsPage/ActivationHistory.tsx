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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import FilterChips from "@shared/molecules/FilterChips/FilterChips";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { PatchNoteDialog, type PatchNote } from "@shared/molecules/PatchNoteDialog/PatchNoteDialog";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { userDisplayName } from "@core/utils/userDisplayName";
import { useLocalStorageState } from "../../../../../hooks/useLocalStorageState";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import { resolvePatchNotes } from "../../../../features/announcements/usePatchNoteHistory";
import {
  useAnnouncementExposureHistoryQuery,
  useLazyPatchNotePackageQuery,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AnnouncementExposure } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ActivationHistory.module.css";

type ExposureKind = AnnouncementExposure["kind"];
const KINDS: ExposureKind[] = ["banner", "patch_note"];

/**
 * What users were shown, one line per exposure: a banner from its activation to
 * its deactivation, or a patch-note announcement until it was replaced or
 * withdrawn. An announcement's line reopens the patch notes exactly as announced.
 */
export default function ActivationHistory() {
  const { t, i18n } = useTranslation();
  const { showError, showInfo } = useToast();
  const { data: exposures = [], isLoading, isError } = useAnnouncementExposureHistoryQuery();
  const [loadPackage] = useLazyPatchNotePackageQuery();
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [opened, setOpened] = useState<PatchNote[]>([]);
  // Remembered per browser: an admin mostly comes back for one of the two types.
  const [storedFilter, setKindFilter] = useLocalStorageState<ExposureKind | null>(
    "announcements.historyTypeFilter",
    null,
  );
  // A value from an older build, or hand-edited, means no filter.
  const kindFilter = storedFilter && KINDS.includes(storedFilter) ? storedFilter : null;
  const shown = useMemo(
    () => (kindFilter ? exposures.filter((exposure) => exposure.kind === kindFilter) : exposures),
    [exposures, kindFilter],
  );

  const actorIds = useMemo(
    () => [...new Set(exposures.map((exposure) => exposure.actor_uid).filter((uid): uid is string => Boolean(uid)))],
    [exposures],
  );
  const { data: actors = [] } = useUsersByIdsQuery({ ids: actorIds }, { skip: actorIds.length === 0 });
  const actorById = useMemo(() => new Map(actors.map((summary) => [summary.id, summary])), [actors]);

  if (isLoading) {
    return (
      <div className={styles.state}>
        <Spinner />
      </div>
    );
  }
  if (isError) {
    return <p className={`${styles.state} ${styles.error}`}>{t("rework.announcements.history.error")}</p>;
  }
  if (exposures.length === 0) {
    return <PageEmptyState icon="history" message={t("rework.announcements.history.empty")} />;
  }

  const openPackage = async (exposure: AnnouncementExposure) => {
    setLoadingId(exposure.id);
    try {
      const snapshots = await loadPackage({ announcementId: exposure.id }, true).unwrap();
      const readable = resolvePatchNotes(snapshots, i18n.language);
      // Nothing readable: say so, the dialog would stay closed without a word.
      if (readable.length === 0) showInfo({ summary: t("rework.announcements.history.packageEmpty") });
      setOpened(readable);
    } catch {
      showError({ summary: t("rework.announcements.history.packageFailed") });
    } finally {
      setLoadingId(null);
    }
  };

  // A patch-note line is named after the first note of its package.
  const title = (exposure: AnnouncementExposure) => {
    const first = resolveAnnouncementText(exposure.label, i18n.language) ?? exposure.announcement_id;
    const others = (exposure.note_count ?? 1) - 1;
    return others > 0 ? t("rework.announcements.history.more", { title: first, count: others }) : first;
  };
  const type = (exposure: AnnouncementExposure) => t(`rework.announcements.history.type.${exposure.kind}`);
  const actor = (exposure: AnnouncementExposure) =>
    exposure.actor_uid
      ? userDisplayName(exposure.actor_uid, actorById.get(exposure.actor_uid))
      : t("rework.announcements.history.unknownActor");
  const moment = (iso: string | null | undefined) =>
    iso && (
      <time className={styles.cellText} dateTime={iso}>
        {new Date(iso).toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" })}
      </time>
    );

  const columns: DataTableColumn<AnnouncementExposure>[] = [
    {
      label: t("rework.announcements.history.column.type"),
      size: "minmax(8rem, 1fr)",
      // A banner's chip takes its severity tone, as the banner does; patch notes stay neutral.
      cellRenderer: (exposure) => (
        <StatusBadge tone={(exposure.kind === "banner" && exposure.severity) || "neutral"} label={type(exposure)} />
      ),
      sortable: true,
      sortValue: type,
    },
    {
      label: t("rework.announcements.history.column.title"),
      size: "minmax(12rem, 3fr)",
      cellRenderer: title,
      sortable: true,
      sortValue: title,
    },
    {
      label: t("rework.announcements.history.column.activation"),
      size: "minmax(11rem, 1.5fr)",
      cellRenderer: (exposure) => moment(exposure.activated_at),
      sortable: true,
      sortValue: (exposure) => new Date(exposure.activated_at),
    },
    {
      label: t("rework.announcements.history.column.deactivation"),
      size: "minmax(11rem, 1.5fr)",
      // Empty while users still see it.
      cellRenderer: (exposure) => moment(exposure.deactivated_at),
    },
    {
      label: t("rework.announcements.history.column.by"),
      size: "minmax(10rem, 1.5fr)",
      cellRenderer: actor,
      sortable: true,
      sortValue: actor,
    },
    {
      label: t("rework.announcements.history.column.open"),
      size: "4rem",
      // Only a line that kept its package has something to open.
      cellRenderer: (exposure) =>
        exposure.kind === "patch_note" &&
        exposure.note_count != null && (
          <IconButton
            size="small"
            variant="icon"
            icon={{ category: "outlined", type: "visibility" }}
            aria-label={t("rework.announcements.history.openPackage")}
            loading={loadingId === exposure.id}
            onClick={() => void openPackage(exposure)}
          />
        ),
    },
  ];

  return (
    <div className={styles.history}>
      <FilterChips<ExposureKind>
        options={KINDS.map((id) => ({
          id,
          label: t(`rework.announcements.history.filter.${id}`),
          count: exposures.filter((exposure) => exposure.kind === id).length,
        }))}
        value={kindFilter}
        onChange={setKindFilter}
        allLabel={t("rework.announcements.history.filter.all")}
        aria-label={t("rework.announcements.history.filter.group")}
      />
      <div className={styles.table}>
        <DataTable
          columns={columns}
          data={shown}
          rowKey={(exposure) => exposure.id}
          size="small"
          firstColumnInset
          pageSize={20}
        />
      </div>
      {/* The users' dialog, read-only: opening a past package records nothing. */}
      <PatchNoteDialog open={opened.length > 0} notes={opened} onClose={() => setOpened([])} />
    </div>
  );
}
