// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { stripDiacritics } from "@rework/utils/stripDiacritics";
import { formatDateTime } from "@rework/utils/formatDateTime";
import ResourceCard from "@shared/organisms/PromptCard/ResourceCard";
import TablePagination from "@shared/molecules/TablePagination/TablePagination";
import Select from "@shared/molecules/Select/Select";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import {
  enhancedControlPlaneApi,
  useMarketplaceEntriesQuery,
  useOrganizationResourcesQuery,
  useMarketplaceProposalsQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { MarketplaceKind, SubmitProposalRequest } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import MarketplaceDetailDialog from "./MarketplaceDetailDialog";
import MarketplaceProposalDialog from "./MarketplaceProposalDialog";
import { marketplaceError, marketplaceName, savedProposalRequests, useMarketplaceSession } from "./marketplace";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import styles from "./Marketplace.module.css";
import layout from "../PromptsPage/PromptsPage.module.scss";

export default function MarketplacePage({ kind }: { kind: MarketplaceKind }) {
  const { t } = useTranslation();
  const { organizationId, marketplaces, loading, error } = useWorkingOrganization();
  if (loading) return <Spinner size={20} />;
  if (error || !organizationId) return <ServiceNotice icon="lock" title={t("rework.localMarketplace.noAccess")} />;
  const canBrowseCatalogue =
    !marketplaces.isError && !!marketplaces.currentData?.items.some((item) => item.space_id === organizationId);
  return (
    <Catalogue
      key={`${organizationId}:${kind}:${canBrowseCatalogue}`}
      marketplaceSpaceId={organizationId}
      kind={kind}
      canBrowseCatalogue={canBrowseCatalogue}
    />
  );
}

function Catalogue({
  marketplaceSpaceId,
  kind,
  canBrowseCatalogue,
}: {
  marketplaceSpaceId: string;
  kind: MarketplaceKind;
  canBrowseCatalogue: boolean;
}) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const active = useMarketplaceSession();
  const [recoverySource, setRecoverySource] = useState<SubmitProposalRequest>();
  const recoveries = savedProposalRequests(marketplaceSpaceId, kind);
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState(
    !canBrowseCatalogue ? "explore" : params.has("proposal") ? "proposals" : "publications",
  );
  const [origin, setOrigin] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const proposals = view === "proposals";
  const exploring = view === "explore";
  const [resourceId, setResourceId] = useState<string>();
  const resources = useOrganizationResourcesQuery(
    sessionQueryArgs({ organizationId: marketplaceSpaceId, kind, search, page }),
    { ...crossSessionRefreshOptions(!exploring), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(resources.refetch, !exploring);
  const entriesQuery = useMarketplaceEntriesQuery(sessionQueryArgs({ marketplaceSpaceId, kind }), {
    ...crossSessionRefreshOptions(!canBrowseCatalogue || proposals || exploring),
    refetchOnMountOrArgChange: true,
  });
  const proposalsQuery = useMarketplaceProposalsQuery(
    sessionQueryArgs({ marketplaceSpaceId, kind, state: "pending" }),
    { ...crossSessionRefreshOptions(!canBrowseCatalogue || !proposals), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(entriesQuery.refetch, !canBrowseCatalogue || proposals || exploring);
  useRefetchOnWindowFocus(proposalsQuery.refetch, !canBrowseCatalogue || !proposals);
  const query = exploring ? resources : proposals ? proposalsQuery : entriesQuery;
  const resource =
    !resources.isError && !resources.isFetching
      ? resources.currentData?.items.find((item) => item.resource_id === resourceId)
      : undefined;
  const items = query.isError ? [] : ((proposals ? proposalsQuery : entriesQuery).currentData?.items ?? []);
  const origins = [...new Set([origin, ...items.map((item) => item.origin_name)])]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));
  const searchText = stripDiacritics(search).toLocaleLowerCase();
  const rows = items.filter(
    (item) =>
      (!origin || item.origin_name === origin) &&
      [item.display_name, item.description, item.origin_name, item.entry_id].some((text) =>
        stripDiacritics(text).toLocaleLowerCase().includes(searchText),
      ),
  );
  const directoryTotal = resources.currentData?.total;
  const directoryPageCount = Math.max(1, Math.ceil((directoryTotal ?? 0) / 20));
  useEffect(() => {
    if (exploring && directoryTotal !== undefined && page >= directoryPageCount) setPage(directoryPageCount - 1);
  }, [exploring, directoryTotal, page, directoryPageCount]);
  const total = exploring ? (directoryTotal ?? 0) : rows.length;
  const currentPage = Math.min(page, Math.max(0, Math.ceil(total / 20) - 1));
  const open = (id: string) => setParams({ catalogue: marketplaceSpaceId, [proposals ? "proposal" : "entry"]: id });
  const close = () => {
    setResourceId(undefined);
    setParams({ catalogue: marketplaceSpaceId });
  };
  return (
    <div className={layout.pageContainer}>
      <PageHeader
        title={t(`rework.localMarketplace.kinds.${kind}`)}
        actions={
          <div className={layout.searchBar}>
            <SearchInput
              size="xs"
              value={search}
              onChange={(value) => {
                setSearch(value.slice(0, 180));
                setPage(0);
                close();
              }}
              placeholder={t("rework.localMarketplace.search")}
              ariaLabel={t("rework.localMarketplace.search")}
              clearAriaLabel={t("rework.localMarketplace.clearSearch")}
            />
          </div>
        }
      />
      <span className={styles.identity}>
        {t(
          exploring
            ? "rework.resourceDiscovery.hint"
            : `rework.localMarketplace.${proposals ? "proposalsHint" : "catalogueHint"}`,
        )}
      </span>
      <div className={styles.toolbar}>
        <Select
          size="small"
          label={t("rework.localMarketplace.view")}
          value={view}
          onChange={(value) => {
            setView(value);
            setOrigin("");
            setPage(0);
            close();
          }}
          options={(canBrowseCatalogue ? ["publications", "explore", "proposals"] : ["explore"]).map((value) => ({
            key: value,
            value,
            label: t(`rework.localMarketplace.${value}`),
          }))}
        />
        {!exploring && (
          <Select
            size="small"
            label={t("rework.localMarketplace.origin")}
            value={origin}
            disabled={query.isFetching || query.isError || !query.currentData}
            onChange={(value) => {
              setOrigin(value);
              setPage(0);
            }}
            options={[
              { key: "", value: "", label: t("rework.localMarketplace.allOrigins") },
              ...origins.map((name) => ({ key: name, value: name, label: name })),
            ]}
          />
        )}
        <Button
          size="small"
          color="primary"
          variant="outlined"
          icon={{ category: "outlined", type: "refresh" }}
          disabled={query.isFetching}
          onClick={() => {
            if (!active()) return;
            if (exploring) void resources.refetch();
            else
              dispatch(
                enhancedControlPlaneApi.util.invalidateTags([{ type: "MarketplaceContent", id: marketplaceSpaceId }]),
              );
          }}
        >
          {t("rework.localMarketplace.refresh")}
        </Button>
      </div>
      {proposals && recoveries.length > 0 && (
        <section aria-label={t("rework.localMarketplace.savedProposals")}>
          <h2>{t("rework.localMarketplace.savedProposals")}</h2>
          {recoveries.map(({ args: { submitProposalRequest: source }, context }) => (
            <div key={JSON.stringify([source.source_space_id, source.source_resource_id])}>
              <span className={styles.identity}>
                {context?.name ?? t(`rework.localMarketplace.kinds.${kind}`)} ·{" "}
                {context?.destination ?? t("rework.localMarketplace.catalogue")} · {formatDateTime(context?.startedAt)}
              </span>
              <Button
                size="small"
                color="primary"
                variant="outlined"
                onClick={() => {
                  if (active()) setRecoverySource(source);
                }}
              >
                {t("rework.localMarketplace.resumeProposal")}
              </Button>
            </div>
          ))}
        </section>
      )}
      {recoverySource && (
        <MarketplaceProposalDialog source={recoverySource} recoveryOnly onClose={() => setRecoverySource(undefined)} />
      )}
      {query.isError ? (
        <span className={styles.line} role="alert">
          {marketplaceError(query.error, t)}
        </span>
      ) : query.isFetching || !query.currentData ? (
        <span className={styles.line} role="status">
          {t("common.loading")}
        </span>
      ) : !total ? (
        <PageEmptyState
          icon="storefront"
          message={t(
            search || origin || exploring
              ? "rework.localMarketplace.empty"
              : `rework.localMarketplace.${proposals ? "noProposals" : "noPublications"}`,
          )}
          description={t("rework.localMarketplace.catalogueHint")}
        />
      ) : (
        <>
          <div className={layout.promptList}>
            {exploring
              ? resources.currentData?.items.map((item) => (
                  <ResourceCard
                    key={item.resource_id}
                    title={item.display_name}
                    description={item.description}
                    label={`${item.space_name} · ${t(`rework.localMarketplace.spaceKinds.${item.space_kind}`)}`}
                    notice={t("rework.resourceDiscovery.metadataOnly")}
                    onOpen={() => setResourceId(item.resource_id)}
                  />
                ))
              : rows
                  .slice(currentPage * 20, (currentPage + 1) * 20)
                  .map((item) => (
                    <ResourceCard
                      key={"state" in item ? item.proposal_id : item.entry_id}
                      title={item.display_name}
                      label={marketplaceName(item.origin_name, t)}
                      description={item.description}
                      notice={t(
                        "state" in item
                          ? `rework.localMarketplace.states.${item.state}`
                          : "rework.localMarketplace.published",
                      )}
                      onOpen={() => open("state" in item ? item.proposal_id : item.entry_id)}
                    />
                  ))}
          </div>
          {total > 20 && (
            <TablePagination
              totalItems={total}
              currentPage={currentPage}
              pageCount={Math.ceil(total / 20)}
              rowsPerPage={20}
              rowsPerPageOptions={[]}
              onFirst={() => setPage(0)}
              onPrev={() => setPage(currentPage - 1)}
              onNext={() => setPage(currentPage + 1)}
              onLast={() => setPage(Math.ceil(total / 20) - 1)}
              labels={{
                totalItems: (count) => t("dataTable.pagination.totalItems", { count }),
                pageNumber: (page, pageCount) => t("dataTable.pagination.pageNumber", { page, pageCount }),
                first: t("dataTable.pagination.first"),
                prev: t("dataTable.pagination.prev"),
                next: t("dataTable.pagination.next"),
                last: t("dataTable.pagination.last"),
              }}
            />
          )}
        </>
      )}
      {resource && (
        <MarketplaceDetailDialog marketplaceSpaceId={marketplaceSpaceId} resource={resource} onClose={close} />
      )}
      {canBrowseCatalogue && (params.get("entry") || params.get("proposal")) && (
        <MarketplaceDetailDialog
          key={params.get("proposal") ?? params.get("entry")}
          marketplaceSpaceId={marketplaceSpaceId}
          entryId={params.get("entry") ?? undefined}
          proposalId={params.get("proposal") ?? undefined}
          onClose={close}
        />
      )}
    </div>
  );
}
