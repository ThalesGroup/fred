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
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import type { SelfTestFamily } from "../../../../features/pipeline/families";
import { StepReportPanel } from "./StepReportPanel";
import styles from "./SelfTestPage.module.css";

interface FamilySectionProps {
  family: SelfTestFamily;
  busy: boolean;
  notice?: ReactNode;
  children?: ReactNode;
}

export function FamilySection({ family, busy, notice, children }: FamilySectionProps) {
  const { t } = useTranslation();
  const { run } = family;
  return (
    <section className={styles.testSection} data-family={family.id}>
      <div className={styles.header}>
        <h2 className={styles.title}>{t(`rework.selftest.families.${family.id}.title`)}</h2>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: family.icon, filled: false }}
          onClick={() => void run.start()}
          disabled={busy}
        >
          {run.isRunning ? t("rework.selftest.report.running") : t("rework.selftest.family.run")}
        </Button>
      </div>
      <p className={styles.subtitle}>{t(`rework.selftest.families.${family.id}.subtitle`)}</p>
      {notice}
      <StepReportPanel steps={run.steps} isRunning={run.isRunning} emptyLabel={t("rework.selftest.report.empty")} />
      {children}
    </section>
  );
}
