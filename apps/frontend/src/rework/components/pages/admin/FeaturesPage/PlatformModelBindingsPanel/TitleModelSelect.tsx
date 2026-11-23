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

import Select, { type SelectOption } from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useTranslation } from "react-i18next";
import {
  useCreationAssistantSettingsQuery,
  useSetCreationAssistantSettingsMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformModelBindingsPanel.module.css";

/** Model of generated conversation titles. It is stored with the creation
 * assistant settings, whose PUT replaces them all: the others are re-sent as is. */
export function TitleModelSelect() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { data, isError } = useCreationAssistantSettingsQuery();
  const [save, { isLoading }] = useSetCreationAssistantSettingsMutation();

  if (isError) return <p className={styles.hint}>{t("rework.admin.platformModelBindings.titleModel.loadError")}</p>;
  if (!data) return null;

  const saved = data.title_model_profile_id ?? "";
  const options: SelectOption<string>[] = [
    { key: "default", value: "", label: t("rework.admin.platformModelBindings.titleModel.default") },
    ...(data.model_options ?? []).map((option) => ({
      key: option.profile_id,
      value: option.profile_id,
      label: option.name,
    })),
  ];
  // Keep an unavailable saved value visible without offering it as a new choice.
  if (saved && !options.some((option) => option.value === saved)) {
    options.push({ key: saved, value: saved, label: saved, disabled: true });
  }

  const onChange = async (value: string) => {
    try {
      await save({
        setCreationAssistantSettingsRequest: {
          text: data.is_default ? null : data.text,
          model_profile_id: data.model_profile_id ?? null,
          title_model_profile_id: value || null,
          reasoning_effort: data.reasoning_effort,
        },
      }).unwrap();
      showSuccess({ summary: t("rework.admin.platformModelBindings.titleModel.saved") });
    } catch {
      showError({ summary: t("rework.admin.platformModelBindings.titleModel.saveError") });
    }
  };

  return (
    <div className={styles.row}>
      <strong>{t("rework.admin.platformModelBindings.titleModel.label")}</strong>
      <Select
        size="small"
        compact
        ariaLabel={t("rework.admin.platformModelBindings.titleModel.label")}
        options={options}
        value={saved}
        onChange={(value) => void onChange(value)}
        disabled={isLoading}
      />
    </div>
  );
}
