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

// "Enforce variety [mode] at most [N] times each" with its switch: one sentence
// for the two variety settings. Off saves `variety_check: "off"`; on restores
// the last mode, so the selects stay put (disabled) while off.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Switch from "@shared/atoms/Switch/Switch";
import Select, { type SelectOption } from "@shared/molecules/Select/Select.tsx";
import { VARIETY_CHECK_KEY, VARIETY_MAX_USES_KEY } from "./types";
import styles from "./PptBuilderTemplatePanel.module.css";

type VarietyMode = "template_slide" | "kind";

const MODES: readonly VarietyMode[] = ["template_slide", "kind"];
const MAX_USES = [1, 2, 3, 4, 5];
const DEFAULT_MAX_USES = 2;

interface Props {
  disabled: boolean;
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
}

export function PptBuilderVarietySettings({ disabled, configValues, onConfigChange }: Props) {
  const { t } = useTranslation();
  const stored = configValues[VARIETY_CHECK_KEY];
  const on = stored !== "off";
  const storedMode = stored === "kind" || stored === "template_slide" ? stored : null;
  const [lastMode, setLastMode] = useState<VarietyMode>(storedMode ?? "template_slide");
  const mode = storedMode ?? lastMode;
  const storedMax = configValues[VARIETY_MAX_USES_KEY];
  const maxUses = typeof storedMax === "number" ? storedMax : DEFAULT_MAX_USES;

  const modeOptions: SelectOption<VarietyMode>[] = MODES.map((m) => ({
    value: m,
    key: m,
    label: t(`capability.ppt_builder.fields.variety_check.options.${m}`),
  }));
  const maxOptions: SelectOption<number>[] = MAX_USES.map((n) => ({ value: n, key: String(n), label: String(n) }));

  // A div, not a label: a click on a select must not toggle the switch.
  return (
    <div className={`${styles.settingCard} ${styles.varietyRow}`}>
      <span className={styles.switchText}>
        <span className={styles.sentence}>
          <span className={styles.switchLabel}>{t("capability.ppt_builder.fields.variety_check.title")}</span>
          <span className={styles.modeSelect}>
            <Select
              size="small"
              compact
              ariaLabel={t("capability.ppt_builder.fields.variety_check.modeAria")}
              options={modeOptions}
              value={mode}
              disabled={disabled || !on}
              onChange={(next) => {
                setLastMode(next);
                onConfigChange(VARIETY_CHECK_KEY, next);
              }}
            />
          </span>
          <span className={styles.switchLabel}>{t("capability.ppt_builder.fields.variety_check.atMost")}</span>
          <span className={styles.maxSelect}>
            <Select
              size="small"
              compact
              ariaLabel={t("capability.ppt_builder.fields.variety_check.maxAria")}
              options={maxOptions}
              value={maxUses}
              disabled={disabled || !on}
              onChange={(n) => onConfigChange(VARIETY_MAX_USES_KEY, n)}
            />
          </span>
          <span className={styles.switchLabel}>{t("capability.ppt_builder.fields.variety_check.times")}</span>
        </span>
        <span className={styles.switchDescription}>{t("capability.ppt_builder.fields.variety_check.description")}</span>
      </span>
      <Switch
        checked={on}
        disabled={disabled}
        aria-label={t("capability.ppt_builder.fields.variety_check.title")}
        onChange={(event) => onConfigChange(VARIETY_CHECK_KEY, event.target.checked ? mode : "off")}
      />
    </div>
  );
}
