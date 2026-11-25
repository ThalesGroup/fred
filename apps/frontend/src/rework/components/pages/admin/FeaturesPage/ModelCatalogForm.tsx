// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import TextInput from "@shared/atoms/TextInput/TextInput";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Select from "@shared/molecules/Select/Select";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCreateModelCatalogMutation,
  useUpdateModelCatalogMutation,
  useRefreshModelSourceMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ModelDialect,
  ModelWire,
  ModelInventory,
  SingleModelUse,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import styles from "./ModelCatalog.module.css";

const lockIcon = { category: "outlined", type: "lock" } as const;
const dialectOptions = [
  { key: "openai_compatible", value: "openai_compatible", label: "OpenAI compatible" },
  { key: "openai", value: "openai", label: "OpenAI" },
  { key: "mistral", value: "mistral", label: "Mistral" },
];
const wireOptions = [
  { key: "openai_chat", value: "openai_chat", label: "Chat Completions" },
  { key: "openai_responses", value: "openai_responses", label: "Responses" },
];
const modelUsages: SingleModelUse[] = ["chat", "embedding", "audio_transcription"];

export function ModelCatalogForm({
  organizationId,
  onClose,
  onCreated,
  source,
  singleModel = false,
  onDelete,
  inventoryFetching = false,
}: {
  organizationId: string;
  onClose: () => void;
  onCreated: (sourceId: string) => void;
  source?: ModelInventory;
  singleModel?: boolean;
  onDelete?: () => void;
  inventoryFetching?: boolean;
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [create, creating] = useCreateModelCatalogMutation();
  const [update, updating] = useUpdateModelCatalogMutation();
  const readOnly = !!source && !source.managed;
  const declared = singleModel || (!!source?.managed && !source.url);
  const [refresh, refreshResult] = useRefreshModelSourceMutation();
  const [refreshFrom, setRefreshFrom] = useState<number>();
  const refreshing = refreshResult.isLoading || (refreshFrom !== undefined && inventoryFetching);
  const isLoading = creating.isLoading || updating.isLoading || inventoryFetching || refreshing;
  const [name, setName] = useState(source?.name ?? "");
  const [expectedRevision] = useState(source?.observation.source_revision ?? 0);
  const [url, setUrl] = useState(source?.url ?? "");
  const [modelId, setModelId] = useState("");
  const [modelUse, setModelUse] = useState<SingleModelUse>("chat");
  const [root, setRoot] = useState(source?.api_root ?? "");
  const [token, setToken] = useState("");
  const [metadataProvider, setMetadataProvider] = useState(source?.metadata_provider ?? "");
  const [modelsDevEnabled, setModelsDevEnabled] = useState(source?.models_dev_enabled ?? true);
  const modelsDevSwitchId = useId();
  const [dialect, setDialect] = useState<ModelDialect>(source?.dialect ?? "openai_compatible");
  const [wire, setWire] = useState<ModelWire>(source?.wire ?? "openai_chat");
  const key = "rework.admin.capabilities.organizationModels.catalogs";
  const missingConnection = !source && (!root.trim() || !token || !(declared ? modelId.trim() : url.trim()));
  const refreshError =
    refreshResult.error &&
    (normalizeApiError(refreshResult.error).detail ?? t("rework.admin.capabilities.discovery.refreshFailed"));
  // Only the snapshot published after this request can report a new enrichment failure.
  const enrichmentUnavailable =
    refreshResult.isSuccess &&
    !refreshing &&
    refreshFrom !== undefined &&
    source &&
    source.models_dev_enabled !== false &&
    source.observation.snapshot_revision > refreshFrom &&
    source.observation.error_code === "models_dev_unavailable";
  const save = async () => {
    if (readOnly || isLoading || missingConnection) return;
    const provider = metadataProvider.trim() || null;
    const providerChanged = provider !== (source?.metadata_provider ?? null);
    const syncChanged = modelsDevEnabled !== (source?.models_dev_enabled ?? true);
    try {
      let sourceId: string;
      if (source) {
        sourceId = source.observation.source_id;
        await update({
          organizationId,
          sourceId,
          updateModelCatalog: {
            expected_revision: expectedRevision,
            name: name.trim(),
            token: token || undefined,
            metadata_provider: providerChanged ? provider : undefined,
            models_dev_enabled: syncChanged ? modelsDevEnabled : undefined,
          },
        }).unwrap();
      } else {
        sourceId = await create({
          organizationId,
          createModelCatalog: {
            name: name.trim(),
            ...(declared ? { model: { id: modelId.trim(), usage: modelUse } } : { url: url.trim() }),
            api_root: root.trim(),
            token,
            dialect,
            wire,
            metadata_provider: provider ?? undefined,
            models_dev_enabled: modelsDevEnabled ? undefined : false,
          },
        }).unwrap();
      }
      setToken("");
      onCreated(sourceId);
      onClose();
      try {
        if (!source || token) await refresh({ organizationId, sourceId }).unwrap();
      } catch (error) {
        showError({ summary: t(`${key}.refreshFailed`), detail: normalizeApiError(error).detail });
      }
    } catch (error) {
      showError({
        summary: t(`${key}.${declared ? "saveModelFailed" : "saveFailed"}`),
        detail: normalizeApiError(error).detail,
      });
    }
  };
  return (
    <Dialog
      open
      title={t(
        `${key}.${source ? (readOnly ? "details" : declared ? "editModel" : "edit") : declared ? "addModel" : "add"}`,
        {
          name: source?.name,
        },
      )}
      maxWidth={480}
      dense
      confirmLabel={t("common.save")}
      cancelLabel={t(readOnly ? "common.close" : "common.cancel")}
      hideConfirm={readOnly}
      onConfirm={() => void save()}
      onCancel={onClose}
      confirmDisabled={isLoading || !name.trim() || missingConnection}
      footerStart={
        source && (
          <div className={styles.toolbar}>
            <IconButton
              color="on-surface"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "refresh" }}
              title={t("rework.admin.capabilities.discovery.refresh")}
              disabled={isLoading || !source.observation.enabled}
              onClick={() => {
                setRefreshFrom(source.observation.snapshot_revision);
                void refresh({ organizationId, sourceId: source.observation.source_id });
              }}
            />
            <IconButton
              color="error"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "delete" }}
              title={t(`${key}.delete`)}
              disabled={isLoading || readOnly || !onDelete}
              onClick={onDelete}
            />
          </div>
        )
      }
    >
      <div className={`${styles.form} ${styles.catalogForm}`}>
        {source && (
          <p role="note" className={styles.hint}>
            {t(`${key}.${readOnly ? "configuredHint" : "immutableHint"}`)}
          </p>
        )}
        <TextInput
          size="xs"
          compact
          label={t(`${key}.name`)}
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={128}
          required
          disabled={isLoading && !readOnly}
          readOnly={readOnly}
          icon={readOnly ? lockIcon : undefined}
        />
        {declared ? (
          <TextInput
            size="xs"
            compact
            label={t(`${key}.modelId`)}
            value={source ? (source.offers?.[0]?.upstream_model_id ?? "") : modelId}
            onChange={(event) => setModelId(event.target.value)}
            maxLength={256}
            showCharacterCount={false}
            required={!source}
            disabled={isLoading && !source}
            readOnly={!!source}
            icon={source ? lockIcon : undefined}
          />
        ) : (
          <TextInput
            size="xs"
            compact
            label={t(`${key}.url`)}
            type="url"
            value={source && !source.url ? t(`${key}.declaredInventory`) : url}
            onChange={(event) => {
              const value = event.target.value;
              setUrl(value);
              // A suggestion only: the administrator sees and approves the inference root.
              if (!root || root === url.replace(/\/models\/?$/, "")) setRoot(value.replace(/\/models\/?$/, ""));
            }}
            required
            disabled={isLoading && !source}
            readOnly={!!source}
            icon={source ? lockIcon : undefined}
          />
        )}
        {!source && declared && (
          <Select
            size="xs"
            compact
            label={t(`${key}.modelUse`)}
            value={modelUse}
            options={modelUsages.map((usage) => ({
              key: usage,
              value: usage,
              label: t(`rework.admin.capabilities.organizationModels.usages.${usage}`),
            }))}
            onChange={(value) => setModelUse(value as SingleModelUse)}
            disabled={isLoading}
          />
        )}
        <TextInput
          size="xs"
          compact={!!source}
          label={t(`${key}.apiRoot`)}
          explanation={source || declared ? undefined : t(`${key}.apiRootHint`)}
          type="url"
          value={root}
          onChange={(event) => setRoot(event.target.value)}
          required
          disabled={isLoading && !source}
          readOnly={!!source}
          icon={source ? lockIcon : undefined}
        />
        <TextInput
          size="xs"
          compact={readOnly}
          label={t(`${key}.token`)}
          explanation={
            readOnly ? undefined : t(`${key}.${source ? "rotateTokenHint" : declared ? "modelTokenHint" : "tokenHint"}`)
          }
          type="password"
          autoComplete="new-password"
          value={token}
          placeholder={readOnly ? t(`${key}.configuredToken`) : undefined}
          onChange={(event) => setToken(event.target.value)}
          required={!source}
          disabled={isLoading && !readOnly}
          readOnly={readOnly}
          icon={readOnly ? lockIcon : undefined}
        />
        {[
          {
            field: "dialect",
            value: dialect,
            options: dialectOptions,
            onChange: (value: string) => setDialect(value as ModelDialect),
          },
          {
            field: "wire",
            value: wire,
            options: wireOptions,
            onChange: (value: string) => setWire(value as ModelWire),
          },
        ].map(({ field, value, options, onChange }) =>
          source ? (
            <TextInput
              key={field}
              size="xs"
              compact
              label={t(`${key}.${field}`)}
              value={options.find((option) => option.value === value)?.label ?? value}
              readOnly
              icon={lockIcon}
            />
          ) : (
            <Select
              key={field}
              size="xs"
              compact
              label={t(`${key}.${field}`)}
              value={value}
              options={options}
              onChange={onChange}
              disabled={isLoading}
            />
          ),
        )}
        <div className={styles.toolbar}>
          <Switch
            id={modelsDevSwitchId}
            size="small"
            checked={modelsDevEnabled}
            onChange={(event) => setModelsDevEnabled(event.target.checked)}
            disabled={isLoading || readOnly}
          />
          <label htmlFor={modelsDevSwitchId}>{t(`${key}.modelsDevSync`)}</label>
        </div>
        <TextInput
          size="xs"
          compact={readOnly || !modelsDevEnabled}
          label={t(`${key}.metadataProvider`)}
          explanation={readOnly || !modelsDevEnabled ? undefined : t(`${key}.metadataProviderHint`)}
          placeholder={t(`${key}.metadataProviderAuto`)}
          maxLength={64}
          showCharacterCount={false}
          value={metadataProvider}
          onChange={(event) => setMetadataProvider(event.target.value)}
          disabled={!readOnly && (isLoading || !modelsDevEnabled)}
          readOnly={readOnly}
          icon={readOnly ? lockIcon : undefined}
        />
        {source && (
          <p role="status" className={styles.hint}>
            {refreshing
              ? t("rework.admin.capabilities.discovery.refreshing")
              : `${t(`${key}.lastRefresh`)} ${source.observation.last_success_at ? new Date(source.observation.last_success_at).toLocaleString() : t(`${key}.never`)}`}
          </p>
        )}
        {refreshError && (
          <p role="alert" className={styles.hint}>
            {refreshError}
          </p>
        )}
        {enrichmentUnavailable && (
          <p role="status" className={styles.hint}>
            {t(`${key}.modelsDevUnavailable`)}
          </p>
        )}
      </div>
    </Dialog>
  );
}
