// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useMarketplaceEntriesQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { sessionQueryArgs } from "../../../../../slices/controlPlane/controlPlaneApi";
import MarketplaceDetailDialog from "../../marketplace/MarketplaceDetailDialog";
import MarketplaceScope from "../../marketplace/MarketplaceScope";
import type { HomePeriod } from "../HomePage";
import styles from "./MarketplaceTopPrompts.module.scss";

const TOP_N = 8;

/** Keep Home's card layout. The period, ranking and usage chart await the
 * usage contract; only the actual published definitions are read here. */
export default function MarketplaceTopPrompts(_props: { period: HomePeriod }) {
  const { t } = useTranslation();
  return (
    <section className={styles.section} aria-label={t("rework.home.topPrompts.title")}>
      <div className={styles.head}>
        <Icon category="outlined" type="storefront" />
        <h2 className={styles.title}>{t("rework.home.topPrompts.title")}</h2>
      </div>
      <ServiceNotice icon="info" title={t("rework.promptPublication.metricsUnavailable")} />
      <MarketplaceScope>
        {(marketplaceSpaceId) => <PublishedCards key={marketplaceSpaceId} marketplaceSpaceId={marketplaceSpaceId} />}
      </MarketplaceScope>
    </section>
  );
}

function PublishedCards({ marketplaceSpaceId }: { marketplaceSpaceId: string }) {
  const { t } = useTranslation();
  const query = useMarketplaceEntriesQuery(sessionQueryArgs({ marketplaceSpaceId, kind: "prompt" }), {
    ...crossSessionRefreshOptions(false),
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(query.refetch, false);
  const [viewingId, setViewingId] = useState<string>();
  if (query.isError) return <ServiceNotice icon="lock" title={t("rework.manager.unavailable")} />;
  if (!query.currentData) return <Spinner size={20} />;
  const prompts = query.currentData.items.slice(0, TOP_N);
  return (
    <>
      {prompts.length === 0 ? (
        <div className={styles.empty}>{t("rework.home.topPrompts.empty")}</div>
      ) : (
        <div className={styles.grid}>
          {prompts.map((prompt) => (
            <div
              key={prompt.entry_id}
              className={styles.card}
              role="button"
              tabIndex={0}
              onClick={() => setViewingId(prompt.entry_id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setViewingId(prompt.entry_id);
                }
              }}
            >
              <span className={styles.team} title={prompt.origin_name}>
                {prompt.origin_name}
              </span>
              <span className={styles.name} title={prompt.display_name}>
                {prompt.display_name}
              </span>
              <div className={styles.foot}>
                <div className={styles.uses}>
                  <span className={styles.usesLbl}>{t("rework.promptPublication.usageUnavailable")}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {viewingId && (
        <MarketplaceDetailDialog
          marketplaceSpaceId={marketplaceSpaceId}
          entryId={viewingId}
          onClose={() => setViewingId(undefined)}
        />
      )}
    </>
  );
}
