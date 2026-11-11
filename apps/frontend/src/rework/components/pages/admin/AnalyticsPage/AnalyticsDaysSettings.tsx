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

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import type { AnalyticsDays } from "./analyticsQuery";
import styles from "./AnalyticsDaysSettings.module.css";

interface AnalyticsDaysSettingsProps {
  value: AnalyticsDays;
  onChange: (days: AnalyticsDays) => void;
}

/** Header button and dialog choosing the counted days. Switches apply at once, so the dialog only closes. */
export default function AnalyticsDaysSettings({ value, onChange }: AnalyticsDaysSettingsProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const weekendsId = useId();
  const holidaysId = useId();

  return (
    <>
      <Tooltip text={t("rework.analytics.days.open")}>
        <IconButton
          variant="icon"
          size="medium"
          color="on-surface-retreat"
          icon={{ category: "outlined", type: "settings" }}
          aria-label={t("rework.analytics.days.open")}
          aria-haspopup="dialog"
          onClick={() => setOpen(true)}
        />
      </Tooltip>
      <Dialog
        open={open}
        title={t("rework.analytics.days.title")}
        hideCancel
        confirmLabel={t("common.close")}
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      >
        <div className={styles.body}>
          <p className={styles.intro}>{t("rework.analytics.days.intro")}</p>
          <div className={styles.row}>
            <span id={weekendsId}>{t("rework.analytics.days.excludeWeekends")}</span>
            <Switch
              size="small"
              aria-labelledby={weekendsId}
              checked={value.excludeWeekends}
              onChange={(event) => onChange({ ...value, excludeWeekends: event.target.checked })}
            />
          </div>
          <div className={styles.row}>
            <span id={holidaysId}>{t("rework.analytics.days.excludeHolidays")}</span>
            <Switch
              size="small"
              aria-labelledby={holidaysId}
              checked={value.excludeHolidays}
              onChange={(event) => onChange({ ...value, excludeHolidays: event.target.checked })}
            />
          </div>
        </div>
      </Dialog>
    </>
  );
}
