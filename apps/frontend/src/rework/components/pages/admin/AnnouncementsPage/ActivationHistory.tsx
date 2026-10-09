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
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import FilterChips from "@shared/molecules/FilterChips/FilterChips";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { userDisplayName } from "@core/utils/userDisplayName";
import { useLocalStorageState } from "../../../../../hooks/useLocalStorageState";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import {
  useAnnouncementActivationHistoryQuery,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AnnouncementActivationEvent } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ActivationHistory.module.css";

type HistoryAction = AnnouncementActivationEvent["action"];
const ACTIONS: HistoryAction[] = ["activated", "deactivated"];

/**
 * Who switched which announcement on or off, and when, as a dense full-width table.
 * The API returns the newest 100 events already sorted, also the `/users/by-ids`
 * limit, so actors resolve in one call.
 */
export default function ActivationHistory() {
  const { t, i18n } = useTranslation();
  const { data: events = [], isLoading, isError } = useAnnouncementActivationHistoryQuery();
  // Remembered per browser: admins mostly come back to look at activations only.
  const [storedFilter, setActionFilter] = useLocalStorageState<HistoryAction | null>(
    "announcements.historyActionFilter",
    null,
  );
  // A value from an older build, or hand-edited, means no filter.
  const actionFilter = storedFilter && ACTIONS.includes(storedFilter) ? storedFilter : null;
  const shown = useMemo(
    () => (actionFilter ? events.filter((event) => event.action === actionFilter) : events),
    [events, actionFilter],
  );

  const actorIds = useMemo(
    () => [...new Set(events.map((event) => event.actor_uid).filter((uid): uid is string => Boolean(uid)))],
    [events],
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
  if (events.length === 0) {
    return <PageEmptyState icon="history" message={t("rework.announcements.history.empty")} />;
  }

  const label = (event: AnnouncementActivationEvent) =>
    resolveAnnouncementText(event.label, i18n.language) ?? event.announcement_id;
  const kind = (event: AnnouncementActivationEvent) => t(`rework.announcements.kind.${event.kind}`);
  const action = (event: AnnouncementActivationEvent) => t(`rework.announcements.history.${event.action}`);
  const actor = (event: AnnouncementActivationEvent) =>
    event.actor_uid
      ? userDisplayName(event.actor_uid, actorById.get(event.actor_uid))
      : t("rework.announcements.history.unknownActor");

  const columns: DataTableColumn<AnnouncementActivationEvent>[] = [
    {
      label: t("rework.announcements.history.column.announcement"),
      size: "minmax(12rem, 3fr)",
      cellRenderer: label,
      sortable: true,
      sortValue: label,
    },
    {
      label: t("rework.announcements.history.column.type"),
      size: "minmax(8rem, 1fr)",
      // A banner's chip takes its severity tone, as the banner does; a patch note stays neutral.
      cellRenderer: (event) => (
        <StatusBadge tone={(event.kind === "banner" && event.severity) || "neutral"} label={kind(event)} />
      ),
      sortable: true,
      sortValue: kind,
    },
    {
      label: t("rework.announcements.history.column.action"),
      size: "minmax(9rem, 1fr)",
      cellRenderer: (event) => (
        <span className={styles.action} data-action={event.action}>
          <Icon category="outlined" type={event.action === "activated" ? "visibility" : "visibility_off"} />
          {action(event)}
        </span>
      ),
      sortable: true,
      sortValue: action,
    },
    {
      label: t("rework.announcements.history.column.date"),
      size: "minmax(11rem, 1.5fr)",
      cellRenderer: (event) => (
        <time className={styles.cellText} dateTime={event.occurred_at}>
          {new Date(event.occurred_at).toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" })}
        </time>
      ),
      sortable: true,
      sortValue: (event) => new Date(event.occurred_at),
    },
    {
      label: t("rework.announcements.history.column.by"),
      size: "minmax(10rem, 1.5fr)",
      cellRenderer: actor,
      sortable: true,
      sortValue: actor,
    },
  ];

  return (
    <div className={styles.history}>
      <FilterChips<HistoryAction>
        options={ACTIONS.map((id) => ({
          id,
          label: t(`rework.announcements.history.filter.${id}`),
          count: events.filter((event) => event.action === id).length,
        }))}
        value={actionFilter}
        onChange={setActionFilter}
        allLabel={t("rework.announcements.history.filter.all")}
        aria-label={t("rework.announcements.history.filter.group")}
      />
      <div className={styles.table}>
        <DataTable
          columns={columns}
          data={shown}
          rowKey={(event) => event.id}
          size="small"
          firstColumnInset
          pageSize={20}
        />
      </div>
    </div>
  );
}
