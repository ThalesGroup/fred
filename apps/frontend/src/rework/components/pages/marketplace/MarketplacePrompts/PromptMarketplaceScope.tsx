// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState, type ReactNode } from "react";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useTranslation } from "react-i18next";
import Select from "@shared/molecules/Select/Select";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { useMarketplacesQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";

/** Marketplace participation admits published definitions without granting source-space access. */
export default function PromptMarketplaceScope({ children }: { children: (marketplaceSpaceId: string) => ReactNode }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string>();
  const context = useMarketplacesQuery({}, { ...crossSessionRefreshOptions(false), refetchOnMountOrArgChange: true });
  useRefetchOnWindowFocus(context.refetch, false);
  if (context.isError) return <ServiceNotice icon="lock" title={t("rework.manager.unavailable")} />;
  if (!context.currentData) return <Spinner size={20} />;
  const marketplaces = context.currentData.items;
  const marketplace = marketplaces.find((item) => item.space_id === selected) ?? marketplaces[0];
  if (!marketplace) return <ServiceNotice icon="lock" title={t("rework.promptPublication.noAccess")} />;
  return (
    <>
      <Select
        size="small"
        compact
        label={t("rework.promptPublication.marketplace")}
        value={marketplace.space_id}
        options={marketplaces.map((item) => ({
          key: item.space_id,
          value: item.space_id,
          label: item.name,
        }))}
        onChange={setSelected}
      />
      {children(marketplace.space_id)}
    </>
  );
}
