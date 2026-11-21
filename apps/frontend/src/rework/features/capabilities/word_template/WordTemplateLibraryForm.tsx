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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import type { CapabilityConfigWidgetProps } from "../types";
import { WordTemplateLibraryEditor, type LibraryItem } from "./WordTemplateLibraryEditor";
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
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<TemplateLibraryState>({ entries: [], files: [] });

  const entries = useMemo(() => readTemplateLibrary(configValues.template_library), [configValues.template_library]);
  const files = stagedLibraryFiles(assetFiles[TEMPLATE_LIBRARY_SLOT]);
  const rowProblems = templateLibraryRowProblems(entries);

  const itemsFor = (library: TemplateLibraryState, problems: (string | null)[] = []): LibraryItem[] =>
    library.entries.map((entry, index) => {
      const stagedFile = entry.template_key
        ? undefined
        : library.files[library.entries.slice(0, index).filter((item) => !item.template_key).length];
      return {
        key: entry.template_key ?? `new-${index}`,
        name: entry.label,
        detail: stagedFile?.name ?? t("capability.word_template.form.storedFile"),
        error: problems[index] ? t(`capability.word_template.form.row.${problems[index]}`) : undefined,
      };
    });
  const draftProblems = templateLibraryRowProblems(draft.entries);
  const draftInvalidType = draft.files.some((file) => !/\.docx$/i.test(file.name));
  const draftOverLimit = draft.entries.length > 8;
  const draftChanged =
    JSON.stringify(draft.entries) !== JSON.stringify(entries) ||
    draft.files.length !== files.length ||
    draft.files.some((file, index) => file !== files[index]);

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
      items={itemsFor({ entries, files }, rowProblems)}
      draftItems={itemsFor(draft, draftProblems)}
      labels={{
        title: t("capability.word_template.form.title"),
        empty: t("capability.word_template.form.empty"),
        edit: t("capability.word_template.form.edit"),
        editTitle: t("capability.word_template.form.editTitle", { agentsNicknameSingular }),
        editHint: t("capability.word_template.form.editHint", { agentsNicknameSingular }),
        upload: t("capability.word_template.form.upload"),
        uploadAria: t("capability.word_template.form.uploadAria", { agentsNicknameSingular }),
        remove: (name) => t("capability.word_template.form.removeAria", { label: name }),
        count: t("capability.word_template.form.count", { count: draft.entries.length }),
        save: t("capability.word_template.form.apply"),
        cancel: t("capability.word_template.form.cancel"),
        nameField: t("capability.word_template.form.labelField"),
      }}
      description={t("capability.word_template.form.description", { agentsNicknameSingular })}
      editing={editing}
      canEdit
      disabled={disabled}
      confirmDisabled={!draftChanged || draftOverLimit || draftInvalidType || draftProblems.some(Boolean)}
      onOpen={() => {
        setDraft({ entries, files });
        setEditing(true);
      }}
      onCancel={() => setEditing(false)}
      onConfirm={() => {
        commit(draft);
        setEditing(false);
      }}
      onAdd={(picked) => setDraft((current) => addTemplateFiles(current, picked))}
      onRemove={(index) => setDraft((current) => removeTemplateEntry(current, index))}
      onRename={(index, label) =>
        setDraft((current) => ({ ...current, entries: updateTemplateLabel(current.entries, index, label) }))
      }
      errors={
        <>
          {draftOverLimit && (
            <p className={styles.error} role="alert">
              {t("capability.word_template.form.tooMany", { agentsNicknameSingular })}
            </p>
          )}
          {draftInvalidType && (
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
          <WordTemplatePreparationStatus
            teamId={teamId}
            agentInstanceId={agentInstanceId}
            staged={files.length > 0}
            hasLibrary={entries.length > 0}
          />
        </>
      }
    />
  );
}
