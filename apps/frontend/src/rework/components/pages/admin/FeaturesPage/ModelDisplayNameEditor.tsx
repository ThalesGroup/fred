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
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSetModelDisplayNameMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import styles from "./FeaturesPage.module.css";

interface Props {
  capabilityId: string;
  wireName: string;
  effectiveName: string | null | undefined;
  overrideName: string | null | undefined;
}

export function ModelDisplayNameEditor({ capabilityId, wireName, effectiveName, overrideName }: Props) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const [setDisplayName, { isLoading }] = useSetModelDisplayNameMutation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(overrideName ?? "");

  useEffect(() => setDraft(overrideName ?? ""), [capabilityId, overrideName]);

  const trimmed = draft.trim();
  const canSave = trimmed.length > 0 && trimmed.length <= 160 && trimmed !== (overrideName ?? "");

  const save = async (name: string | null) => {
    try {
      await setDisplayName({
        capabilityId,
        setModelDisplayNameRequest: { display_name: name },
      }).unwrap();
      showSuccess({ summary: t("rework.admin.capabilities.modelName.saved") });
      setEditing(false);
    } catch (error) {
      showError({
        summary: t("rework.admin.capabilities.modelName.saveError"),
        detail: normalizeApiError(error).detail,
      });
    }
  };

  if (!editing) {
    return (
      <Button
        color="on-surface"
        variant="text"
        size="small"
        type="button"
        onClick={() => setEditing(true)}
        aria-label={t("rework.admin.capabilities.modelName.editAria", { name: wireName })}
      >
        {t("rework.admin.capabilities.modelName.editAction")}
      </Button>
    );
  }

  return (
    <form
      className={styles.modelNameForm}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave && !isLoading) void save(trimmed);
      }}
    >
      <TextInput
        label={t("rework.admin.capabilities.modelName.label")}
        value={draft}
        placeholder={effectiveName ?? wireName}
        maxLength={160}
        showCharacterCount={false}
        size="small"
        onChange={(event) => setDraft(event.target.value)}
        disabled={isLoading}
      />
      <div className={styles.modelNameActions}>
        <Button color="primary" variant="filled" size="small" type="submit" disabled={!canSave || isLoading}>
          {t("rework.admin.capabilities.modelName.saveAction")}
        </Button>
        {overrideName && (
          <Button
            color="on-surface"
            variant="text"
            size="small"
            type="button"
            disabled={isLoading}
            onClick={() => void save(null)}
          >
            {t("rework.admin.capabilities.modelName.resetAction")}
          </Button>
        )}
        <Button
          color="on-surface"
          variant="text"
          size="small"
          type="button"
          disabled={isLoading}
          onClick={() => {
            setDraft(overrideName ?? "");
            setEditing(false);
          }}
        >
          {t("rework.admin.capabilities.modelName.cancelAction")}
        </Button>
      </div>
    </form>
  );
}
