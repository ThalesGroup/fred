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

import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { useDropzone } from "react-dropzone";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { TaskCard } from "@shared/molecules/TaskCard/TaskCard";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import KpiStatCard from "@shared/molecules/KpiStatCard/KpiStatCard.tsx";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import {
  usePlatformStatsQuery,
  useResetPlatformMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { TeamStats } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { selectVisibleTasks, taskRegistered } from "../../../../features/tasks/taskSlice";
import { launchPlatformImport } from "../../../../features/migration/launchPlatformImport";
import { exportPlatform } from "../../../../features/migration/exportPlatform";
import styles from "./MigrationPage.module.css";

export default function MigrationPage() {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const tasks = useSelector(selectVisibleTasks);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [isLaunching, setIsLaunching] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: stats, isFetching: statsLoading, isError: statsError, refetch: refetchStats } = usePlatformStatsQuery();
  const [resetPlatform, { isLoading: isResetting }] = useResetPlatformMutation();

  const migrationTasks = useMemo(() => tasks.filter((t) => t.kind === "migration"), [tasks]);
  const activeTasks = migrationTasks.filter(
    (t) => t.state === "running" || t.state === "pending" || t.state === "cancelling",
  );
  const terminalTasks = migrationTasks.filter(
    (t) => t.state === "succeeded" || t.state === "failed" || t.state === "cancelled",
  );

  // Refresh the summary whenever an import/reset/export task settles (the
  // terminal task count grows) so the panel mirrors the live DB state.
  const terminalCount = terminalTasks.length;
  useEffect(() => {
    void refetchStats();
  }, [refetchStats, terminalCount]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    noKeyboard: true,
    multiple: false,
    accept: [".zip", "application/zip", "application/x-zip-compressed"],
    onDrop: (accepted) => {
      if (accepted.length > 0) {
        setFile(accepted[0]);
        setError(null);
      }
    },
  });

  const handleResetConfirmed = async () => {
    setShowResetConfirm(false);
    setError(null);
    try {
      const { task_id } = await resetPlatform().unwrap();
      dispatch(
        taskRegistered({
          taskId: task_id,
          kind: "migration",
          target: { type: "platform", id: task_id, label: t("rework.tasks.migration.reset.taskLabel") },
        }),
      );
    } catch {
      setError(t("rework.tasks.migration.reset.error"));
    }
  };

  const handleExport = async () => {
    if (isExporting) return;
    setIsExporting(true);
    setError(null);
    try {
      await exportPlatform();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsExporting(false);
    }
  };

  const handleLaunch = async () => {
    if (!file || isLaunching) return;
    setIsLaunching(true);
    setError(null);
    try {
      const { taskId, importId } = await launchPlatformImport(file, label);
      dispatch(
        taskRegistered({
          taskId,
          kind: "migration",
          target: { type: "platform", id: importId, label: file.name },
        }),
      );
      setFile(null);
      setLabel("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLaunching(false);
    }
  };

  const teamColumns: DataTableColumn<TeamStats>[] = [
    { label: t("rework.tasks.migration.stats.col.team"), size: "2fr", cellRenderer: (r) => r.name },
    { label: t("rework.tasks.migration.stats.col.admins"), cellRenderer: (r) => r.admins },
    { label: t("rework.tasks.migration.stats.col.editors"), cellRenderer: (r) => r.editors },
    { label: t("rework.tasks.migration.stats.col.analysts"), cellRenderer: (r) => r.analysts },
    { label: t("rework.tasks.migration.stats.col.members"), cellRenderer: (r) => r.members },
    { label: t("rework.tasks.migration.stats.col.agents"), cellRenderer: (r) => r.agents },
    { label: t("rework.tasks.migration.stats.col.prompts"), cellRenderer: (r) => r.prompts },
  ];

  return (
    <div className={styles.page}>
      <section className={styles.overview}>
        <div className={styles.overviewHeader}>
          <span className={styles.overviewTitle}>{t("rework.tasks.migration.stats.title")}</span>
          <IconButton
            color="on-surface"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "refresh", filled: false }}
            onClick={() => void refetchStats()}
            disabled={statsLoading}
            title={t("rework.tasks.migration.stats.refresh")}
          />
        </div>
        <div className={styles.kpiGrid}>
          <KpiStatCard
            label={t("rework.tasks.migration.stats.teams")}
            value={stats?.teams}
            isLoading={statsLoading}
            isError={statsError}
          />
          <KpiStatCard
            label={t("rework.tasks.migration.stats.members")}
            value={stats?.distinct_users}
            isLoading={statsLoading}
            isError={statsError}
          />
          <KpiStatCard
            label={t("rework.tasks.migration.stats.agents")}
            value={stats?.total_agents}
            isLoading={statsLoading}
            isError={statsError}
          />
          <KpiStatCard
            label={t("rework.tasks.migration.stats.prompts")}
            value={stats?.total_prompts}
            isLoading={statsLoading}
            isError={statsError}
          />
        </div>
        {stats && stats.per_team.length > 0 && <DataTable columns={teamColumns} data={stats.per_team} />}
      </section>

      <div className={styles.cards}>
        {/* ── Import ─────────────────────────────────────────── */}
        <section className={styles.card}>
          <div className={styles.cardHead}>
            <Icon category="outlined" type="upload" />
            <span className={styles.cardTitle}>{t("rework.tasks.migration.import.title")}</span>
          </div>

          <div {...getRootProps()} className={styles.dropzone} data-active={isDragActive}>
            <input {...getInputProps()} />
            <Icon category="outlined" type="folder" />
            <span>{file ? file.name : t("rework.tasks.migration.dropzone")}</span>
          </div>

          <TextInput
            label={t("rework.tasks.migration.label")}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={t("rework.tasks.migration.labelPlaceholder")}
            disabled={isLaunching}
          />

          <div className={styles.actions}>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              onClick={handleLaunch}
              disabled={!file || isLaunching}
            >
              {isLaunching ? t("rework.tasks.migration.launching") : t("rework.tasks.migration.launch")}
            </Button>
          </div>
        </section>

        {/* ── Export ─────────────────────────────────────────── */}
        <section className={styles.card}>
          <div className={styles.cardHead}>
            <Icon category="outlined" type="download" />
            <span className={styles.cardTitle}>{t("rework.tasks.migration.export.title")}</span>
          </div>

          <p className={styles.cardBody}>{t("rework.tasks.migration.export.description")}</p>

          <div className={styles.actions}>
            <Button color="primary" variant="filled" size="medium" onClick={handleExport} disabled={isExporting}>
              {isExporting ? t("rework.tasks.migration.export.launching") : t("rework.tasks.migration.export.launch")}
            </Button>
          </div>
        </section>
      </div>

      {error && <span className={styles.errorText}>{error}</span>}

      {activeTasks.length > 0 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("rework.tasks.page.active")}</h2>
          <div className={styles.grid}>
            {activeTasks.map((task) => (
              <TaskCard key={task.taskId} task={task} />
            ))}
          </div>
        </section>
      )}

      {terminalTasks.length > 0 && (
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>{t("rework.tasks.page.terminal")}</h2>
          <div className={styles.grid}>
            {terminalTasks.map((task) => (
              <TaskCard key={task.taskId} task={task} />
            ))}
          </div>
        </section>
      )}

      <div className={styles.dangerZone}>
        <Button
          color="error"
          variant="outlined"
          size="medium"
          onClick={() => setShowResetConfirm(true)}
          disabled={isResetting}
        >
          {isResetting ? t("rework.tasks.migration.reset.running") : t("rework.tasks.migration.reset.launch")}
        </Button>
      </div>

      <ConfirmationDialog
        open={showResetConfirm}
        title={t("rework.tasks.migration.reset.confirmTitle")}
        message={t("rework.tasks.migration.reset.confirmMessage")}
        confirmLabel={t("rework.tasks.migration.reset.confirmLabel")}
        cancelLabel={t("rework.tasks.migration.reset.cancelLabel")}
        criticalAction
        onConfirm={handleResetConfirmed}
        onCancel={() => setShowResetConfirm(false)}
      />
    </div>
  );
}
