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

// Agent template names travel as config; new files use the matching asset slot.

import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { useResolveWordTemplateLibraryQuery as useLibrary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import type { CapabilityConfigWidgetProps } from "../types";
import { WordTemplateLibraryEditor, type LibraryItem } from "./WordTemplateLibraryEditor";
import {
  addTemplateFiles,
  readTemplateLibrary,
  removeTemplateEntry,
  stagedLibraryFiles,
  stagedTemplateFileKey,
  TEMPLATE_LIBRARY_SLOT,
  templateLibraryRowProblems,
  type TemplateLibraryState,
  updateTemplateLabel,
} from "./templateLibrary";
import styles from "./WordTemplateLibraryForm.module.css";
import { libraryEntries } from "./librarySave";
import { WordTemplatePreparationStatus } from "./WordTemplatePreparationStatus";

export function WordTemplateLibraryForm({
  disabled,
  configValues,
  onConfigChange,
  assetFiles,
  onAssetFileChange,
  onBlockingErrorChange,
  teamId,
  agentInstanceId,
  runtimeId,
}: CapabilityConfigWidgetProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();
  const entries = useMemo(() => readTemplateLibrary(configValues.template_library), [configValues.template_library]);
  const platformSelection = useLibrary(
    { spaceId: teamId ?? "", agentInstanceId, runtimeId },
    { skip: !teamId || (!agentInstanceId && !runtimeId), refetchOnMountOrArgChange: true, pollingInterval: 3000 },
  );
  const initialized = useRef(false);
  useEffect(() => {
    if (!initialized.current && platformSelection.currentData) {
      initialized.current = true;
      if (platformSelection.currentData.source === "agent")
        onConfigChange("template_library", libraryEntries(platformSelection.currentData));
    }
  }, [platformSelection.currentData, onConfigChange]);
  const platformItems: LibraryItem[] =
    platformSelection.currentData?.source === "organization"
      ? platformSelection.currentData.files.map(({ file, label }) => ({ key: file.id, name: label, readOnly: true }))
      : [];
  const files = stagedLibraryFiles(assetFiles[TEMPLATE_LIBRARY_SLOT]);
  const rowProblems = templateLibraryRowProblems(entries);

  const itemsFor = (library: TemplateLibraryState, problems: (string | null)[] = []): LibraryItem[] =>
    library.entries.map((entry, index) => {
      const stagedFile = entry.template_key
        ? undefined
        : library.files[library.entries.slice(0, index).filter((item) => !item.template_key).length];
      return {
        key: entry.template_key ?? (stagedFile ? stagedTemplateFileKey(stagedFile) : `missing-${index}`),
        name: entry.label,
        detail: stagedFile?.name ?? entry.filename ?? undefined,
        error: problems[index] ? t(`capability.word_template.form.row.${problems[index]}`) : undefined,
      };
    });
  const commit = (next: TemplateLibraryState) => {
    onConfigChange("template_library", next.entries);
    onAssetFileChange(TEMPLATE_LIBRARY_SLOT, next.files.length > 0 ? next.files : null);
  };

  const firstProblem = rowProblems.find((p) => p !== null) ?? null;
  const blockingError =
    entries.length > 8
      ? t("capability.word_template.form.tooMany", { agentsNicknameSingular })
      : firstProblem
        ? t(`capability.word_template.form.${firstProblem}`)
        : null;

  useEffect(() => {
    onBlockingErrorChange(blockingError);
    // Clearing on unmount keeps a deselected capability from blocking Save.
    return () => onBlockingErrorChange(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockingError]);

  return (
    <WordTemplateLibraryEditor
      items={entries.length ? itemsFor({ entries, files }, rowProblems) : platformItems}
      labels={{
        title: t(`capability.word_template.form.${platformItems.length ? "platformTitle" : "title"}`),
        empty: t("capability.word_template.form.empty"),
        edit: (name) => t("capability.word_template.form.editOne", { name }),
        editHint: "",
        upload: t("capability.word_template.form.upload"),
        uploadAria: t("capability.word_template.form.uploadAria", { agentsNicknameSingular }),
        remove: (name) => t("capability.word_template.form.removeAria", { label: name }),
        count: t("capability.word_template.form.count", { count: entries.length }),
        save: t("capability.word_template.form.saveName"),
        cancel: t("capability.word_template.form.cancel"),
        nameField: t("capability.word_template.form.labelField"),
      }}
      description={
        entries.length ? (
          <p className={styles.description}>
            {t("capability.word_template.form.description", { agentsNicknameSingular })}
          </p>
        ) : platformItems.length ? (
          <ServiceNotice color="info" compact title={t("capability.word_template.form.platformDescription")} />
        ) : undefined
      }
      canEdit
      disabled={disabled || (!!teamId && !platformSelection.currentData)}
      onAdd={(picked) => commit(addTemplateFiles({ entries, files }, picked))}
      onRemove={(index) => commit(removeTemplateEntry({ entries, files }, index))}
      onRename={(index, label) => onConfigChange("template_library", updateTemplateLabel(entries, index, label))}
      errors={
        <>
          {entries.length > 8 && (
            <p className={styles.error} role="alert">
              {t("capability.word_template.form.tooMany", { agentsNicknameSingular })}
            </p>
          )}
          {files.some((file) => !/\.docx$/i.test(file.name)) && (
            <p className={styles.error} role="alert">
              {t("capability.word_template.form.invalidType")}
            </p>
          )}
        </>
      }
      status={
        <>
          {blockingError && (
            <p className={styles.error} role="alert">
              {blockingError}
            </p>
          )}
          {entries.length === 0 && platformSelection.isLoading && (
            <p className={styles.description} role="status">
              {t("capability.word_template.form.platformLoading")}
            </p>
          )}
          {entries.length === 0 && platformSelection.isError && (
            <p className={styles.error} role="alert">
              {t("capability.word_template.form.platformLoadError")}
            </p>
          )}
          <WordTemplatePreparationStatus
            teamId={teamId}
            agentInstanceId={agentInstanceId}
            staged={files.length > 0}
            hasLibrary={entries.length > 0}
            disabled={disabled}
          />
        </>
      }
    />
  );
}
