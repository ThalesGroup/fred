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

// "Validate the plan before building" switch, off by default: on, the first
// presentation of a conversation is shown as an outline before it is built.

import { useTranslation } from "react-i18next";
import Switch from "@shared/atoms/Switch/Switch";
import { VALIDATE_PLAN_KEY } from "./types";
import styles from "./PptBuilderTemplatePanel.module.css";

interface Props {
  disabled: boolean;
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
}

export function PptBuilderPlanSettings({ disabled, configValues, onConfigChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className={styles.settingCard}>
      <label className={styles.switchRow}>
        <span className={styles.switchText}>
          <span className={styles.switchLabel}>{t("capability.ppt_builder.fields.validate_plan.title")}</span>
          <span className={styles.switchDescription}>
            {t("capability.ppt_builder.fields.validate_plan.description")}
          </span>
        </span>
        <Switch
          size="small"
          checked={configValues[VALIDATE_PLAN_KEY] === true}
          disabled={disabled}
          onChange={(event) => onConfigChange(VALIDATE_PLAN_KEY, event.target.checked)}
        />
      </label>
    </div>
  );
}
