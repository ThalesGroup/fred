// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import Button from "@shared/atoms/Button/Button";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import IconButton from "@shared/atoms/IconButton/IconButton";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Select from "@shared/molecules/Select/Select";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useReplaceModelComplementsMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ModelMetadata, StoredModelOffer } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import { safeHttpUrl } from "../../../../utils/externalUrl";
import styles from "./ModelCatalog.module.css";

const fields = {
  display_name: "text",
  chat: "boolean",
  embedding: "boolean",
  audio_transcription: "boolean",
  vision: "boolean",
  tool_calling: "boolean",
  structured_output: "boolean",
  reasoning: "boolean",
  reasoning_required: "boolean",
  reasoning_efforts: "list",
  reasoning_default: "text",
  reasoning_transport: "text",
  reasoning_replay: "text",
  context_window_tokens: "number",
  max_input_tokens: "number",
  max_output_tokens: "number",
} as const;
const enumChoices: Record<string, string[]> = {
  reasoning_transport: ["responses", "reasoning_content", "content_blocks", "text_tags"],
  reasoning_replay: ["server_reference", "opaque_items", "assistant_message", "none"],
};
const usageFields = ["chat", "vision", "embedding", "audio_transcription"] as const;
const usageKey = "rework.admin.capabilities.organizationModels.usages";

export function LicenseBadge({
  label,
  href,
  description = label,
}: {
  label: string;
  href?: string;
  description?: string;
}) {
  const badge = <StatusBadge label={label} tone="neutral" />;
  return (
    <Tooltip content={description} asChild>
      {href ? (
        <a className={styles.licenseBadge} href={href} target="_blank" rel="noreferrer" aria-label={description}>
          {badge}
        </a>
      ) : (
        <span className={styles.licenseBadge} tabIndex={0}>
          {badge}
        </span>
      )}
    </Tooltip>
  );
}

export function ModelMetadataDialog({
  organizationId,
  offer,
  platformTermsUrl,
  usageOnly = false,
  onClose,
}: {
  organizationId: string;
  offer: StoredModelOffer;
  platformTermsUrl?: string;
  usageOnly?: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const inputId = useId();
  const { showError } = useToast();
  const [save, { isLoading }] = useReplaceModelComplementsMutation();
  const [values, setValues] = useState<Record<string, unknown>>(offer.metadata_complements ?? {});
  const [resetResult, setResetResult] = useState<{ metadata: ModelMetadata; revision: number }>();
  const key = "rework.admin.capabilities.organizationModels.metadata";
  const catalogKey = "rework.admin.capabilities.organizationModels.catalogs";
  const expectedRevision = resetResult?.revision ?? offer.metadata_revision;
  const metadata = resetResult?.metadata ?? offer.metadata;
  const detected = resetResult?.metadata ?? offer.detected_metadata ?? {};
  const provenance = detected.provenance ?? {};
  const providerName =
    provenance.display_name === "provider"
      ? (detected.display_name ?? offer.upstream_model_id)
      : offer.upstream_model_id;
  const licenseName = detected.license?.name?.trim();
  const licenseUrl = detected.license?.url && safeHttpUrl(detected.license.url);
  const licenseLabel = t(`${key}.fields.license`);
  const licenseOrigin = detected.provenance?.license;
  const licenseDescription = [licenseLabel, licenseName, licenseOrigin && t(`${key}.origins.${licenseOrigin}`)]
    .filter(Boolean)
    .join(" · ");
  const update = (field: string, value: unknown) => setValues((previous) => ({ ...previous, [field]: value }));
  const clear = (field: string) =>
    setValues((previous) => {
      const next = { ...previous };
      delete next[field];
      return next;
    });
  const fieldState = (field: keyof typeof fields) => {
    const provider = field !== "display_name" && provenance[field] === "provider";
    const constrained =
      (field === "embedding" && detected.chat === true && provenance.chat === "provider") ||
      (field === "chat" && detected.embedding === true && provenance.embedding === "provider") ||
      (field.startsWith("reasoning_") && detected.reasoning === false && provenance.reasoning === "provider");
    const locked = provider || constrained;
    const savedComplement = field in values;
    const customized = !locked && savedComplement;
    const automatic = field === "display_name" ? (detected.display_name ?? providerName) : detected[field];
    const selected = customized ? values[field] : automatic;
    const value =
      usageOnly && field === "audio_transcription"
        ? (selected ?? detected.provider_capabilities?.audio_transcription)
        : selected;
    return { provider, locked, customized, savedComplement, value };
  };
  const draftChat = usageOnly && fieldState("chat").value === true;
  const draftEmbedding = usageOnly && fieldState("embedding").value === true;
  const visibleFields = usageOnly ? usageFields : (Object.keys(fields) as (keyof typeof fields)[]);
  const invalid = Object.entries(values).some(
    ([field, value]) =>
      value != null &&
      ((fields[field as keyof typeof fields] === "number" && (!Number.isSafeInteger(value) || Number(value) <= 0)) ||
        (enumChoices[field] && !enumChoices[field].includes(String(value))) ||
        (fields[field as keyof typeof fields] === "text" && !String(value).trim())),
  );
  const submit = async (reset = false) => {
    if (isLoading) return;
    try {
      const result = await save({
        organizationId,
        sourceId: offer.source_id,
        replaceModelComplements: {
          expected_revision: expectedRevision,
          upstream_model_id: offer.upstream_model_id,
          values: reset
            ? {}
            : Object.fromEntries(
                Object.entries(values).map(([field, value]) => [
                  field,
                  fields[field as keyof typeof fields] === "list" && typeof value === "string"
                    ? value
                        .split(",")
                        .map((item) => item.trim())
                        .filter(Boolean)
                    : value,
                ]),
              ),
        },
      }).unwrap();
      if (reset) {
        setValues({});
        setResetResult({ metadata: result, revision: expectedRevision + 1 });
      } else {
        onClose();
      }
    } catch (error) {
      showError({ summary: t(`${key}.saveFailed`), detail: normalizeApiError(error).detail });
    }
  };
  return (
    <Dialog
      open
      className={styles.metadataDialog}
      title={`${t(usageOnly ? `${usageKey}.edit` : `${key}.details`)} - ${metadata.display_name ?? offer.upstream_model_id}`}
      titleAddon={
        <>
          {!usageOnly && (licenseName || licenseUrl || platformTermsUrl) && (
            <div className={styles.metadataLicenses}>
              {(licenseName || licenseUrl) && (
                <LicenseBadge
                  label={licenseName || licenseLabel}
                  href={licenseUrl || undefined}
                  description={licenseDescription}
                />
              )}
              {platformTermsUrl && (
                <LicenseBadge
                  label={t(`${catalogKey}.platformTermsBadge`)}
                  href={platformTermsUrl}
                  description={t(`${catalogKey}.platformTerms`)}
                />
              )}
            </div>
          )}
          <IconButton
            className={styles.metadataClose}
            size="small"
            variant="icon"
            icon={{ category: "outlined", type: "close" }}
            aria-label={t("common.close")}
            onClick={onClose}
          />
        </>
      }
      maxWidth={usageOnly ? 560 : 1000}
      dense
      dividers
      initialFocus="dialog"
      confirmLabel={t("common.save")}
      onConfirm={() => void submit()}
      confirmDisabled={isLoading || invalid}
      onCancel={onClose}
      footerStart={
        !usageOnly && (
          <Button
            size="small"
            variant="outlined"
            color="on-surface"
            onClick={() => void submit(true)}
            disabled={isLoading}
          >
            {t(`${key}.reset`)}
          </Button>
        )
      }
    >
      <p className={styles.metadataHint}>{t(usageOnly ? `${usageKey}.editHint` : `${key}.hint`)}</p>
      {!usageOnly && !!Object.keys(metadata.provider_capabilities ?? {}).length && (
        <p className={styles.metadataHint}>
          {t(`${key}.providerCapabilities`)}{" "}
          {Object.entries(metadata.provider_capabilities ?? {})
            .filter(([, value]) => value)
            .map(([capability]) => capability)
            .join(", ") || t(`${key}.noneReported`)}
        </p>
      )}
      <div className={styles.metadataGrid}>
        {!usageOnly && (
          <div className={styles.metadataField}>
            <div className={styles.metadataFieldHeader}>
              <strong>
                <label htmlFor={`${inputId}-providerName`}>{t(`${key}.providerName`)}</label>
              </strong>
              <span className={styles.hint}>{t(`${key}.origins.provider`)}</span>
            </div>
            <TextInput
              id={`${inputId}-providerName`}
              className={styles.providerName}
              size="small"
              compact
              readOnly
              value={providerName}
            />
          </div>
        )}
        {visibleFields.map((field) => {
          const kind = fields[field];
          const { provider, locked, customized, savedComplement, value } = fieldState(field);
          const origin =
            field === "display_name" ? "platform" : locked ? "provider" : customized ? "manual" : provenance[field];
          const sourceLabel =
            usageOnly && origin === "manual"
              ? t(`${usageKey}.manual`)
              : origin && origin !== "unknown"
                ? t(`${key}.origins.${origin}`)
                : t(`${key}.detected`);
          const label = t(usageOnly ? `${usageKey}.${field}` : `${key}.fields.${field}`);
          const checked = value === true;
          const conflictingUse = (field === "chat" && draftEmbedding) || (field === "embedding" && draftChat);
          const usageHint =
            usageOnly && !checked
              ? field === "vision" && !draftChat
                ? t(`${usageKey}.visionNeedsChat`)
                : conflictingUse
                  ? t(`${usageKey}.exclusiveUses`)
                  : undefined
              : undefined;
          const resettable = usageOnly ? savedComplement && (!checked || locked) : customized;
          return (
            <div key={field} className={styles.metadataField}>
              <div className={styles.metadataFieldHeader}>
                <strong>{usageOnly ? <label htmlFor={`${inputId}-${field}`}>{label}</label> : label}</strong>
                {locked || usageHint ? (
                  <Tooltip
                    content={locked ? t(`${key}.${provider ? "providerReadOnly" : "providerConstraint"}`) : usageHint}
                    asChild
                  >
                    <span className={styles.hint} tabIndex={0}>
                      {sourceLabel}
                    </span>
                  </Tooltip>
                ) : (
                  <span className={styles.hint}>{sourceLabel}</span>
                )}
              </div>
              <div className={usageOnly ? styles.usageControls : styles.metadataControls}>
                {usageOnly ? (
                  <Checkbox
                    id={`${inputId}-${field}`}
                    checked={checked}
                    disabled={isLoading || locked || !!usageHint || (checked && !customized)}
                    onChange={(event) => {
                      if (event.currentTarget.checked) update(field, true);
                      else clear(field);
                    }}
                  />
                ) : kind === "boolean" ? (
                  <Select
                    size="small"
                    compact
                    ariaLabel={`${t(`${key}.fields.${field}`)} - ${t(`${key}.value`)}`}
                    value={value == null ? "" : String(value)}
                    options={[
                      { key: "unknown", value: "", label: t(`${key}.unknown`) },
                      { key: "true", value: "true", label: t(`${key}.yes`) },
                      { key: "false", value: "false", label: t(`${key}.no`) },
                    ]}
                    disabled={isLoading || locked}
                    onChange={(value) => update(field, value === "" ? null : value === "true")}
                  />
                ) : enumChoices[field] ? (
                  <Select
                    size="small"
                    compact
                    ariaLabel={`${t(`${key}.fields.${field}`)} - ${t(`${key}.value`)}`}
                    value={String(value ?? "")}
                    options={[
                      { key: "unknown", value: "", label: t(`${key}.unknown`) },
                      ...enumChoices[field].map((value) => ({
                        key: value,
                        value,
                        label: t(`${key}.options.${value}`),
                      })),
                    ]}
                    onChange={(value) => update(field, value || null)}
                    disabled={isLoading || locked}
                  />
                ) : (
                  <TextInput
                    size="small"
                    compact
                    aria-label={`${t(`${key}.fields.${field}`)} - ${t(`${key}.value`)}`}
                    type={kind === "number" ? "number" : "text"}
                    min={kind === "number" ? 1 : undefined}
                    maxLength={field === "display_name" ? 256 : undefined}
                    showCharacterCount={false}
                    value={Array.isArray(value) ? value.join(", ") : String(value ?? "")}
                    placeholder={t(`${key}.unknown`)}
                    disabled={isLoading || locked}
                    onChange={(event) =>
                      update(
                        field,
                        event.target.value === ""
                          ? null
                          : kind === "number"
                            ? Number(event.target.value)
                            : event.target.value,
                      )
                    }
                  />
                )}
                {resettable && (
                  <IconButton
                    size="small"
                    variant="icon"
                    icon={{ category: "outlined", type: "refresh" }}
                    title={`${label} - ${t(`${key}.resetField`)}`}
                    disabled={isLoading}
                    onClick={() => clear(field)}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Dialog>
  );
}
