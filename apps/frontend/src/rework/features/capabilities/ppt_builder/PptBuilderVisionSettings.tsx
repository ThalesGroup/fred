// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import Switch from "@shared/atoms/Switch/Switch";
import { USE_VISION_KEY } from "./types";
import type { VisionAvailability } from "./useVisionAvailability";
import styles from "./PptBuilderTemplatePanel.module.css";

interface Props {
  disabled: boolean;
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
  vision: VisionAvailability;
}

export function PptBuilderVisionSettings({ disabled, configValues, onConfigChange, vision }: Props) {
  const { t } = useTranslation();
  const unavailable = vision.available === false;
  const useVision = unavailable
    ? configValues[USE_VISION_KEY] === true
    : configValues[USE_VISION_KEY] !== false;

  return (
    <div className={`${styles.settingCard} ${styles.stacked}`}>
      <label className={styles.switchRow}>
        <span className={styles.switchText}>
          <span className={styles.switchLabel}>{t("capability.ppt_builder.fields.use_vision.title")}</span>
          <span className={styles.switchDescription}>
            {unavailable
              ? t("capability.ppt_builder.fields.use_vision.unavailable")
              : t("capability.ppt_builder.fields.use_vision.description")}
          </span>
        </span>
        <Switch
          size="small"
          checked={useVision}
          disabled={disabled || (unavailable && !useVision)}
          onChange={(event) => onConfigChange(USE_VISION_KEY, event.target.checked)}
        />
      </label>
    </div>
  );
}
