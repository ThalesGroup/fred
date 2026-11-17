// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import SelectableCard from "@shared/molecules/SelectableCard/SelectableCard.tsx";
import { teamRoleLabel } from "@shared/utils/teamRoleLabel";
import { teamProjects } from "@core/utils/teamProjects";
import { useMySpacesQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./TeamProjectsPage.module.css";

/** The projects of a team the person is a member of, each card entering its project. */
export default function TeamProjectsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const memberships = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: 60 });
  const spaces = memberships.isError ? undefined : memberships.currentData;
  const projects = teamProjects(
    spaces,
    spaces?.find((space) => space.id === teamId),
  );

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.teamProjects.title")} subtitle={t("rework.teamProjects.subtitle")} />
      {memberships.isError ? (
        <span role="alert" className={styles.status}>
          {t("rework.manager.unavailable")}
        </span>
      ) : !memberships.currentData ? (
        <span role="status" className={styles.status}>
          {t("common.loading")}
        </span>
      ) : projects.length === 0 ? (
        <PageEmptyState icon="assignment" message={t("rework.teamProjects.empty")} />
      ) : (
        <ul className={styles.grid}>
          {projects.map((project) => (
            <li key={project.id} className={styles.item}>
              <SelectableCard
                icon="assignment"
                title={project.name}
                description={project.description ?? teamRoleLabel(project.roles, t)}
                onSelect={() => navigate(`/team/${project.id}`)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
