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

import { useTranslation } from "react-i18next";
import { MaterialIcon } from "@shared/atoms/Icon/Icon";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import type { AnalyticsAdoptionResponse, PeriodValue } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { InfoHint } from "./AnalyticsSection";
import { formatValue, periodDelta } from "./analyticsFormat";
import styles from "./AnalyticsPage.module.css";

const KEY = "rework.analytics.funnel";

interface AdoptionFunnelProps {
  data: AnalyticsAdoptionResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}

/** Access, then visitors, then active users, each with the rate of the step that leads to it. */
export default function AdoptionFunnel({ data, isLoading, isError }: AdoptionFunnelProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const title = t(`${KEY}.title`);
  const steps = [
    { id: "peopleWithAccess", value: data?.people_with_access ?? null, how: true },
    { id: "visitors", value: data?.visitors.current ?? null, rate: { id: "visitRate", period: data?.visit_rate } },
    {
      id: "activeUsers",
      value: data?.active_users.current ?? null,
      rate: { id: "visitorToActive", period: data?.visitor_to_active_rate },
    },
  ];
  const max = Math.max(0, ...steps.map((s) => s.value ?? 0));

  return (
    <section className={`${styles.block} ${styles.funnel}`} aria-label={title}>
      <div className={styles.blockHeader}>
        <h3 className={styles.blockTitle}>{title}</h3>
        <InfoHint label={title} def={t(`${KEY}.def`)} how={t(`${KEY}.how`)} />
      </div>
      {isError ? (
        <p role="alert" className={styles.note}>
          {t("common.loadingError")}
        </p>
      ) : isLoading ? (
        <p role="status" className={styles.note}>
          {t("common.loading")}
        </p>
      ) : (
        <>
          {steps.map((step) => {
            const label = t(`${KEY}.steps.${step.id}.label`);
            return (
              <div key={step.id} className={styles.funnelStep}>
                {step.rate && <StepRate id={step.rate.id} period={step.rate.period} />}
                <div className={styles.funnelRow}>
                  <span className={styles.funnelLabel}>
                    {label}
                    <InfoHint
                      label={label}
                      def={t(`${KEY}.steps.${step.id}.def`)}
                      how={step.how ? t(`${KEY}.steps.${step.id}.how`) : undefined}
                    />
                  </span>
                  <div className={styles.funnelTrack}>
                    <ProgressBar theme="primary" current={step.value ?? 0} max={max} aria-label={label} />
                  </div>
                  <span className={styles.funnelValue}>
                    {step.value == null ? t(`${KEY}.unknown`) : formatValue(step.value, "count", lng)}
                  </span>
                </div>
              </div>
            );
          })}
          <AdoptionRate period={data?.adoption_rate} />
        </>
      )}
    </section>
  );
}

function Delta({ period }: { period: PeriodValue | undefined }) {
  const { t, i18n } = useTranslation();
  const delta = periodDelta(period, "points", t, i18n.language);
  if (!delta) return null;
  const tone = delta.tone === "positive" ? styles.positive : delta.tone === "negative" ? styles.negative : "";
  return <span className={`${styles.funnelDelta} ${tone}`}>{delta.label}</span>;
}

function StepRate({ id, period }: { id: string; period: PeriodValue | undefined }) {
  const { t, i18n } = useTranslation();
  const key = `${KEY}.rates.${id}`;
  const name = t(`${key}.name`);
  if (period?.current == null) return null;
  return (
    <div className={styles.funnelRate}>
      <span className={styles.funnelArrow}>
        <MaterialIcon type="arrow_downward" />
      </span>
      <span>
        <strong>{formatValue(period.current, "percent", i18n.language)}</strong> {t(`${key}.text`)}
      </span>
      <InfoHint label={name} def={`${name} - ${t(`${key}.def`)}`} how={t(`${key}.how`)} />
      <Delta period={period} />
    </div>
  );
}

function AdoptionRate({ period }: { period: PeriodValue | undefined }) {
  const { t, i18n } = useTranslation();
  const label = t(`${KEY}.adoption.label`);
  return (
    <div className={styles.funnelAdoption}>
      <span className={styles.funnelLabel}>
        {label}
        <InfoHint label={label} def={t(`${KEY}.adoption.def`)} how={t(`${KEY}.adoption.how`)} />
      </span>
      <span className={styles.funnelAdoptionValue}>
        {period?.current == null ? t(`${KEY}.unknown`) : formatValue(period.current, "percent", i18n.language)}
      </span>
      <span className={styles.note}>{t(`${KEY}.adoption.text`)}</span>
      <Delta period={period} />
    </div>
  );
}
