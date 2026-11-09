// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useTranslation } from "react-i18next";
import Select from "@shared/molecules/Select/Select";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { useMarketplacesQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";

import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import { KeyCloakService } from "../../../../security/KeycloakService";

/** Marketplace participation admits published definitions without granting source-space access. */
export default function MarketplaceScope({ children }: { children: (marketplaceSpaceId: string) => ReactNode }) {
  return <SessionScope key={KeyCloakService.GetSessionIdentity()}>{children}</SessionScope>;
}

function SessionScope({ children }: { children: (marketplaceSpaceId: string) => ReactNode }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const selected = params.get("catalogue");
  const context = useMarketplacesQuery(sessionQueryArgs({}), {
    ...crossSessionRefreshOptions(false),
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(context.refetch, false);
  if (context.isError) return <ServiceNotice icon="lock" title={t("rework.manager.unavailable")} />;
  if (!context.currentData) return <Spinner size={20} />;
  const marketplaces = context.currentData.items;
  const marketplace = marketplaces.find((item) => item.space_id === selected) ?? marketplaces[0];
  if (!marketplace) return <ServiceNotice icon="lock" title={t("rework.localMarketplace.noAccess")} />;
  return (
    <>
      <Select
        size="small"
        compact
        label={t("rework.localMarketplace.catalogue")}
        value={marketplace.space_id}
        options={marketplaces.map((item) => ({
          key: item.space_id,
          value: item.space_id,
          label: item.name,
        }))}
        onChange={(id) => setParams({ catalogue: id })}
      />
      {children(marketplace.space_id)}
    </>
  );
}
