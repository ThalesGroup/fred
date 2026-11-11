// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { weaverFeatures, type WeaverFeature } from "./catalog";
import styles from "./WeaverFeaturePage.module.css";

export default function WeaverFeaturePage({ feature }: { feature: WeaverFeature }) {
  const { t } = useTranslation();
  const entry = weaverFeatures.find((entry) => entry.id === feature)!;
  return (
    <section className={styles.page}>
      <PageHeader title={t(`rework.weaver.features.${feature}.title`)} />
      <ServiceNotice title={t("rework.weaver.pending")} description={t(`rework.weaver.features.${feature}.next`)} />
      {import.meta.env.DEV && (
        <ServiceNotice title={t("rework.weaver.previewTitle")} description={t("rework.weaver.previewStart")} />
      )}
      {import.meta.env.DEV && (
        <a href={`http://localhost:5174/swift-preview.html#${entry.preview}`} target="_blank" rel="noreferrer">
          {t("rework.weaver.openPreview")}
        </a>
      )}
    </section>
  );
}
