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

// The word_template agent-creation widget (`word_template_library`): the
// .docx templates the agent fills and writes, each with a name (prefilled
// from the file name). Entries travel as config (`template_library`), files
// as the multi-file `word_template_library` slot - see templateLibrary.ts for
// the pairing.

import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import Icon from "@shared/atoms/Icon/Icon";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import type { CapabilityConfigWidgetProps } from "../types";
import {
  addTemplateFiles,
  readTemplateLibrary,
  removeTemplateEntry,
  stagedLibraryFiles,
  TEMPLATE_LIBRARY_SLOT,
  templateLibraryRowProblems,
  type TemplateLibraryState,
  updateTemplateLabel,
} from "./templateLibrary";
import styles from "./WordTemplateLibraryForm.module.css";
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
}: CapabilityConfigWidgetProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const entries = useMemo(() => readTemplateLibrary(configValues.template_library), [configValues.template_library]);
  const files = stagedLibraryFiles(assetFiles[TEMPLATE_LIBRARY_SLOT]);
  const rowProblems = templateLibraryRowProblems(entries);
  // Each keyless (new) entry's staged file, by its position among new entries.
  const stagedFileByRow = entries.map((entry, index) =>
    entry.template_key ? undefined : files[entries.slice(0, index).filter((e) => !e.template_key).length],
  );

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
    <div className={`${styles.root} ${styles.settingCard}`}>
      <div className={styles.sectionHeader}>
        <span className={styles.sectionTitle}>{t("capability.word_template.form.title")}</span>
        {entries.length > 0 && <span className={styles.countBadge}>{entries.length}</span>}
      </div>
      <p className={styles.description}>{t("capability.word_template.form.description", { agentsNicknameSingular })}</p>
      <div className={styles.uploadRow}>
        <input
          ref={fileInputRef}
          className={styles.fileInput}
          type="file"
          accept=".docx"
          multiple
          disabled={disabled || entries.length >= 8}
          aria-label={t("capability.word_template.form.uploadAria", { agentsNicknameSingular })}
          onChange={(event) => {
            const picked = Array.from(event.target.files ?? []);
            if (picked.length) commit(addTemplateFiles({ entries, files }, picked));
            event.target.value = "";
          }}
        />
        <Button
          type="button"
          color="primary"
          variant="outlined"
          size="small"
          disabled={disabled || entries.length >= 8}
          icon={{ category: "outlined", type: "upload" }}
          onClick={() => fileInputRef.current?.click()}
        >
          {t("capability.word_template.form.upload")}
        </Button>
      </div>
      {entries.length > 0 && (
        <ul className={styles.libraryList}>
          {entries.map((entry, index) => {
            const stagedFile = stagedFileByRow[index];
            const problem = rowProblems[index];
            return (
              <li key={entry.template_key ?? `new-${index}`} className={styles.libraryRow}>
                <Icon category="outlined" type="description" />
                <div className={styles.libraryName}>
                  <TextInput
                    compact
                    value={entry.label}
                    disabled={disabled}
                    aria-label={t("capability.word_template.form.labelField")}
                    error={problem ? t(`capability.word_template.form.row.${problem}`) : undefined}
                    onChange={(event) =>
                      onConfigChange("template_library", updateTemplateLabel(entries, index, event.target.value))
                    }
                  />
                </div>
                <span className={styles.libraryFile} title={stagedFile?.name}>
                  {stagedFile ? (
                    stagedFile.name
                  ) : (
                    <>
                      <Icon category="outlined" type="check_circle" />
                      {t("capability.word_template.form.storedFile")}
                    </>
                  )}
                </span>
                <DeleteIconButton
                  size="small"
                  disabled={disabled}
                  aria-label={t("capability.word_template.form.removeAria", { label: entry.label })}
                  onClick={() => commit(removeTemplateEntry({ entries, files }, index))}
                />
              </li>
            );
          })}
        </ul>
      )}
      {entries.length > 8 && (
        <p className={styles.error} role="alert">
          {t("capability.word_template.form.tooMany", { agentsNicknameSingular })}
        </p>
      )}
      <WordTemplatePreparationStatus
        teamId={teamId}
        agentInstanceId={agentInstanceId}
        staged={files.length > 0}
        hasLibrary={entries.length > 0}
      />
    </div>
  );
}
