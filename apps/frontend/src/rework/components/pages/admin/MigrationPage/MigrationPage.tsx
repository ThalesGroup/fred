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
import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { useDropzone } from "react-dropzone";
import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { TaskCard } from "@shared/molecules/TaskCard/TaskCard";
import { selectVisibleTasks, taskRegistered } from "../../../../features/tasks/taskSlice";
import { launchPlatformImport } from "../../../../features/migration/launchPlatformImport";
import styles from "./MigrationPage.module.css";

export default function MigrationPage() {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const tasks = useSelector(selectVisibleTasks);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [isLaunching, setIsLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const migrationTasks = useMemo(() => tasks.filter((t) => t.kind === "migration"), [tasks]);
  const activeTasks = migrationTasks.filter(
    (t) => t.state === "running" || t.state === "pending" || t.state === "cancelling",
  );
  const terminalTasks = migrationTasks.filter(
    (t) => t.state === "succeeded" || t.state === "failed" || t.state === "cancelled",
  );

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

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.tasks.migration.title")}</h1>
      </div>

      <section className={styles.uploadCard}>
        <div {...getRootProps()} className={styles.dropzone} data-active={isDragActive}>
          <input {...getInputProps()} />
          <span className={styles.dropIcon}>📦</span>
          <span>{file ? file.name : t("rework.tasks.migration.dropzone")}</span>
        </div>

        <TextInput
          label={t("rework.tasks.migration.label")}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder={t("rework.tasks.migration.labelPlaceholder")}
          disabled={isLaunching}
        />

        {error && <span className={styles.errorText}>{error}</span>}

        <div className={styles.actions}>
          <Button color="primary" variant="filled" size="medium" onClick={handleLaunch} disabled={!file || isLaunching}>
            {isLaunching ? t("rework.tasks.migration.launching") : t("rework.tasks.migration.launch")}
          </Button>
        </div>
      </section>

      {migrationTasks.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>✓</span>
          <span>{t("rework.tasks.migration.empty")}</span>
        </div>
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}
