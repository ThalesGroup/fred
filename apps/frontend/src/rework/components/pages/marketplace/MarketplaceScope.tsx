// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { Spinner } from "@shared/atoms/Spinner/Spinner";

/** Catalogue permission stays independent of organization-library access. */
export default function MarketplaceScope({ children }: { children: (marketplaceSpaceId: string) => ReactNode }) {
  const { t } = useTranslation();
  const { organizationId, marketplaces, loading, error } = useWorkingOrganization();
  if (error || marketplaces.isError) return <ServiceNotice icon="lock" title={t("rework.manager.unavailable")} />;
  if (loading || !marketplaces.currentData) return <Spinner size={20} />;
  if (!organizationId || !marketplaces.currentData.items.some((item) => item.space_id === organizationId))
    return <ServiceNotice icon="lock" title={t("rework.localMarketplace.noAccess")} />;
  return children(organizationId);
}
