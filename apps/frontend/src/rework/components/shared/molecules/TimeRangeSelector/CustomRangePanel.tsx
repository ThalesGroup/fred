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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import DateTimeInput from "@shared/atoms/DateTimeInput/DateTimeInput";
import Button from "@shared/atoms/Button/Button";
import styles from "./TimeRangeSelector.module.scss";

interface CustomRangePanelProps {
  initialSince: string;
  initialUntil: string;
  onApply: (since: string, until: string) => void;
}

function toDateTimeLocal(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function CustomRangePanel({ initialSince, initialUntil, onApply }: CustomRangePanelProps) {
  const { t } = useTranslation();
  const [since, setSince] = useState(toDateTimeLocal(initialSince));
  const [until, setUntil] = useState(toDateTimeLocal(initialUntil));

  const isValid = since && until && since < until;

  return (
    <div className={styles.customPanel}>
      <DateTimeInput
        label={t("rework.analytics.timeRange.since")}
        value={since}
        max={until || undefined}
        onChange={(e) => setSince(e.target.value)}
      />
      <DateTimeInput
        label={t("rework.analytics.timeRange.until")}
        value={until}
        min={since || undefined}
        onChange={(e) => setUntil(e.target.value)}
      />
      <Button
        color="primary"
        variant="filled"
        size="small"
        disabled={!isValid}
        onClick={() => isValid && onApply(new Date(since).toISOString(), new Date(until).toISOString())}
      >
        {t("rework.analytics.timeRange.apply")}
      </Button>
    </div>
  );
}
