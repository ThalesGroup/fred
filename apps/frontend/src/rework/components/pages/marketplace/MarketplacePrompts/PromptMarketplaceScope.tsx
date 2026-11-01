// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useState, type ReactNode } from "react";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useTranslation } from "react-i18next";
import Select from "@shared/molecules/Select/Select";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { usePromptMarketplacesQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";

/** Publication context is intentionally separate from general space membership:
 * an invitation admits this catalogue without opening other space domains. */
export default function PromptMarketplaceScope({ children }: { children: (organizationId: string) => ReactNode }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string>();
  const context = usePromptMarketplacesQuery(
    {},
    { ...crossSessionRefreshOptions(false), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(context.refetch, false);
  if (context.isError) return <ServiceNotice icon="lock" title={t("rework.manager.unavailable")} />;
  if (!context.currentData) return <Spinner size={20} />;
  const organizations = context.currentData.items;
  const organization = organizations.find((item) => item.organization_id === selected) ?? organizations[0];
  if (!organization) return <ServiceNotice icon="lock" title={t("rework.promptPublication.noAccess")} />;
  return (
    <>
      <Select
        size="small"
        compact
        label={t("rework.manager.kinds.organization")}
        value={organization.organization_id}
        options={organizations.map((item) => ({
          key: item.organization_id,
          value: item.organization_id,
          label: item.name,
        }))}
        onChange={setSelected}
      />
      {children(organization.organization_id)}
    </>
  );
}
