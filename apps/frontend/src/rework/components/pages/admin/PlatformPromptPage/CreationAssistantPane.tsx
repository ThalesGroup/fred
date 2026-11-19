// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { PromptEditor } from "@shared/molecules/PromptEditor/PromptEditor";
import Select, { type SelectOption } from "@shared/molecules/Select/Select";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { findReservedPromptTag } from "@rework/utils/promptValidation";
import { modelChoiceKey, parseModelChoice } from "@rework/features/capabilities/modelChoice";
import {
  useGetCreationAssistantSettingsQuery,
  useResetCreationAssistantPromptMutation,
  usePatchCreationAssistantSettingsMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PatchCreationAssistant } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PlatformPromptPage.module.css";

const MAX_CHARS = 20_000;
const KEY = "rework.platformPrompt.creationAssistant";

export default function CreationAssistantPane({ organizationId }: { organizationId: string }) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const {
    currentData: data,
    isFetching,
    isError,
    error,
    refetch,
  } = useGetCreationAssistantSettingsQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const [save, { isLoading: isSaving }] = usePatchCreationAssistantSettingsMutation();
  const [reset, { isLoading: isResetting }] = useResetCreationAssistantPromptMutation();
  const busy = isFetching || isSaving || isResetting;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [runtimeId, setRuntimeId] = useState<string>();
  const source = data?.defaults.find((item) => item.runtime_id === runtimeId) ?? data?.defaults[0];
  const unavailable = !source || source.source_unavailable || source.creation_assistant_prompt === null;
  const [editedText, setText] = useState<string>();
  const [editedModel, setModel] = useState<string>();
  const [editedReasoning, setReasoning] = useState<boolean>();
  const [serverError, setServerError] = useState<string>();
  const [showDefault, setShowDefault] = useState(false);
  const discard = () => {
    setText(undefined);
    setModel(undefined);
    setReasoning(undefined);
    setServerError(undefined);
  };
  // Successful writes refetch canonical values, including the separate text audit.
  useEffect(discard, [data?.text, data?.updated_at, data?.text_updated_at]);
  const text = editedText ?? data?.text ?? source?.creation_assistant_prompt ?? "";
  const savedModel = data?.model ? modelChoiceKey(data.model) : "";
  const model = editedModel ?? savedModel;
  const reasoning = editedReasoning ?? data?.reasoning ?? false;
  const effectiveModel = model || (data?.models.default ? modelChoiceKey(data.models.default) : "");
  const reasoningAllowed =
    data?.models.policy.reasoning_enabled.some((key) => modelChoiceKey(key) === effectiveModel) ?? false;
  const options: SelectOption<string>[] = [
    { key: "default", value: "", label: t(`${KEY}.model.default`) },
    ...(data?.models.offers.filter((offer) => offer.selectable) ?? []).map((offer) => ({
      key: modelChoiceKey(offer.key),
      value: modelChoiceKey(offer.key),
      label: `${offer.metadata?.display_name ?? offer.key.upstream_model_id} (${offer.key.source_id})`,
    })),
  ];
  if (model && !options.some((option) => option.value === model))
    options.push({
      key: model,
      value: model,
      disabled: true,
      label: t(`${KEY}.model.missing`, {
        id: `${parseModelChoice(model).upstream_model_id} (${parseModelChoice(model).source_id})`,
      }),
    });
  const tag = findReservedPromptTag(text);
  const length = [...text].length;
  const clientError = tag
    ? t("rework.promptEditor.reservedTag", { tag })
    : length > MAX_CHARS
      ? t("rework.platformPrompt.field.tooLong", { max: MAX_CHARS })
      : editedText !== undefined && !text.trim()
        ? t(`${KEY}.empty`)
        : undefined;
  const revised =
    data?.text !== null &&
    data?.text_updated_at &&
    data.defaults.some(
      (item) =>
        item.creation_assistant_prompt_revised_at &&
        item.creation_assistant_prompt_revised_at > data.text_updated_at!.slice(0, 10),
    );
  const patch: PatchCreationAssistant = {};
  // A text save, even unchanged, explicitly acknowledges a newer shipped prompt.
  if (editedText !== undefined) patch.text = text;
  if (editedModel !== undefined && model !== savedModel) patch.model = model ? parseModelChoice(model) : null;
  if (editedReasoning !== undefined && reasoning !== data?.reasoning) patch.reasoning = reasoning;
  if (revised && Object.keys(patch).length === 0) patch.text = text;
  const dirty = editedText !== undefined || editedModel !== undefined || editedReasoning !== undefined;
  const canSave = !!data && !busy && !clientError && Object.keys(patch).length > 0;
  const saveSettings = async () => {
    if (!canSave) return;
    try {
      await save({ organizationId, patchCreationAssistant: patch }).unwrap();
      if (!mounted.current) return;
      discard();
      showSuccess({ summary: t(`${KEY}.saved`) });
    } catch (failure) {
      if (!mounted.current) return;
      setServerError(normalizeApiError(failure).detail);
      showError({ summary: t(`${KEY}.saveFailed`) });
    }
  };
  const resetText = () =>
    showConfirmationDialog({
      title: t(`${KEY}.resetConfirm.title`),
      message: t(`${KEY}.resetConfirm.message`),
      confirmButtonLabel: t(`${KEY}.reset`),
      onConfirm: async () => {
        if (!mounted.current) return;
        try {
          await reset({ organizationId }).unwrap();
          if (!mounted.current) return;
          setText(undefined);
          setServerError(undefined);
          showSuccess({ summary: t(`${KEY}.resetDone`) });
        } catch (failure) {
          if (mounted.current)
            showError({ summary: t(`${KEY}.resetFailed`), detail: normalizeApiError(failure).detail });
        }
      },
    });
  if (isError)
    return (
      <div role="alert">
        <p>{t("rework.platformPrompt.loadFailed")}</p>
        <p>{normalizeApiError(error).detail}</p>
        <Button color="primary" variant="outlined" size="medium" onClick={() => void refetch()}>
          {t("rework.provisioning.retryAuthority")}
        </Button>
      </div>
    );
  if (!data) return <p role="status">{t("common.loading")}</p>;
  return (
    <section className={`${styles.pane} ${styles.fill}`}>
      <div className={styles.paneHeadRow}>
        <div className={styles.paneHead}>
          <div className={styles.paneTitleRow}>
            <h2 className={styles.paneTitle}>{t(`${KEY}.title`)}</h2>
            <span className={styles.badge}>{t(`${KEY}.${data.text === null ? "badgeDefault" : "badgeCustom"}`)}</span>
          </div>
          <p className={styles.paneSubtitle}>{t(`${KEY}.subtitle`)}</p>
        </div>
        <div className={styles.modelSlot}>
          <Select
            size="small"
            compact
            ariaLabel={t(`${KEY}.model.label`)}
            options={options}
            value={model}
            onChange={setModel}
            disabled={busy}
          />
          <Tooltip text={reasoningAllowed ? t(`${KEY}.reasoning.label`) : t(`${KEY}.reasoning.unsupported`)}>
            <div className={styles.reasoningToggle}>
              <Switch
                size="small"
                checked={reasoning && reasoningAllowed}
                onChange={(event) => setReasoning(event.target.checked)}
                disabled={busy || !reasoningAllowed}
                aria-label={t(`${KEY}.reasoning.label`)}
              />
              <span aria-hidden="true">{t(`${KEY}.reasoning.label`)}</span>
            </div>
          </Tooltip>
        </div>
      </div>
      <Select
        size="small"
        label={t("rework.platformPrompt.source")}
        value={source?.runtime_id}
        options={data.defaults.map((item) => ({
          key: item.runtime_id,
          value: item.runtime_id,
          label: item.runtime_id,
        }))}
        onChange={setRuntimeId}
        disabled={busy}
        emptyMessage={t("rework.platformPrompt.noSources")}
      />
      {unavailable && <p className={styles.warning}>{t("rework.platformPrompt.sourceUnavailable")}</p>}
      {!!text.trim() && !text.includes("{language}") && <p className={styles.warning}>{t(`${KEY}.missingLanguage`)}</p>}
      {revised && <p className={styles.warning}>{t(`${KEY}.newDefault`)}</p>}
      {data.text !== null && (
        <Button color="primary" variant="text" size="small" onClick={() => setShowDefault(!showDefault)}>
          {t(`${KEY}.${showDefault ? "hideDefault" : "viewDefault"}`)}
        </Button>
      )}
      {showDefault && data.text !== null && !unavailable && (
        <pre className={`${styles.instructionsBody} ${styles.defaultPreview}`} data-testid="creation-assistant-default">
          {source?.creation_assistant_prompt}
        </pre>
      )}
      <div className={styles.editorSlot}>
        <PromptEditor
          fillHeight
          label={t("rework.platformPrompt.field.label")}
          value={text}
          onChange={(next) => {
            setText(next);
            setServerError(undefined);
          }}
          disabled={busy}
          error={clientError ?? serverError}
        />
      </div>
      <div className={styles.editorFooter}>
        <p className={styles.hint}>{t(`${KEY}.hint`)}</p>
        <p className={`${styles.counter} ${length > MAX_CHARS ? styles.counterOver : ""}`}>
          {length} / {MAX_CHARS}
        </p>
      </div>
      <div className={styles.paneFooter}>
        {data.text_updated_at && (
          <p className={styles.meta}>
            {t("rework.platformPrompt.lastUpdated", {
              who: data.text_updated_by ?? t("rework.platformPrompt.unknownAuthor"),
              when: new Date(data.text_updated_at).toLocaleString(),
            })}
          </p>
        )}
        <div className={styles.actions}>
          <Button
            color="primary"
            variant="text"
            size="medium"
            onClick={resetText}
            disabled={data.text === null || busy}
          >
            {t(`${KEY}.reset`)}
          </Button>
          <Button color="primary" variant="outlined" size="medium" onClick={discard} disabled={!dirty || busy}>
            {t("rework.platformPrompt.reset")}
          </Button>
          <Button
            color="primary"
            variant="filled"
            size="medium"
            icon={{ category: "outlined", type: "check", filled: false }}
            onClick={saveSettings}
            disabled={!canSave}
          >
            {t(isSaving ? "rework.platformPrompt.saving" : "rework.platformPrompt.save")}
          </Button>
        </div>
      </div>
    </section>
  );
}
