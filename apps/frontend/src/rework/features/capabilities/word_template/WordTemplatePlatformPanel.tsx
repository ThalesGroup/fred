// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { handlePlatformAccessResponse } from "../../../../common/platformAccess";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { KeyCloakService } from "../../../../security/KeycloakService";
import {
  useDeletePlatformCapabilityPreparationControlPlaneV1PlatformCapabilityPreparationsRuntimeIdCapabilityIdSlotKeyDeleteMutation as useReset,
  useGetPlatformCapabilityPreparationControlPlaneV1PlatformCapabilityPreparationsRuntimeIdCapabilityIdSlotKeyGetQuery as useSelection,
  usePostPlatformCapabilityCandidateRetryControlPlaneV1PlatformCapabilityPreparationsRuntimeIdCapabilityIdSlotKeyCandidateRetryPostMutation as useRetry,
  type PlatformPreparationSelection,
  type PreparationAsset,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { CapabilityPlatformPanelProps } from "../types";
import { WordTemplateLibraryEditor } from "./WordTemplateLibraryEditor";
import { stagedTemplateFileKey } from "./templateLibrary";
import styles from "./WordTemplateLibraryForm.module.css";

const SLOT = "word_template_library";
const K = "capability.word_template.platform";

const labelOf = (name: string) => name.replace(/\.docx$/i, "");
const labelsOf = (assets: PreparationAsset[], publicConfig: Record<string, unknown> | undefined): string[] => {
  const labels = publicConfig?.template_labels;
  return assets.map((asset, index) =>
    Array.isArray(labels) && typeof labels[index] === "string" ? labels[index] : labelOf(asset.filename),
  );
};
interface LibraryDraft {
  retained: PreparationAsset[];
  added: File[];
  labels: string[];
  activeId: string | undefined;
}
const normalizedLabel = (label: string) =>
  label
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");

async function uploadTemplates(
  runtimeId: string,
  activeId: string | undefined,
  retained: PreparationAsset[],
  files: File[],
  labels: string[],
): Promise<PlatformPreparationSelection> {
  const hashes = await Promise.all(
    files.map(async (file) => {
      const bytes = await file.arrayBuffer();
      return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    }),
  );
  const form = new FormData();
  files.forEach((file) => form.append("file", file));
  form.append("retained_asset_ids_json", JSON.stringify(retained.map((asset) => asset.asset_id)));
  form.append("expected_active_preparation_id", activeId ?? "");
  form.append(
    "config_json",
    JSON.stringify({
      preparation_hashes: [...retained.map((asset) => asset.sha256), ...hashes],
      template_labels: labels,
    }),
  );
  const response = await fetch(
    `/control-plane/v1/platform/capability-preparations/${encodeURIComponent(runtimeId)}/word_template/${SLOT}/candidate`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
      body: form,
    },
  );
  await handlePlatformAccessResponse(response);
  if (response.status === 409) throw new Error("stale");
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : "");
  }
  return (await response.json()) as PlatformPreparationSelection;
}

export function WordTemplatePlatformPanel({ capability, canManage }: CapabilityPlatformPanelProps) {
  const { t } = useTranslation();
  const { siteDisplayName, agentsNicknamePlural } = useFrontendProperties();
  const { showError, showSuccess } = useToast();
  const [draft, setDraft] = useState<LibraryDraft | null>(null);
  const [editorRevision, setEditorRevision] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetExpectedId, setResetExpectedId] = useState<string | null>(null);
  const args = { runtimeId: capability.runtime_id, capabilityId: "word_template", slotKey: SLOT };
  const selection = useSelection(args, { pollingInterval: 3000 });
  const [retry, retryState] = useRetry();
  const [reset, resetState] = useReset();
  const active = selection.data?.active;
  const candidate = selection.data?.candidate;
  const candidateLabels = labelsOf(candidate?.assets ?? [], candidate?.public_config);
  const busy = uploading || retryState.isLoading || resetState.isLoading;
  const original: LibraryDraft = {
    retained: active?.assets ?? [],
    added: [],
    labels: labelsOf(active?.assets ?? [], active?.public_config),
    activeId: active?.preparation_id,
  };
  const current = draft ?? original;
  const { retained, added } = current;
  const names = [...retained.map((asset) => asset.filename), ...added.map((file) => file.name)];
  const invalidType = names.some((name) => !/\.docx$/i.test(name));
  const missingName = current.labels.some((name) => !name.trim());
  const duplicateName = new Set(current.labels.map(normalizedLabel)).size !== current.labels.length;
  const overLimit = names.length > 8;
  const unchanged =
    !!draft &&
    added.length === 0 &&
    retained.map((asset) => asset.asset_id).join() === (active?.assets ?? []).map((asset) => asset.asset_id).join() &&
    current.labels.join() === original.labels.join();

  const save = async () => {
    if (names.length === 0) {
      setResetExpectedId(current.activeId ?? "");
      setConfirmReset(true);
      return;
    }
    if (invalidType || missingName || duplicateName || overLimit || unchanged) return;
    setUploading(true);
    try {
      await uploadTemplates(capability.runtime_id, current.activeId, retained, added, current.labels);
      await selection.refetch();
      setDraft(null);
      setEditorRevision((revision) => revision + 1);
      showSuccess({ summary: t(`${K}.started`) });
    } catch (error) {
      await selection.refetch().catch(() => undefined);
      const stale = error instanceof Error && error.message === "stale";
      if (stale) {
        setDraft(null);
        setEditorRevision((revision) => revision + 1);
      }
      showError({
        summary: t(`${K}.uploadError`),
        detail: stale ? t(`${K}.stale`) : error instanceof Error ? error.message : String(error),
      });
    } finally {
      setUploading(false);
    }
  };

  const retryCandidate = async () => {
    try {
      await retry(args).unwrap();
      await selection.refetch();
    } catch (error) {
      showError({ summary: t(`${K}.retryError`), detail: String(error) });
    }
  };

  const clear = async () => {
    setConfirmReset(false);
    try {
      await reset({ ...args, expectedActivePreparationId: resetExpectedId ?? undefined }).unwrap();
      await selection.refetch();
      setDraft(null);
      setEditorRevision((revision) => revision + 1);
    } catch (error) {
      showError({ summary: t(`${K}.resetError`), detail: String(error) });
    } finally {
      setResetExpectedId(null);
    }
  };

  if (selection.isLoading)
    return (
      <p role="status">
        <Spinner size={16} /> {t(`${K}.loading`)}
      </p>
    );
  if (selection.isError) return <p role="alert">{t(`${K}.loadError`)}</p>;
  return (
    <div className={styles.root}>
      <p className={styles.description}>{t(`${K}.intro`, { siteDisplayName, agentsNicknamePlural })}</p>
      <WordTemplateLibraryEditor
        key={editorRevision}
        items={[
          ...retained.map((asset, index) => ({
            key: asset.asset_id,
            name: current.labels[index],
            detail: asset.filename,
          })),
          ...added.map((file, index) => ({
            key: stagedTemplateFileKey(file),
            name: current.labels[retained.length + index],
            detail: file.name,
          })),
        ]}
        labels={{
          title: t(`${K}.${draft ? "draftTitle" : "activeTitle"}`),
          empty: t(`${K}.empty`),
          edit: (name) => t(`${K}.editOne`, { name }),
          editHint: t(`${K}.editHint`, { agentsNicknamePlural }),
          upload: t(`${K}.upload`),
          uploadAria: t(`${K}.uploadAria`),
          remove: (name) => t(`${K}.removeOne`, { name }),
          count: t(`${K}.count`, { count: names.length }),
          save: t(`${K}.save`),
          cancel: t(`${K}.cancel`),
          nameField: t(`${K}.labelField`),
        }}
        canEdit={canManage}
        disabled={busy}
        dirty={draft !== null}
        saveDisabled={unchanged || invalidType || missingName || duplicateName || overLimit}
        onSave={() => void save()}
        onCancel={() => {
          setDraft(null);
          setEditorRevision((revision) => revision + 1);
        }}
        onStartRename={() => {
          if (!draft) setDraft(current);
        }}
        onAdd={(files) =>
          setDraft({
            ...current,
            added: [...added, ...files],
            labels: [...current.labels, ...files.map((file) => labelOf(file.name))],
          })
        }
        onRemove={(index) =>
          setDraft({
            ...current,
            retained: index < retained.length ? retained.filter((_, position) => position !== index) : retained,
            added:
              index >= retained.length ? added.filter((_, position) => position !== index - retained.length) : added,
            labels: current.labels.filter((_, position) => position !== index),
          })
        }
        onRename={(index, name) =>
          setDraft({
            ...current,
            labels: current.labels.map((label, position) => (position === index ? name : label)),
          })
        }
        status={
          candidate && (
            <div className={styles.candidateLibrary}>
              <div className={styles.sectionHeader}>
                <span className={styles.sectionTitle}>{t(`${K}.candidateTitle`)}</span>
                <span className={styles.countBadge}>{candidate.assets?.length ?? 0}</span>
              </div>
              <div className={styles.uploadRow}>
                {candidate.assets?.map((asset, index) => (
                  <Chip
                    key={`${asset.filename}-${index}`}
                    label={
                      candidateLabels[index] === labelOf(asset.filename)
                        ? asset.filename
                        : `${candidateLabels[index]} (${asset.filename})`
                    }
                    leading={<Icon category="outlined" type="description" />}
                  />
                ))}
              </div>
              <p
                className={candidate.state === "failed" ? styles.error : styles.status}
                role={candidate.state === "failed" ? "alert" : "status"}
              >
                {candidate.state === "pending" || candidate.state === "running" ? <Spinner size={16} /> : null}
                {t(`${K}.candidate.${candidate.state}`)}
              </p>
            </div>
          )
        }
        errors={
          <>
            {overLimit && (
              <p className={styles.error} role="alert">
                {t(`${K}.tooMany`)}
              </p>
            )}
            {duplicateName && (
              <p className={styles.error} role="alert">
                {t(`${K}.duplicateName`)}
              </p>
            )}
            {invalidType && (
              <p className={styles.error} role="alert">
                {t(`${K}.invalidType`)}
              </p>
            )}
            {missingName && (
              <p className={styles.error} role="alert">
                {t(`${K}.missingName`)}
              </p>
            )}
          </>
        }
      />
      {canManage && (candidate?.state === "failed" || active) && (
        <div className={styles.uploadRow}>
          {candidate?.state === "failed" && (
            <Button
              color="on-surface"
              variant="outlined"
              size="small"
              disabled={busy}
              icon={{ category: "outlined", type: "refresh" }}
              onClick={() => void retryCandidate()}
            >
              {t(`${K}.retry`)}
            </Button>
          )}
          {active && (
            <Button
              color="error"
              variant="outlined"
              size="small"
              disabled={busy}
              onClick={() => {
                setResetExpectedId(active.preparation_id);
                setConfirmReset(true);
              }}
            >
              {t(`${K}.reset`)}
            </Button>
          )}
        </div>
      )}
      <ConfirmationDialog
        open={confirmReset}
        title={t(`${K}.resetConfirm.title`, { siteDisplayName })}
        message={t(`${K}.resetConfirm.message`, { agentsNicknamePlural })}
        confirmLabel={t(`${K}.resetConfirm.confirm`)}
        cancelLabel={t(`${K}.resetConfirm.cancel`)}
        criticalAction
        onConfirm={() => void clear()}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
}
