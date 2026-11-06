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
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge.tsx";
import { TaskProgressBar } from "@shared/atoms/TaskProgressBar/TaskProgressBar.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import type { SelfTestFamily } from "../../../../features/pipeline/familyCatalog";
import { FamilySection } from "./FamilySection";
import { buildCombinedReport, type ReportSection } from "./report";
import styles from "./SelfTestPage.module.css";

export interface SelfTestGroup {
  id: string;
  title: string;
  families: SelfTestFamily[];
}

interface Props {
  groups?: SelfTestGroup[];
  families?: SelfTestFamily[];
  setup?: (busy: boolean) => ReactNode;
  promptSetup?: (busy: boolean) => ReactNode;
  manual?: (props: {
    busy: boolean;
    onRunningChange: (busy: boolean) => void;
    onReportsChange: (reports: ReportSection[]) => void;
  }) => ReactNode;
}

export function SelfTestView({ families: fallbackFamilies = [], groups, setup, promptSetup, manual }: Props) {
  const { t } = useTranslation();
  const families = groups ? groups.flatMap((group) => group.families) : fallbackFamilies;
  const pathKey = groups?.map((group) => `${group.id}:${group.title}`).join("|");
  const currentPath = useRef(pathKey);
  currentPath.current = pathKey;
  const levelSections = useRef(new Map<string, HTMLDetailsElement>());
  const sequence = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      sequence.current += 1;
    };
  }, []);
  const [manualReports, setManualReports] = useState<ReportSection[]>([]);
  const [extrasRunning, setExtrasRunning] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [copied, setCopied] = useState(false);
  const busy = runningAll || extrasRunning || families.some((f) => f.run.isRunning);
  const hasSteps = families.some((f) => f.run.steps.length > 0) || manualReports.some((s) => s.steps.length > 0);

  // Sequential, so each family keeps the one-run-at-a-time rule; a failure never stops the next.
  const runAll = async () => {
    if (busy) return;
    const token = ++sequence.current;
    const selectedPath = pathKey;
    for (const section of levelSections.current.values()) section.open = false;
    setRunningAll(true);
    for (const family of families) family.run.reset?.();
    try {
      for (const family of families) {
        if (!mounted.current || sequence.current !== token || currentPath.current !== selectedPath) break;
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
    if (
      await writeRichClipboard(
        "",
        buildCombinedReport(
          sections,
          window.location.origin,
          new Date(),
          manualReports,
          groups?.map((group) => ({
            title: group.title,
            sections: group.families.map((family) => ({
              title: t(`rework.selftest.families.${family.id}.title`),
              steps: family.run.steps,
            })),
          })),
        ),
      )
    ) {
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
              {runningAll
                ? t("rework.selftest.report.running")
                : t(
                    groups
                      ? "rework.selftest.page.runPath"
                      : setup
                        ? "rework.selftest.page.runStandard"
                        : "rework.selftest.page.runAll",
                  )}
            </Button>
          </div>
        }
      />
      <ServiceNotice
        icon="schedule"
        color="info"
        title={t(setup ? "rework.selftest.page.weaverNotice" : "rework.selftest.page.durationTitle")}
        description={t(setup ? "rework.selftest.page.weaverHelp" : "rework.selftest.page.durationDescription")}
      />
      {setup?.(busy)}
      {groups
        ? groups.map((group) => {
            const steps = group.families.flatMap((family) => family.run.steps);
            const isRunning =
              group.families.some((family) => family.run.isRunning) || steps.some((step) => step.status === "running");
            const passed = steps.filter((step) => step.status === "passed").length;
            const failed = steps.filter((step) => step.status === "failed").length;
            const skipped = steps.filter((step) => step.status === "skipped").length;
            const status = isRunning
              ? "running"
              : failed
                ? "failed"
                : passed
                  ? "passed"
                  : skipped
                    ? "skipped"
                    : "notRun";
            return (
              <details
                key={group.id}
                className={styles.testSection}
                ref={(section) => {
                  if (section) levelSections.current.set(group.id, section);
                  else levelSections.current.delete(group.id);
                }}
              >
                <summary className={`${styles.header} ${styles.groupHeader}`}>
                  <span className={styles.title}>{group.title}</span>
                  <span role="status">
                    <StatusBadge
                      label={t(`rework.selftest.report.sectionStatus.${status}`)}
                      tone={isRunning ? "info" : failed ? "error" : passed ? "success" : "neutral"}
                    />
                  </span>
                  <span className={styles.counts}>
                    {t("rework.selftest.report.counts", {
                      passed,
                      failed,
                      skipped,
                      total: steps.length,
                    })}
                  </span>
                  {isRunning && (
                    <span className={styles.groupProgress}>
                      <TaskProgressBar state="running" progress={null} />
                    </span>
                  )}
                </summary>
                {group.families.map((family) => (
                  <FamilySection
                    key={family.id}
                    family={family}
                    busy={busy}
                    weaver
                    reportTitle={`${group.title} / ${t(`rework.selftest.families.${family.id}.title`)}`}
                  />
                ))}
              </details>
            );
          })
        : families.map((family) => (
            <FamilySection
              key={family.id}
              family={family}
              busy={busy}
              weaver={!!setup}
              notice={
                family.id === "authorization" ? (
                  <ServiceNotice
                    icon="info"
                    color="info"
                    title={t("rework.selftest.authz.notice.title")}
                    description={t(
                      setup ? "rework.selftest.authz.notice.weaver" : "rework.selftest.authz.notice.description",
                    )}
                  />
                ) : family.id === "prompts" ? (
                  promptSetup?.(busy)
                ) : undefined
              }
            >
              {family.id === "authorization" &&
                manual?.({ busy, onRunningChange: setExtrasRunning, onReportsChange: setManualReports })}
            </FamilySection>
          ))}
      {groups && manual && (
        <section className={styles.testSection}>
          <h2 className={styles.title}>{t("rework.selftest.page.manualTests")}</h2>
          {manual?.({ busy, onRunningChange: setExtrasRunning, onReportsChange: setManualReports })}
        </section>
      )}
    </div>
  );
}
