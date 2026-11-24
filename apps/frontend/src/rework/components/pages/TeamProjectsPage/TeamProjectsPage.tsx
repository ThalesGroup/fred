// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import TeamCard from "@shared/organisms/TeamCard/TeamCard";
import { useTeamProjectsQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import styles from "./TeamProjectsPage.module.css";

/** The team's visible projects and the person's own: members open one, others join it when it is open. */
export default function TeamProjectsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const query = useTeamProjectsQuery(sessionQueryArgs({ id: teamId ?? "" }), {
    skip: !teamId,
    refetchOnMountOrArgChange: true,
  });
  // Never render a previous team's or a failed answer.
  const projects = !query.isError && !query.isFetching ? query.currentData : undefined;

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.teamProjects.title")} subtitle={t("rework.teamProjects.subtitle")} />
      {query.isError ? (
        <span role="alert" className={styles.status}>
          {t("rework.manager.unavailable")}
        </span>
      ) : !projects ? (
        <span role="status" className={styles.status}>
          {t("common.loading")}
        </span>
      ) : projects.length === 0 ? (
        <PageEmptyState icon="assignment" message={t("rework.teamProjects.empty")} />
      ) : (
        <ul className={styles.list}>
          {projects.map((project) => (
            <li key={project.id} className={styles.item}>
              <TeamCard team={project} kind="project" onJoined={() => void query.refetch()} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
