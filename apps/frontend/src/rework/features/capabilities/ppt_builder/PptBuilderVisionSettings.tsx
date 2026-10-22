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

// "Use a vision model" toggle and its labelling-model selector. With no
// vision-capable model for the agent, the toggle is shown off and locked and
// says that slides are labelled by rules.

import { useTranslation } from "react-i18next";
import Switch from "@shared/atoms/Switch/Switch";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { LABELLING_MODEL_KEY, USE_VISION_KEY } from "./types";
import type { VisionAvailability } from "./useVisionAvailability";
import styles from "./PptBuilderTemplatePanel.module.css";

/** Select value standing for "no override: the agent's own model". */
const AGENT_DEFAULT = "";

interface Props {
  disabled: boolean;
  configValues: Record<string, unknown>;
  onConfigChange: (key: string, value: unknown) => void;
  vision: VisionAvailability;
  /** The first option's label: the model used when none is picked. */
  defaultModelLabel?: string;
  /** When a changed model takes effect: the template is read again with it. */
  changeHint: string;
}

export function PptBuilderVisionSettings({
  disabled,
  configValues,
  onConfigChange,
  vision,
  defaultModelLabel,
  changeHint,
}: Props) {
  const { t } = useTranslation();
  const unavailable = vision.available === false;
  const useVision = !unavailable && configValues[USE_VISION_KEY] !== false;
  const stored = configValues[LABELLING_MODEL_KEY];
  const selected = typeof stored === "string" ? stored : AGENT_DEFAULT;

  const options: OptionModel<string>[] = [
    {
      value: AGENT_DEFAULT,
      key: "agent-default",
      label: defaultModelLabel ?? t("capability.ppt_builder.fields.labelling_model.agentDefault"),
    },
    ...vision.visionProfiles.map((profile) => ({
      value: profile.profile_id,
      key: profile.profile_id,
      label: profile.display_name ?? profile.name,
    })),
  ];
  // A stored profile that lost vision (or access) still shows, so the author sees what is saved.
  if (selected && !options.some((o) => o.value === selected)) {
    options.push({ value: selected, key: selected, label: selected });
  }

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
          disabled={disabled || unavailable}
          onChange={(event) => onConfigChange(USE_VISION_KEY, event.target.checked)}
        />
      </label>
      {useVision && (
        <>
          <span className={styles.switchLabel}>{t("capability.ppt_builder.fields.labelling_model.title")}</span>
          <p className={styles.hint}>{changeHint}</p>
          <Select
            size="small"
            compact
            ariaLabel={t("capability.ppt_builder.fields.labelling_model.title")}
            options={options}
            value={selected}
            disabled={disabled}
            onChange={(value) => onConfigChange(LABELLING_MODEL_KEY, value === AGENT_DEFAULT ? null : value)}
          />
        </>
      )}
    </div>
  );
}
