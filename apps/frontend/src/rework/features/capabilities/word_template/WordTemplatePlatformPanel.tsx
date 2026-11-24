import type { Library } from "../../../../slices/controlPlane/controlPlaneOpenApi";
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useResolveWordTemplateLibraryQuery,
  useSaveWordTemplateLibraryMutation,
  useUploadWordTemplateMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { CapabilityPlatformPanelProps } from "../types";
import { WordTemplateLibraryEditor } from "./WordTemplateLibraryEditor";
import {
  addTemplateFiles,
  removeTemplateEntry,
  templateLibraryRowProblems,
  updateTemplateLabel,
  type TemplateLibraryState,
} from "./templateLibrary";
import { libraryEntries, stageWordLibrary } from "./librarySave";

export function WordTemplatePlatformPanel({ organizationId, runtimeId, canManage }: CapabilityPlatformPanelProps) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const query = useResolveWordTemplateLibraryQuery(
    { spaceId: organizationId, runtimeId },
    { skip: !canManage || !runtimeId, pollingInterval: 3000 },
  );
  const [upload] = useUploadWordTemplateMutation();
  const [save, saving] = useSaveWordTemplateLibraryMutation();
  const [draft, setDraft] = useState<TemplateLibraryState | null>(null);
  const [baseline, setBaseline] = useState<Library>();
  const change = (next: TemplateLibraryState) => {
    if (!draft) setBaseline(query.currentData);
    setDraft(next);
  };
  const [uploading, setUploading] = useState(false);
  const current = draft ?? { entries: libraryEntries(query.currentData), files: [] };
  const problems = templateLibraryRowProblems(current.entries);
  const busy = uploading || saving.isLoading;
  const persist = async () => {
    setUploading(true);
    try {
      const libraryChange = await stageWordLibrary({
        spaceId: organizationId,
        runtimeId,
        ...current,
        previous: baseline,
        upload: (arg) => upload(arg).unwrap(),
      });
      await save({ spaceId: organizationId, runtimeId, libraryChange }).unwrap();
      await query.refetch();
      setDraft(null);
      setBaseline(undefined);
      showSuccess({ summary: t("capability.word_template.platform.started") });
    } catch (error) {
      showError({ summary: t("capability.word_template.platform.uploadError"), detail: String(error) });
    } finally {
      setUploading(false);
    }
  };
  const retry = async () => {
    const library = query.currentData;
    if (!library || draft || !canManage || busy) return;
    try {
      await save({
        spaceId: organizationId,
        runtimeId,
        libraryChange: {
          files: library.files.map(({ file, label }) => ({ file_id: file.id, label })),
          expected_file_ids: library.own_file_ids,
        },
      }).unwrap();
      await query.refetch();
      showSuccess({ summary: t("capability.word_template.platform.started") });
    } catch (error) {
      showError({ summary: t("capability.word_template.preparation.retryError"), detail: String(error) });
    }
  };
  if (query.isError) return <p role="alert">{t("capability.word_template.platform.loadError")}</p>;
  return (
    <WordTemplateLibraryEditor
      items={current.entries.map((entry, index) => ({
        key: entry.template_key ?? String(index),
        name: entry.label,
        detail: entry.filename ?? undefined,
      }))}
      labels={{
        title: t("capability.word_template.form.title"),
        empty: t("capability.word_template.form.empty"),
        edit: (name) => t("capability.word_template.form.editOne", { name }),
        editHint: "",
        upload: t("capability.word_template.form.upload"),
        uploadAria: t("capability.word_template.form.uploadAria"),
        remove: (name) => t("capability.word_template.form.removeAria", { label: name }),
        count: t("capability.word_template.form.count", { count: current.entries.length }),
        save: t("capability.word_template.form.saveName"),
        cancel: t("capability.word_template.form.cancel"),
        nameField: t("capability.word_template.form.labelField"),
      }}
      canEdit={canManage}
      disabled={busy || query.isLoading}
      onAdd={(files) => change(addTemplateFiles(current, files))}
      onRemove={(index) => change(removeTemplateEntry(current, index))}
      onRename={(index, label) => change({ ...current, entries: updateTemplateLabel(current.entries, index, label) })}
      errors={
        <>
          {problems.some(Boolean) && <p role="alert">{t("capability.word_template.form.duplicateLabel")}</p>}
          {current.entries.length > 8 && <p role="alert">{t("capability.word_template.form.tooMany")}</p>}
        </>
      }
      status={
        <>
          {query.currentData?.files.map(({ file, label, preparation_state, preparation_error }) => (
            <p key={file.id} role="status">
              {label}: {t(`capability.word_template.preparation.${preparation_state}`)} {preparation_error}
            </p>
          ))}
          {canManage && !draft && query.currentData?.files.some((file) => file.preparation_state === "failed") && (
            <Button color="primary" variant="outlined" size="small" disabled={busy} onClick={() => void retry()}>
              {t("capability.word_template.preparation.retry")}
            </Button>
          )}
          {canManage && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={!draft || busy || current.entries.length > 8 || problems.some(Boolean)}
              onClick={() => void persist()}
            >
              {t("common.save")}
            </Button>
          )}
        </>
      }
    />
  );
}
