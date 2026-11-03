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
import Button from "@shared/atoms/Button/Button.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import { useSelfTestFamilies } from "../../../../features/pipeline/families";
import { AuthorizationExtras } from "./AuthorizationExtras";
import { FamilySection } from "./FamilySection";
import { buildCombinedReport } from "./report";
import styles from "./SelfTestPage.module.css";

export default function SelfTestPage() {
  const { t } = useTranslation();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const families = useSelfTestFamilies();
  const [extrasRunning, setExtrasRunning] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [copied, setCopied] = useState(false);
  const busy = runningAll || extrasRunning || families.some((f) => f.run.isRunning);
  const hasSteps = families.some((f) => f.run.steps.length > 0);

  // Sequential, so each family keeps the one-run-at-a-time rule; a failure never stops the next.
  const runAll = async () => {
    setRunningAll(true);
    try {
      for (const family of families) {
        if (!mounted.current) break;
        try {
          await family.run.start();
        } catch {
          // The family's own report already shows what it reached; the next one still runs.
        }
      }
    } finally {
      if (mounted.current) setRunningAll(false);
    }
  };

  const copyAll = async () => {
    const sections = families.map((f) => ({
      title: t(`rework.selftest.families.${f.id}.title`),
      steps: f.run.steps,
    }));
    if (await writeRichClipboard("", buildCombinedReport(sections, window.location.origin, new Date()))) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.selftest.page.title")}
        subtitle={t("rework.selftest.page.subtitle")}
        actions={
          <div className={styles.pageActions}>
            <Button
              color="secondary"
              variant="outlined"
              size="medium"
              icon={{ category: "outlined", type: "content_copy", filled: false }}
              onClick={() => void copyAll()}
              disabled={!hasSteps || busy}
            >
              {copied ? t("rework.selftest.report.copied") : t("rework.selftest.page.copyAll")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "rocket_launch", filled: false }}
              onClick={() => void runAll()}
              disabled={busy}
            >
              {runningAll ? t("rework.selftest.report.running") : t("rework.selftest.page.runAll")}
            </Button>
          </div>
        }
      />
      <ServiceNotice
        icon="schedule"
        color="info"
        title={t("rework.selftest.page.durationTitle")}
        description={t("rework.selftest.page.durationDescription")}
      />
      {families.map((family) => (
        <FamilySection
          key={family.id}
          family={family}
          busy={busy}
          notice={
            family.id === "authorization" ? (
              <ServiceNotice
                icon="info"
                color="info"
                title={t("rework.selftest.authz.notice.title")}
                description={t("rework.selftest.authz.notice.description")}
              />
            ) : undefined
          }
        >
          {family.id === "authorization" && <AuthorizationExtras busy={busy} onRunningChange={setExtrasRunning} />}
        </FamilySection>
      ))}
    </div>
  );
}
