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

// Weaver currently labels slides structurally; background vision is unavailable.

import { useTranslation } from "react-i18next";
import Switch from "@shared/atoms/Switch/Switch";
import styles from "./PptBuilderTemplatePanel.module.css";

export function PptBuilderVisionSettings() {
  const { t } = useTranslation();
  return (
    <div className={`${styles.settingCard} ${styles.stacked}`}>
      <label className={styles.switchRow}>
        <span className={styles.switchText}>
          <span className={styles.switchLabel}>{t("capability.ppt_builder.fields.use_vision.title")}</span>
          <span className={styles.switchDescription}>{t("capability.ppt_builder.fields.use_vision.unavailable")}</span>
        </span>
        <Switch size="small" checked={false} disabled />
      </label>
    </div>
  );
}
