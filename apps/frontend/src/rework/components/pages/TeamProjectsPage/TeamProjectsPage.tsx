// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import TeamCard from "@shared/organisms/TeamCard/TeamCard";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { useMySpacesQuery, useTeamProjectsQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import ProjectCreationModal from "./ProjectCreationModal";
import styles from "./TeamProjectsPage.module.css";

/** The person's projects of the team, then its other visible ones: members open one, others join it when it is open.
 *  The team's direct Owner also creates projects here. */
export default function TeamProjectsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const query = useTeamProjectsQuery(sessionQueryArgs({ id: teamId ?? "" }), {
    skip: !teamId,
    refetchOnMountOrArgChange: true,
  });
  const access = useSpaceAccess(teamId ?? "", "manage");
  const team = useMySpacesQuery().currentData?.find((space) => space.id === teamId);
  const [creating, setCreating] = useState(false);
  // currentData never carries a previous team's answer; a refetch keeps the cards in place.
  const projects = query.isError ? undefined : query.currentData;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.teamProjects.title")}
        subtitle={t("rework.teamProjects.subtitle")}
        actions={
          access.offered && (
            <Button
              color="primary"
              variant="filled"
              size="small"
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setCreating(true)}
            >
              {t("rework.create")}
            </Button>
          )
        }
      />
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
        [
          { key: "mine", items: projects.filter((project) => project.is_member) },
          { key: "others", items: projects.filter((project) => !project.is_member) },
        ].map(
          ({ key, items }) =>
            items.length > 0 && (
              <section key={key} className={styles.section} aria-labelledby={`team-projects-${key}`}>
                <h2 id={`team-projects-${key}`} className={styles.sectionTitle}>
                  {t(`rework.teamProjects.${key}`)}
                </h2>
                <ul className={styles.list}>
                  {items.map((project) => (
                    <li key={project.id} className={styles.item}>
                      <TeamCard team={project} kind="project" onJoined={() => void query.refetch()} />
                    </li>
                  ))}
                </ul>
              </section>
            ),
        )
      )}
      {creating && teamId && (
        <ProjectCreationModal teamId={teamId} teamName={team?.name} onClose={() => setCreating(false)} />
      )}
    </div>
  );
}
