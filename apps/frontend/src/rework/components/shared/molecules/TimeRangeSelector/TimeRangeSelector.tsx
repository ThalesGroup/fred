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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import CustomRangePanel from "./CustomRangePanel";
import { TIME_PRESETS, TimePresetKey, TimeRange } from "./timeRange.types";
import styles from "./TimeRangeSelector.module.scss";

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}

function formatRangeLabel(range: TimeRange, t: (k: string) => string): string {
  if (range.presetKey) return t(`rework.analytics.presets.${range.presetKey}`);
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return `${fmt(range.since)} – ${fmt(range.until)}`;
}

export default function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen]);

  const selectPreset = (key: TimePresetKey) => {
    const preset = TIME_PRESETS.find((p) => p.key === key)!;
    onChange({ ...preset.resolve(), presetKey: key });
    setIsOpen(false);
  };

  const applyCustom = (since: string, until: string) => {
    onChange({ since, until });
    setIsOpen(false);
  };

  return (
    <div className={styles.container} ref={containerRef} data-open={isOpen}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        <div className={styles.triggerInner}>
          <Icon category="outlined" type="schedule" />
          <span className={styles.label}>{formatRangeLabel(value, t)}</span>
          <Icon category="outlined" type="arrow_drop_down" />
        </div>
      </button>

      {isOpen && (
        <div className={styles.dropdown} role="dialog">
          <CustomRangePanel initialSince={value.since} initialUntil={value.until} onApply={applyCustom} />

          <div className={styles.divider} />

          <div className={styles.presets}>
            {TIME_PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                className={`${styles.presetItem} ${value.presetKey === preset.key ? styles.active : ""}`}
                onClick={() => selectPreset(preset.key)}
              >
                {t(preset.labelKey)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
