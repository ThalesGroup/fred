// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { useStore } from "react-redux";
import { useTranslation } from "react-i18next";
import type { AppState } from "../../../../common/store";
import Button from "@shared/atoms/Button/Button";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { formatBytes } from "@shared/utils/formatBytes";
import { formatDateTime } from "@rework/utils/formatDateTime";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { useOrganizationSupervisionAccess } from "@core/hooks/useOrganizationSupervisionAccess";
import {
  enhancedControlPlaneApi,
  useOrganizationSupervisionQuery,
  useTeamSupervisionQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import SupervisionCountsView, { SupervisionSummary } from "./SupervisionCountsView";
import styles from "./OrganizationSupervisionPage.module.css";

function ErrorNotice({ error }: { error: unknown }) {
  const { t } = useTranslation();
  const { status, code } = normalizeApiError(error);
  const key =
    status === 401 || status === 403
      ? "forbidden"
      : status === 404
        ? "missing"
        : status === 409
          ? "contextUnavailable"
          : status === 503 || code === "dependency_unavailable"
            ? "dependencyUnavailable"
            : "loadFailed";
  return <p role="alert">{t(`rework.supervision.${key}`)}</p>;
}

export default function OrganizationSupervisionPage() {
  const access = useOrganizationSupervisionAccess();
  // Context changes discard cursor, selection and successful-load dates together.
  return <SupervisionPage key={access.organizationId ?? "no-context"} />;
}

function SupervisionPage() {
  const { t, i18n } = useTranslation();
  const store = useStore<AppState>();
  const access = useOrganizationSupervisionAccess();
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [teamId, setTeamId] = useState<string>();
  const organizationId = access.organizationId ?? "";
  const summary = useOrganizationSupervisionQuery(
    { organizationId, after: cursors[cursors.length - 1] },
    { skip: !access.allowed, refetchOnMountOrArgChange: true },
  );
  const detail = useTeamSupervisionQuery(
    { organizationId, teamId: teamId ?? "" },
    { skip: !access.allowed || !teamId, refetchOnMountOrArgChange: true },
  );
  // Refreshing context suspends metric subscriptions; successful authorization
  // resubscribes with refetchOnMountOrArgChange, including the open detail.
  const refresh = () => {
    void access.refresh();
  };
  useEffect(() => {
    // Resubscription effects run first. Read their current RTK state, not a
    // cached refusal captured by the render before the new request started.
    const state = store.getState();
    const summaryState = enhancedControlPlaneApi.endpoints.organizationSupervision.select({
      organizationId,
      after: cursors[cursors.length - 1],
    })(state);
    const detailState = enhancedControlPlaneApi.endpoints.teamSupervision.select({
      organizationId,
      teamId: teamId ?? "",
    })(state);
    const denied = [
      summaryState.isError ? summaryState.error : undefined,
      teamId && detailState.isError ? detailState.error : undefined,
    ].some((error) => {
      const { status } = normalizeApiError(error);
      return status === 401 || status === 403;
    });
    if (access.allowed && denied) access.revoke();
  }, [
    store,
    organizationId,
    cursors,
    summary.error,
    summary.isError,
    summary.isFetching,
    detail.error,
    detail.isError,
    detail.isFetching,
    teamId,
    access.allowed,
    access.revoke,
  ]);
  useEffect(() => {
    if (!access.loading && !access.allowed) {
      setTeamId(undefined);
      setCursors([undefined]);
    }
  }, [access.loading, access.allowed]);
  const label = (key: string) => t(`rework.supervision.${key}`);
  const number = (value: number) => value.toLocaleString(i18n.language);
  const page = access.allowed && !summary.isError && !summary.isFetching ? summary.currentData : undefined;
  const team = access.allowed && !detail.isError && !detail.isFetching ? detail.currentData : undefined;
  const busy = access.loading || summary.isFetching || (!!teamId && detail.isFetching);
  const lastSuccess = (timestamp?: number) =>
    timestamp
      ? t("rework.supervision.lastSuccess", {
          date: formatDateTime(new Date(timestamp).toISOString(), { seconds: true }),
        })
      : label("neverLoaded");

  const refreshAction = (
    <Button variant="outlined" color="primary" size="medium" disabled={busy} onClick={refresh}>
      {label("refresh")}
    </Button>
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title={label("title")}
        subtitle={access.allowed ? lastSuccess(summary.fulfilledTimeStamp) : undefined}
        actions={refreshAction}
      />
      {access.error ? (
        <ErrorNotice error={access.error} />
      ) : access.loading ? (
        <p role="status">{t("common.loading")}</p>
      ) : !access.organizationId ? (
        <p role="alert">{label("contextUnavailable")}</p>
      ) : !access.allowed ? (
        <p role="alert">{label("forbidden")}</p>
      ) : (
        <>
          {summary.isError ? (
            <ErrorNotice error={summary.error} />
          ) : !page ? (
            <p role="status">{t("common.loading")}</p>
          ) : (
            <>
              <Disclosure title={label("collectionDetails")}>
                <p>
                  {t("rework.supervision.collection", {
                    start: formatDateTime(page.collection_started_at, { seconds: true }),
                    end: formatDateTime(page.collection_finished_at, { seconds: true }),
                  })}
                </p>
                <p>{label("collectionHint")}</p>
                <p>{label("scopeHint")}</p>
              </Disclosure>
              <section aria-label={label("totals")}>
                <SupervisionSummary counts={page.totals} activeTeams={page.active_teams} />
              </section>
              <section>
                <h2>{label("distribution")}</h2>
                <div className={styles.table}>
                  <DataTable
                    size="small"
                    data={(["organization_direct", "teams_total", "personal_total"] as const).map((bucket) => ({
                      bucket,
                      counts: page[bucket],
                    }))}
                    rowKey={(row) => row.bucket}
                    columns={[
                      {
                        label: label("scope"),
                        size: "minmax(14rem, 1.3fr)",
                        cellRenderer: (row) => label(row.bucket),
                      },
                      {
                        label: label("documents"),
                        size: "minmax(9rem, 1fr)",
                        cellRenderer: (row) => number(row.counts.active.documents),
                      },
                      {
                        label: label("vectors"),
                        size: "minmax(9rem, 1fr)",
                        cellRenderer: (row) => number(row.counts.published.vectors),
                      },
                      {
                        label: label("datasets"),
                        size: "minmax(13rem, 1fr)",
                        cellRenderer: (row) => number(row.counts.published.tabular_datasets),
                      },
                      {
                        label: label("volume"),
                        size: "minmax(8rem, 1fr)",
                        cellRenderer: (row) => formatBytes(row.counts.active.bytes, i18n.language),
                      },
                    ]}
                  />
                </div>
                <Disclosure title={label("complementary")}>
                  <div className={styles.compartments}>
                    {(["totals", "organization_direct", "teams_total", "personal_total"] as const).map((bucket) => (
                      <section key={bucket}>
                        <h3>{label(bucket)}</h3>
                        <SupervisionCountsView counts={page[bucket]} />
                      </section>
                    ))}
                  </div>
                </Disclosure>
              </section>
              <section>
                <h2>{label("teams")}</h2>
                {page.teams.items.length === 0 ? (
                  <p>{label("emptyTeams")}</p>
                ) : (
                  <div className={styles.table}>
                    <DataTable
                      size="small"
                      data={page.teams.items}
                      rowKey={(row) => row.id}
                      columns={[
                        {
                          label: label("team"),
                          size: "minmax(12rem, 1.3fr)",
                          cellRenderer: (row) => (
                            <Button
                              className={styles.teamButton}
                              variant="text"
                              color="primary"
                              size="small"
                              onClick={() => setTeamId(row.id)}
                            >
                              {row.name}
                            </Button>
                          ),
                        },
                        {
                          label: label("documents"),
                          size: "minmax(9rem, 1fr)",
                          cellRenderer: (row) => number(row.counts.active.documents),
                        },
                        {
                          label: label("volume"),
                          size: "minmax(8rem, 1fr)",
                          cellRenderer: (row) => formatBytes(row.counts.active.bytes, i18n.language),
                        },
                        {
                          label: label("vectors"),
                          size: "minmax(9rem, 1fr)",
                          cellRenderer: (row) => number(row.counts.published.vectors),
                        },
                        {
                          label: label("datasets"),
                          size: "minmax(13rem, 1fr)",
                          cellRenderer: (row) => number(row.counts.published.tabular_datasets),
                        },
                        {
                          label: label("processing"),
                          size: "minmax(15rem, 1fr)",
                          cellRenderer: (row) =>
                            number(row.counts.processing.reduce((sum, item) => sum + item.documents, 0)),
                        },
                      ]}
                    />
                  </div>
                )}
                <div className={styles.actions}>
                  <Button
                    variant="outlined"
                    color="on-surface"
                    size="small"
                    disabled={cursors.length < 2}
                    onClick={() => setCursors((previous) => previous.slice(0, -1))}
                  >
                    {t("dataTable.pagination.prev")}
                  </Button>
                  <Button
                    variant="outlined"
                    color="on-surface"
                    size="small"
                    disabled={!page.teams.next_cursor}
                    onClick={() => {
                      if (page.teams.next_cursor) setCursors((previous) => [...previous, page.teams.next_cursor!]);
                    }}
                  >
                    {t("dataTable.pagination.next")}
                  </Button>
                </div>
              </section>
            </>
          )}
          <InlineDrawer
            open={!!teamId && !summary.isError}
            onClose={() => setTeamId(undefined)}
            title={team?.team.name ?? label("teamDetail")}
            closeLabel={label("close")}
            headerActions={refreshAction}
          >
            <p>{lastSuccess(detail.currentData ? detail.fulfilledTimeStamp : undefined)}</p>
            {detail.isError ? (
              <ErrorNotice error={detail.error} />
            ) : !team ? (
              <p role="status">{t("common.loading")}</p>
            ) : (
              <>
                <SupervisionSummary counts={team.team.counts} />
                <SupervisionCountsView counts={team.team.counts} />
                <Disclosure title={label("collectionDetails")}>
                  <p>
                    {t("rework.supervision.collection", {
                      start: formatDateTime(team.collection_started_at, { seconds: true }),
                      end: formatDateTime(team.collection_finished_at, { seconds: true }),
                    })}
                  </p>
                  <p>{label("collectionHint")}</p>
                </Disclosure>
              </>
            )}
          </InlineDrawer>
        </>
      )}
    </div>
  );
}
