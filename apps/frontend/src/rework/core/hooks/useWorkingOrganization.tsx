// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { useTranslation } from "react-i18next";
import { useMySpacesQuery, useMarketplacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { sessionQueryArgs } from "../../../slices/controlPlane/controlPlaneApi";
import { KeyCloakService } from "../../../security/KeycloakService";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "./crossSessionRefresh";

/** One navigation preference per identity and tab. Memberships remain server-owned. */
function useSelection() {
  const { t } = useTranslation();
  const memberships = useMySpacesQuery(undefined, crossSessionRefreshOptions(false));
  const marketplaces = useMarketplacesQuery(sessionQueryArgs({}), crossSessionRefreshOptions(false));
  useRefetchOnWindowFocus(memberships.refetch, false);
  useRefetchOnWindowFocus(marketplaces.refetch, false);
  const storageKey = `working.organization:${KeyCloakService.GetSessionIdentity()}`;
  const [selectedId, setSelectedId] = useState<string | undefined>(() => {
    try {
      return sessionStorage.getItem(storageKey) ?? undefined;
    } catch {
      return undefined;
    }
  });
  const organizations = useMemo(() => {
    const choices = new Map<string, { id: string; name: string }>();
    if (memberships.isError) return [];
    const spaces = memberships.currentData ?? [];
    for (const space of spaces) {
      if (space.kind === "organization") choices.set(space.id, { id: space.id, name: space.name });
    }
    // Participation in a catalogue does not grant access to its organization's content.
    if (!marketplaces.isError) {
      for (const catalogue of marketplaces.currentData?.items ?? [])
        choices.set(catalogue.space_id, { id: catalogue.space_id, name: catalogue.name });
    }
    for (const space of spaces) {
      if (!choices.has(space.organization_id))
        choices.set(space.organization_id, {
          id: space.organization_id,
          name: t("rework.home.organizationOf", { name: space.name }),
        });
    }
    return [...choices.values()].sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
  }, [memberships.currentData, memberships.isError, marketplaces.currentData, marketplaces.isError, t]);
  const loading = memberships.isLoading || marketplaces.isLoading;
  const error = memberships.error;
  // A revoked preference never silently changes the organization of subsequent writes.
  const organization =
    !loading && !error
      ? (organizations.find((item) => item.id === selectedId) ?? (selectedId ? undefined : organizations[0]))
      : undefined;
  const organizationId = organization?.id;
  useEffect(() => {
    if (!organizationId) return;
    setSelectedId(organizationId);
    try {
      sessionStorage.setItem(storageKey, organizationId);
    } catch {
      // Storage may be disabled; the current tab still has a valid in-memory choice.
    }
  }, [organizationId, storageKey]);
  const selectOrganization = (id: string) => {
    if (loading || error || !organizations.some((item) => item.id === id)) return false;
    setSelectedId(id);
    return true;
  };
  return { organizationId, organization, organizations, selectOrganization, loading, error, memberships, marketplaces };
}

const WorkingOrganizationContext = createContext<ReturnType<typeof useSelection> | null>(null);

export function WorkingOrganizationProvider({ children }: PropsWithChildren) {
  return <SessionOrganization key={KeyCloakService.GetSessionIdentity()}>{children}</SessionOrganization>;
}

function SessionOrganization({ children }: PropsWithChildren) {
  const context = useSelection();
  return <WorkingOrganizationContext.Provider value={context}>{children}</WorkingOrganizationContext.Provider>;
}

export function useWorkingOrganization() {
  const context = useContext(WorkingOrganizationContext);
  if (!context) throw new Error("Working organization provider missing");
  return context;
}
