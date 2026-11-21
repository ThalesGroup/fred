// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
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
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { CapabilityPlatformPanelProps } from "../types";
import styles from "./WordTemplateLibraryForm.module.css";

const SLOT = "word_template_library";
const K = "capability.word_template.platform";

const templateLabels = (files: File[]) => files.map((file) => file.name.replace(/\.docx$/i, ""));
const normalizedLabel = (label: string) =>
  label
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");

async function uploadTemplates(runtimeId: string, files: File[]): Promise<PlatformPreparationSelection> {
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
  form.append(
    "config_json",
    JSON.stringify({
      preparation_hashes: hashes,
      template_labels: templateLabels(files),
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
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const args = { runtimeId: capability.runtime_id, capabilityId: "word_template", slotKey: SLOT };
  const selection = useSelection(args, { pollingInterval: 3000 });
  const [retry, retryState] = useRetry();
  const [reset, resetState] = useReset();
  const active = selection.data?.active;
  const candidate = selection.data?.candidate;
  const busy = uploading || retryState.isLoading || resetState.isLoading;

  const pick = async (files: File[]) => {
    setUploading(true);
    try {
      if (files.length > 8) throw new Error(t(`${K}.tooMany`));
      const labels = templateLabels(files);
      if (new Set(labels.map(normalizedLabel)).size !== labels.length) throw new Error(t(`${K}.duplicateName`));
      await uploadTemplates(capability.runtime_id, files);
      await selection.refetch();
      showSuccess({ summary: t(`${K}.started`) });
    } catch (error) {
      showError({ summary: t(`${K}.uploadError`), detail: error instanceof Error ? error.message : String(error) });
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
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
      await reset(args).unwrap();
      await selection.refetch();
    } catch (error) {
      showError({ summary: t(`${K}.resetError`), detail: String(error) });
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
      <p>
        {active
          ? t(`${K}.active`, { names: active.assets?.map((asset) => asset.filename).join(", ") ?? "" })
          : t(`${K}.empty`)}
      </p>
      {candidate && (
        <p role="status">
          {candidate.state === "pending" || candidate.state === "running" ? <Spinner size={16} /> : null}
          {t(`${K}.candidate.${candidate.state}`, {
            names: candidate.assets?.map((asset) => asset.filename).join(", ") ?? "",
          })}
        </p>
      )}
      {canManage && (
        <div className={styles.sectionHeader}>
          <input
            ref={input}
            type="file"
            accept=".docx"
            multiple
            aria-label={t(`${K}.uploadAria`)}
            disabled={busy}
            hidden
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length) void pick(files);
            }}
          />
          <Button
            color="primary"
            variant="outlined"
            size="small"
            disabled={busy}
            onClick={() => input.current?.click()}
          >
            {t(active ? `${K}.replace` : `${K}.upload`)}
          </Button>
          {candidate?.state === "failed" && (
            <Button
              color="on-surface"
              variant="text"
              size="small"
              disabled={busy}
              onClick={() => void retryCandidate()}
            >
              {t(`${K}.retry`)}
            </Button>
          )}
          {active && (
            <Button
              color="on-surface"
              variant="text"
              size="small"
              disabled={busy}
              onClick={() => setConfirmReset(true)}
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
