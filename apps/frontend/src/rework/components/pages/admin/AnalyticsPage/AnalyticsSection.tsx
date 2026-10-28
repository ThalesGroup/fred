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

import { createContext, type ReactNode, useContext } from "react";
import { useTranslation } from "react-i18next";
import { MaterialIcon } from "@shared/atoms/Icon/Icon";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import styles from "./AnalyticsPage.module.css";

/** Definition plus an optional "How to read it" line, as one tooltip panel. */
export function HintContent({ def, how }: { def: string; how?: string }) {
  const { t } = useTranslation();
  return (
    <span className={styles.hintPanel}>
      <span>{def}</span>
      {how && (
        <span>
          <strong>{t("rework.analytics.howToRead")}</strong> {how}
        </span>
      )}
    </span>
  );
}

/** A discreet info icon, not a button: focusable so the tooltip also opens from the keyboard. */
export function InfoIcon({ label, content }: { label: string; content: ReactNode }) {
  return (
    <Tooltip content={content}>
      <span className={styles.infoIcon} tabIndex={0} aria-label={label}>
        <MaterialIcon type="info" />
      </span>
    </Tooltip>
  );
}

export function InfoHint({ label, def, how }: { label: string; def: string; how?: string }) {
  const { t } = useTranslation();
  return <InfoIcon label={t("rework.analytics.moreInfo", { label })} content={<HintContent def={def} how={how} />} />;
}

// True inside a section card: tiles there sit on the second surface.
const SectionContext = createContext(false);
export const useInSection = () => useContext(SectionContext);

/** The info icon of a chart title, from `rework.analytics.charts.<id>.def`. */
export function ChartHint({ id, title }: { id: string; title: string }) {
  const { t } = useTranslation();
  return <InfoHint label={title} def={t(`rework.analytics.charts.${id}.def`)} />;
}

/** A question-led card of tiles and charts; `id` names its keys under `rework.analytics.sections`. */
export function AnalyticsSection({
  id,
  aside,
  children,
}: {
  id: string;
  /** A short figure for the whole section, at the right of its heading, e.g. "42 active teams out of 57". */
  aside?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const key = `rework.analytics.sections.${id}`;
  const def = t(`${key}.def`, { defaultValue: "" });
  const title = t(`${key}.title`);
  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionHeading}>
          <span className={styles.eyebrow}>{t(`${key}.eyebrow`)}</span>
          <h2 className={styles.sectionTitle}>{title}</h2>
        </div>
        <div className={styles.sectionAside}>
          {aside}
          {def && <InfoHint label={title} def={def} how={t(`${key}.how`, { defaultValue: "" }) || undefined} />}
        </div>
      </div>
      <SectionContext.Provider value={true}>{children}</SectionContext.Provider>
    </section>
  );
}

export function AnalyticsServiceDown() {
  const { t } = useTranslation();
  return (
    <ServiceNotice
      icon="cloud_off"
      title={t("rework.serviceNotice.controlPlane.title")}
      description={t("rework.serviceNotice.controlPlane.description")}
      centered
    />
  );
}
