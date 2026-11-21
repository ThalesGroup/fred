// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
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
import styles from "./WordTemplateLibraryForm.module.css";

const SLOT = "word_template_library";
const K = "capability.word_template.platform";

const labelOf = (name: string) => name.replace(/\.docx$/i, "");
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
      template_labels: [
        ...retained.map((asset) => labelOf(asset.filename)),
        ...files.map((file) => labelOf(file.name)),
      ],
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
  const input = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState(false);
  const [retained, setRetained] = useState<PreparationAsset[]>([]);
  const [added, setAdded] = useState<File[]>([]);
  const [openedActiveId, setOpenedActiveId] = useState<string | undefined>();
  const [uploading, setUploading] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetExpectedId, setResetExpectedId] = useState<string | null>(null);
  const args = { runtimeId: capability.runtime_id, capabilityId: "word_template", slotKey: SLOT };
  const selection = useSelection(args, { pollingInterval: 3000 });
  const [retry, retryState] = useRetry();
  const [reset, resetState] = useReset();
  const active = selection.data?.active;
  const candidate = selection.data?.candidate;
  const busy = uploading || retryState.isLoading || resetState.isLoading;
  const names = [...retained.map((asset) => asset.filename), ...added.map((file) => file.name)];
  const invalidType = names.some((name) => !/\.docx$/i.test(name));
  const duplicateName = new Set(names.map((name) => normalizedLabel(labelOf(name)))).size !== names.length;
  const overLimit = names.length > 8;
  const unchanged =
    added.length === 0 &&
    retained.map((asset) => asset.asset_id).join() === (active?.assets ?? []).map((asset) => asset.asset_id).join();

  const openEditor = () => {
    setOpenedActiveId(active?.preparation_id);
    setRetained(active?.assets ?? []);
    setAdded([]);
    setEditing(true);
  };

  const save = async () => {
    if (names.length === 0) {
      setEditing(false);
      setResetExpectedId(openedActiveId ?? "");
      setConfirmReset(true);
      return;
    }
    if (invalidType || duplicateName || overLimit || unchanged) return;
    setUploading(true);
    try {
      await uploadTemplates(capability.runtime_id, openedActiveId, retained, added);
      await selection.refetch();
      setEditing(false);
      showSuccess({ summary: t(`${K}.started`) });
    } catch (error) {
      await selection.refetch().catch(() => undefined);
      const stale = error instanceof Error && error.message === "stale";
      if (stale) setEditing(false);
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
      <div className={styles.settingCard}>
        <div className={styles.uploadRow} role="group" aria-label={t(`${K}.libraryTitle`)}>
          {active?.assets?.length ? (
            active.assets.map((asset) => (
              <Chip
                key={asset.asset_id}
                label={asset.filename}
                leading={<Icon category="outlined" type="description" />}
              />
            ))
          ) : (
            <Chip label={t(`${K}.empty`)} leading={<Icon category="outlined" type="description" />} />
          )}
          {canManage && (
            <>
              <Button
                color="primary"
                variant="outlined"
                size="small"
                disabled={busy}
                icon={{ category: "outlined", type: "upload" }}
                onClick={openEditor}
              >
                {t(`${K}.upload`)}
              </Button>
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "edit" }}
                aria-label={t(`${K}.edit`)}
                disabled={busy}
                onClick={openEditor}
              />
            </>
          )}
        </div>
        {candidate && (
          <p
            className={candidate.state === "failed" ? styles.error : styles.status}
            role={candidate.state === "failed" ? "alert" : "status"}
          >
            {candidate.state === "pending" || candidate.state === "running" ? <Spinner size={16} /> : null}
            {t(`${K}.candidate.${candidate.state}`, {
              names: candidate.assets?.map((asset) => asset.filename).join(", ") ?? "",
            })}
          </p>
        )}
      </div>
      <Dialog
        open={editing}
        title={t(`${K}.editTitle`)}
        confirmLabel={t(`${K}.save`)}
        cancelLabel={t(`${K}.cancel`)}
        confirmDisabled={busy || invalidType || duplicateName || overLimit || unchanged}
        onConfirm={() => void save()}
        onCancel={() => setEditing(false)}
        maxWidth={600}
      >
        <div className={styles.root}>
          <p className={styles.description}>{t(`${K}.editHint`)}</p>
          {names.length > 0 ? (
            <ul className={styles.libraryList}>
              {names.map((name, index) => (
                <li className={styles.libraryRow} key={index}>
                  <Icon category="outlined" type="description" />
                  <span className={styles.libraryName}>{name}</span>
                  <DeleteIconButton
                    size="small"
                    disabled={busy}
                    aria-label={t(`${K}.removeOne`, { name })}
                    onClick={() =>
                      index < retained.length
                        ? setRetained(retained.filter((_, position) => position !== index))
                        : setAdded(added.filter((_, position) => position !== index - retained.length))
                    }
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.description}>{t(`${K}.empty`)}</p>
          )}
          <div className={styles.uploadRow}>
            <input
              ref={input}
              className={styles.fileInput}
              type="file"
              accept=".docx"
              multiple
              aria-label={t(`${K}.uploadAria`)}
              disabled={busy}
              onChange={(event) => {
                setAdded((current) => [...current, ...Array.from(event.target.files ?? [])]);
                event.target.value = "";
              }}
            />
            <Button
              color="primary"
              variant="outlined"
              size="small"
              disabled={busy || overLimit}
              icon={{ category: "outlined", type: "upload" }}
              onClick={() => input.current?.click()}
            >
              {t(`${K}.upload`)}
            </Button>
            <span className={styles.description}>{t(`${K}.count`, { count: names.length })}</span>
          </div>
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
        </div>
      </Dialog>
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
