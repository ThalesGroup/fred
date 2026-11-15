// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import Select from "@shared/molecules/Select/Select";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import { useTeamDocumentActivityQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ActivityKind, ActivityStatus } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamSettingsPage.module.scss";
import activityStyles from "@shared/organisms/TaskActivity/TaskActivity.module.css";

const KINDS: ActivityKind[] = ["upload", "processing", "document_deletion", "folder_deletion"];
const STATUSES: ActivityStatus[] = ["pending", "running", "succeeded", "failed", "retrying", "blocked"];
const POLL_MS = 5_000;

/** Durable team history, independently authorized from management and consumption.
 * RTK serializes each page's polling; no merging of a stale active list into history.
 * The route keys this component by team, and currentData never renders another page.
 */
export default function TeamActivity({ spaceId }: { spaceId: string }) {
  const { t, i18n } = useTranslation();
  const access = useSpaceAccess(spaceId, "read");
  const [search, setSearch] = useSearchParams();
  const [view, setView] = useState(0);
  const scoped = search.get("activitySpace") === spaceId;
  const kind = scoped ? KINDS.find((value) => value === search.get("kind")) : undefined;
  const status = scoped ? STATUSES.find((value) => value === search.get("status")) : undefined;
  const until = scoped ? (search.get("until") ?? undefined) : undefined;
  const before = scoped ? (search.get("before") ?? undefined) : undefined;
  const expanded = scoped ? search.get("operation") : null;
  // `view` changes cache identity only; the generated client sends declared fields.
  const args = sessionQueryArgs({ id: spaceId, kind, status, until, before, view });
  const query = useTeamDocumentActivityQuery(args, {
    skip: !access.allowed,
    pollingInterval: POLL_MS,
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(query.refetch, !access.allowed, true);
  const page = query.currentData;
  // Fix the creation window, not the outcomes. A reload preserves filters, page
  // and disclosure, while a fresh server read still checks current permissions.
  useEffect(() => {
    if (!access.allowed || until || query.isFetching || query.isError || !page) return;
    setSearch(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (next.get("activitySpace") !== spaceId) {
          for (const key of ["kind", "status", "before", "operation"]) next.delete(key);
        }
        next.set("activitySpace", spaceId);
        next.set("until", page.until);
        return next;
      },
      { replace: true },
    );
  }, [access.allowed, until, page, query.isFetching, query.isError, setSearch, spaceId]);

  const change = (key: string, value?: string) => {
    setSearch((previous) => {
      const next = new URLSearchParams(previous);
      next.set("activitySpace", spaceId);
      if (value) next.set(key, value);
      else next.delete(key);
      if (key === "kind" || key === "status") {
        next.delete("before");
        next.delete("operation");
      }
      return next;
    });
  };
  const newest = () => {
    setView((value) => value + 1);
    setSearch((previous) => {
      const next = new URLSearchParams(previous);
      for (const key of ["until", "before", "operation"]) next.delete(key);
      next.set("activitySpace", spaceId);
      return next;
    });
  };
  const date = (value: string) => new Date(value).toLocaleString(i18n.language);
  const failure = normalizeApiError(query.error).status;
  const forbidden = failure === 403 || (access.settled && !access.allowed);
  const unavailable = failure !== undefined && [401, 403, 404, 409, 422].includes(failure);
  // A network failure does not undo a known terminal result. Refusals do hide it.
  const rows = access.allowed && !unavailable ? page?.items : undefined;

  return (
    <section className={styles.teamSettingsPage}>
      <PageHeader title={t("rework.teamActivity.title")} subtitle={t("rework.teamActivity.subtitle")} />
      <p>{t("rework.teamActivity.scope")}</p>
      {forbidden ? (
        <p role="alert">{t("rework.teamActivity.forbidden")}</p>
      ) : access.error ? (
        <p role="alert">{t("rework.taskActivity.loadError")}</p>
      ) : !access.settled ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <>
          <div className={styles.actions}>
            <Select
              size="small"
              compact
              label={t("rework.teamActivity.kind")}
              value={kind ?? ""}
              options={[
                { key: "all", value: "", label: t("rework.teamActivity.all") },
                ...KINDS.map((value) => ({ key: value, value, label: t(`rework.teamActivity.kinds.${value}`) })),
              ]}
              onChange={(value) => change("kind", value)}
            />
            <Select
              size="small"
              compact
              label={t("rework.teamActivity.status")}
              value={status ?? ""}
              options={[
                { key: "all", value: "", label: t("rework.teamActivity.all") },
                ...STATUSES.map((value) => ({ key: value, value, label: t(`rework.tasks.state.${value}`) })),
              ]}
              onChange={(value) => change("status", value)}
            />
            <Button color="primary" variant="outlined" size="small" onClick={newest} disabled={query.isFetching}>
              {t("rework.teamActivity.newest")}
            </Button>
          </div>
          <p>{t("rework.teamActivity.polling")}</p>
          {page && <p>{t("rework.teamActivity.window", { when: date(page.until) })}</p>}
          {query.isError && (
            <p role="alert">
              {t(failure === 404 || failure === 409 ? "rework.teamActivity.missing" : "rework.taskActivity.loadError")}
              {!!rows?.length && ` ${t("rework.teamActivity.stale")}`}
            </p>
          )}
          {!rows ? (
            !query.isError && <p role="status">{t("common.loading")}</p>
          ) : rows.length === 0 ? (
            !query.isError && <p>{t("rework.taskActivity.empty")}</p>
          ) : (
            <ul className={activityStyles.list} aria-busy={query.isFetching}>
              {rows.map((item) => {
                const identity = `${item.kind}:${item.id}`;
                return (
                  <li key={identity} className={activityStyles.row}>
                    <div className={activityStyles.rowMain}>
                      <span className={activityStyles.name}>
                        {item.name ?? t(`rework.teamActivity.kinds.${item.kind}`)}
                      </span>
                      <TaskStateBadge state={item.status} showLabel size="sm" />
                      <span>
                        {t(`rework.teamActivity.kinds.${item.kind}`)} · {date(item.created_at)}
                      </span>
                    </div>
                    {item.stage && <span>{t(`rework.teamActivity.stages.${item.stage}`)}</span>}
                    {item.due_at && item.status === "pending" && (
                      <span>{t("rework.taskActivity.dueOn", { when: date(item.due_at) })}</span>
                    )}
                    {item.completed_at && (
                      <span>{t("rework.teamActivity.finishedAt", { when: date(item.completed_at) })}</span>
                    )}
                    {item.error_code && (
                      <p className={activityStyles.rowError}>
                        {t(`rework.documentStorage.processingErrors.${item.error_code}`, {
                          defaultValue: t("rework.teamActivity.operationError"),
                        })}
                      </p>
                    )}
                    <Button
                      color="on-surface"
                      variant="text"
                      size="small"
                      onClick={() => change("operation", expanded === identity ? undefined : identity)}
                      aria-expanded={expanded === identity}
                    >
                      {t("rework.teamActivity.details")}
                    </Button>
                    {expanded === identity && (
                      <dl className={styles.activityDetails}>
                        <dt>{t("rework.teamActivity.reference")}</dt>
                        <dd>{item.id}</dd>
                        {item.target_id && (
                          <>
                            <dt>{t("rework.teamActivity.target")}</dt>
                            <dd>{item.target_id}</dd>
                          </>
                        )}
                        {item.profile && (
                          <>
                            <dt>{t("rework.teamActivity.profile")}</dt>
                            <dd>{item.profile}</dd>
                          </>
                        )}
                        {item.retry_of && (
                          <>
                            <dt>{t("rework.teamActivity.retryOf")}</dt>
                            <dd>{item.retry_of}</dd>
                          </>
                        )}
                        {item.error_code && (
                          <>
                            <dt>{t("rework.teamActivity.errorCode")}</dt>
                            <dd>{item.error_code}</dd>
                          </>
                        )}
                      </dl>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <div className={styles.actions}>
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={!before || query.isFetching}
              onClick={() => change("before")}
            >
              {t("rework.teamActivity.firstPage")}
            </Button>
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={!rows || !page?.next_cursor || query.isFetching}
              onClick={() => change("before", page?.next_cursor ?? undefined)}
            >
              {t("dataTable.pagination.next")}
            </Button>
          </div>
        </>
      )}
      <Button
        color="primary"
        variant="text"
        size="small"
        disabled={query.isFetching}
        onClick={() => {
          void access.refetch();
          if (!query.isUninitialized) void query.refetch();
        }}
      >
        {t("rework.spaceMembers.refresh")}
      </Button>
      <Disclosure title={t("rework.teamActivity.coverageTitle")}>
        <p>{t("rework.teamActivity.coverage")}</p>
      </Disclosure>
    </section>
  );
}
