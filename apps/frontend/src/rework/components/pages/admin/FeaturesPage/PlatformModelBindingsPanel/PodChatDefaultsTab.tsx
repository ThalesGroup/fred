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

import Button from "@shared/atoms/Button/Button.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useClearPodChatDefaultMutation,
  useClearPodChatFallbackMutation,
  usePodChatDefaultsQuery,
  useSetPodChatDefaultMutation,
  useSetPodChatFallbackMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PodChatDefaultStatus } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PlatformModelBindingsPanel.module.css";

const MAX_VISIBLE_PROFILE_ID_LENGTH = 36;

function PodDefaultRow({ pod }: { pod: PodChatDefaultStatus }) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const [selectedProfileId, setSelectedProfileId] = useState(pod.effective_profile_id ?? "");
  const [selectedFallbackId, setSelectedFallbackId] = useState(pod.effective_fallback_profile_id ?? "");
  const [setDefault, { isLoading: isSaving }] = useSetPodChatDefaultMutation();
  const [clearDefault, { isLoading: isClearing }] = useClearPodChatDefaultMutation();
  const [setFallback, { isLoading: isSavingFallback }] = useSetPodChatFallbackMutation();
  const [clearFallback, { isLoading: isClearingFallback }] = useClearPodChatFallbackMutation();

  useEffect(() => setSelectedProfileId(pod.effective_profile_id ?? ""), [pod.effective_profile_id]);
  useEffect(() => setSelectedFallbackId(pod.effective_fallback_profile_id ?? ""), [pod.effective_fallback_profile_id]);

  const options = (pod.models ?? []).map((model) => {
    const profileId = model.profile_id;
    const truncated = profileId.length > MAX_VISIBLE_PROFILE_ID_LENGTH;
    return {
      key: profileId,
      value: profileId,
      label: model.display_name || model.name,
      description: truncated ? `${profileId.slice(0, MAX_VISIBLE_PROFILE_ID_LENGTH - 3)}...` : profileId,
      tooltip: truncated ? profileId : undefined,
      section: model.discovery_source_id
        ? t("rework.admin.platformModelBindings.discoveredSource")
        : t("rework.admin.platformModelBindings.manualSource"),
    };
  });
  const fallbackOptions = options.filter((option) =>
    (pod.models ?? []).some((model) => model.profile_id === option.value && !model.discovery_source_id),
  );
  const defaultSelectable = options.some((option) => option.value === selectedProfileId);
  const fallbackSelectable = fallbackOptions.some((option) => option.value === selectedFallbackId);
  const busy = isSaving || isClearing || isSavingFallback || isClearingFallback;

  const save = async () => {
    if (!selectedProfileId) return;
    try {
      await setDefault({
        runtimeId: pod.runtime_id,
        setPodChatDefaultRequest: { profile_id: selectedProfileId },
      }).unwrap();
      showSuccess({ summary: t("rework.admin.platformModelBindings.podSaved") });
    } catch {
      showError({ summary: t("rework.admin.platformModelBindings.podSaveError") });
    }
  };

  const reset = async () => {
    try {
      await clearDefault({ runtimeId: pod.runtime_id }).unwrap();
      showSuccess({ summary: t("rework.admin.platformModelBindings.podReset") });
    } catch {
      showError({ summary: t("rework.admin.platformModelBindings.podSaveError") });
    }
  };

  const saveFallback = async () => {
    if (!selectedFallbackId) return;
    try {
      await setFallback({
        runtimeId: pod.runtime_id,
        setPodChatFallbackRequest: { profile_id: selectedFallbackId },
      }).unwrap();
      showSuccess({ summary: t("rework.admin.platformModelBindings.fallbackSaveToast") });
    } catch {
      showError({ summary: t("rework.admin.platformModelBindings.fallbackError") });
    }
  };

  const resetFallback = async () => {
    try {
      await clearFallback({ runtimeId: pod.runtime_id }).unwrap();
      showSuccess({ summary: t("rework.admin.platformModelBindings.fallbackDeleteToast") });
    } catch {
      showError({ summary: t("rework.admin.platformModelBindings.fallbackError") });
    }
  };

  return (
    <section className={styles.podRow}>
      <div className={styles.podHeading}>
        <strong>{pod.runtime_id}</strong>
        <code>{pod.base_url}</code>
      </div>
      {!pod.reachable && <p className={styles.hint}>{t("rework.admin.platformModelBindings.podUnreachable")}</p>}
      {pod.override_unavailable && (
        <p className={styles.statusError}>
          {t("rework.admin.platformModelBindings.podOverrideUnavailable", { profile: pod.override_profile_id })}
        </p>
      )}
      {selectedProfileId && !defaultSelectable && (
        <p className={styles.hint}>
          {t("rework.admin.platformModelBindings.currentNotSelectable")}{" "}
          <code className={styles.currentProfileId} title={selectedProfileId}>
            {selectedProfileId}
          </code>
        </p>
      )}
      <Select
        label={t("rework.admin.platformModelBindings.podDefaultSelect")}
        size="small"
        compact
        options={options}
        value={defaultSelectable ? selectedProfileId : ""}
        onChange={setSelectedProfileId}
        placeholder={t("rework.admin.platformModelBindings.chooseEnabledModel")}
        disabled={!pod.reachable || busy}
        emptyMessage={t("rework.admin.platformModelBindings.podNoModels")}
      />
      <div className={styles.formActions}>
        {pod.override_profile_id && (
          <Button color="on-surface" variant="text" size="small" onClick={() => void reset()} disabled={busy}>
            {t("rework.admin.platformModelBindings.podResetAction")}
          </Button>
        )}
        <Button
          color="primary"
          variant="filled"
          size="small"
          onClick={() => void save()}
          disabled={!pod.reachable || busy || !defaultSelectable || selectedProfileId === pod.effective_profile_id}
        >
          {t("rework.admin.platformModelBindings.form.save")}
        </Button>
      </div>
      <div className={styles.podFallback}>
        <strong>{t("rework.admin.platformModelBindings.fallbackLabel")}</strong>
        <p className={styles.hint}>{t("rework.admin.platformModelBindings.fallbackHint")}</p>
        {pod.fallback_unavailable && (
          <p className={styles.statusError}>
            {t("rework.admin.platformModelBindings.podFallbackUnavailable", {
              profile: pod.fallback_override_profile_id,
            })}
          </p>
        )}
        {selectedFallbackId && !fallbackSelectable && (
          <p className={styles.hint}>
            {t("rework.admin.platformModelBindings.currentNotSelectable")}{" "}
            <code className={styles.currentProfileId} title={selectedFallbackId}>
              {selectedFallbackId}
            </code>
          </p>
        )}
        <Select
          label={t("rework.admin.platformModelBindings.fallbackSelect")}
          size="small"
          compact
          options={fallbackOptions}
          value={fallbackSelectable ? selectedFallbackId : ""}
          onChange={setSelectedFallbackId}
          placeholder={t("rework.admin.platformModelBindings.chooseEnabledManualModel")}
          disabled={!pod.reachable || busy}
          emptyMessage={t("rework.admin.platformModelBindings.noManualModels")}
        />
        <div className={styles.formActions}>
          {pod.fallback_override_profile_id && (
            <Button color="on-surface" variant="text" size="small" onClick={() => void resetFallback()} disabled={busy}>
              {t("rework.admin.platformModelBindings.podResetAction")}
            </Button>
          )}
          <Button
            color="primary"
            variant="filled"
            size="small"
            onClick={() => void saveFallback()}
            disabled={
              !pod.reachable || busy || !fallbackSelectable || selectedFallbackId === pod.effective_fallback_profile_id
            }
          >
            {t("rework.admin.platformModelBindings.form.save")}
          </Button>
        </div>
      </div>
    </section>
  );
}

export function PodChatDefaultsTab() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = usePodChatDefaultsQuery();

  if (isLoading) return <p className={styles.hint}>{t("rework.admin.platformModelBindings.podsLoading")}</p>;
  if (isError) return <p className={styles.statusError}>{t("rework.admin.platformModelBindings.podsLoadError")}</p>;
  if (!data?.pods?.length) return <p className={styles.hint}>{t("rework.admin.platformModelBindings.noPods")}</p>;

  return (
    <div className={styles.podList}>
      {data.pods.map((pod) => (
        <PodDefaultRow key={pod.runtime_id} pod={pod} />
      ))}
    </div>
  );
}
