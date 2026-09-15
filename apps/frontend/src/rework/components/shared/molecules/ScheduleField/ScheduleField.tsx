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

import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { IntervalSchedule } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./ScheduleField.module.css";

/** How often something recurs, edited as a duration.
 *
 * Nothing here is about Knowledge Bases: a recurring administration task wants
 * the same field. It edits the `Schedule` the Control Plane's OpenAPI slice
 * generates, so the shape it produces is the shape the API accepts, with no
 * translation in between.
 *
 * One kind today — `interval` — and the value carries its own discriminator,
 * so `cron` and `calendar` arrive as another branch here rather than as a
 * change to everything that holds a schedule.
 */

/** A duration the user picks in the unit they think in, stored in seconds
 *  because that is what the engine underneath measures. */
const UNITS = [
  { key: "minutes", seconds: 60 },
  { key: "hours", seconds: 3600 },
  { key: "days", seconds: 86400 },
] as const;

type UnitKey = (typeof UNITS)[number]["key"];

/** The largest unit that divides this duration exactly.
 *
 * So 3600 comes back as "1 hour" rather than "60 minutes": a user reads back
 * what they would have typed, not what the engine stores.
 */
export function splitDuration(seconds: number): { every: number; unit: UnitKey } {
  for (const unit of [...UNITS].reverse()) {
    if (seconds % unit.seconds === 0) {
      return { every: seconds / unit.seconds, unit: unit.key };
    }
  }
  return { every: seconds, unit: "minutes" };
}

function toSeconds(every: number, unit: UnitKey): number {
  return every * (UNITS.find((candidate) => candidate.key === unit)?.seconds ?? 60);
}

/** The value this field edits, with its discriminator present rather than
 *  optional — which is the shape the generated API type carries. */
export type IntervalScheduleValue = { type: "interval" } & IntervalSchedule;

export interface ScheduleFieldProps {
  value: IntervalScheduleValue;
  onChange: (schedule: IntervalScheduleValue) => void;
  disabled?: boolean;
  /** Shown under the field. Callers explain what recurs, in their own words. */
  explanation?: string;
}

export default function ScheduleField({ value, onChange, disabled, explanation }: ScheduleFieldProps) {
  const { t } = useTranslation();
  const { every, unit } = useMemo(() => splitDuration(value.every_seconds), [value.every_seconds]);

  const unitOptions: OptionModel<UnitKey>[] = UNITS.map((candidate) => ({
    key: candidate.key,
    value: candidate.key,
    label: t(`rework.schedule.unit.${candidate.key}`),
  }));

  const emit = (nextEvery: number, nextUnit: UnitKey) => {
    // A period of zero or less has no meaning and the API refuses it, so the
    // field never emits one rather than letting a submit fail.
    onChange({ type: "interval", every_seconds: toSeconds(Math.max(1, nextEvery), nextUnit) });
  };

  return (
    <div className={styles.field}>
      <span className={styles.label}>{t("rework.schedule.label")}</span>
      <div className={styles.row}>
        <TextInput
          type="number"
          min={1}
          value={String(every)}
          onChange={(event) => emit(Number(event.target.value), unit)}
          disabled={disabled}
          size="medium"
          aria-label={t("rework.schedule.every")}
        />
        <Select<UnitKey>
          options={unitOptions}
          value={unit}
          onChange={(nextUnit) => emit(every, nextUnit)}
          size="medium"
          disabled={disabled}
          ariaLabel={t("rework.schedule.unit.label")}
        />
      </div>
      {explanation && <span className={styles.explanation}>{explanation}</span>}
    </div>
  );
}
