// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useDispatch } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { formatDateTime } from "@rework/utils/formatDateTime";
import ResourceCard from "@shared/organisms/PromptCard/ResourceCard";
import cardStyles from "@shared/organisms/PromptCard/PromptCard.module.scss";
import Chip from "@shared/atoms/Chip/Chip";
import TablePagination from "@shared/molecules/TablePagination/TablePagination";
import Select from "@shared/molecules/Select/Select";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import {
  enhancedControlPlaneApi,
  useMarketplaceEntriesQuery,
  useMarketplaceProposalsQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  MarketplaceKind,
  ProposalState,
  SubmitProposalRequest,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import MarketplaceScope from "./MarketplaceScope";
import MarketplaceDetailDialog from "./MarketplaceDetailDialog";
import MarketplaceProposalDialog from "./MarketplaceProposalDialog";
import { marketplaceError, marketplaceName, savedProposalRequests, useMarketplaceSession } from "./marketplace";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import styles from "./Marketplace.module.css";

export default function MarketplacePage({ kind }: { kind: MarketplaceKind }) {
  return (
    <MarketplaceScope>
      {(marketplaceSpaceId) => (
        <Catalogue key={`${marketplaceSpaceId}:${kind}`} marketplaceSpaceId={marketplaceSpaceId} kind={kind} />
      )}
    </MarketplaceScope>
  );
}

function Catalogue({ marketplaceSpaceId, kind }: { marketplaceSpaceId: string; kind: MarketplaceKind }) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const active = useMarketplaceSession();
  const [recoverySource, setRecoverySource] = useState<SubmitProposalRequest>();
  const recoveries = savedProposalRequests(marketplaceSpaceId, kind);
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState(params.has("proposal") ? "proposals" : "publications");
  const [state, setState] = useState<ProposalState | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const proposals = view === "proposals";
  const entriesQuery = useMarketplaceEntriesQuery(sessionQueryArgs({ marketplaceSpaceId, kind }), {
    ...crossSessionRefreshOptions(proposals),
    refetchOnMountOrArgChange: true,
  });
  const proposalsQuery = useMarketplaceProposalsQuery(
    sessionQueryArgs({ marketplaceSpaceId, kind, state: state || undefined }),
    { ...crossSessionRefreshOptions(!proposals), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(entriesQuery.refetch, proposals);
  useRefetchOnWindowFocus(proposalsQuery.refetch, !proposals);
  const query = proposals ? proposalsQuery : entriesQuery;
  const rows = query.isError
    ? []
    : (query.currentData?.items ?? []).filter((item) =>
        [item.display_name, item.description, item.origin_name, item.entry_id].some((text) =>
          text.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
        ),
      );
  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / 20) - 1));
  const open = (id: string) => setParams({ catalogue: marketplaceSpaceId, [proposals ? "proposal" : "entry"]: id });
  const close = () => setParams({ catalogue: marketplaceSpaceId });
  return (
    <div className={styles.page}>
      <PageHeader title={t(`rework.localMarketplace.kinds.${kind}`)} />
      <p className={styles.identity}>{t(`rework.localMarketplace.${proposals ? "proposalsHint" : "catalogueHint"}`)}</p>
      <div className={styles.toolbar}>
        <Select
          size="small"
          label={t("rework.localMarketplace.view")}
          value={view}
          onChange={(value) => {
            setView(value);
            setPage(0);
            close();
          }}
          options={["publications", "proposals"].map((value) => ({
            key: value,
            value,
            label: t(`rework.localMarketplace.${value}`),
          }))}
        />
        {proposals && (
          <Select
            size="small"
            label={t("rework.localMarketplace.state")}
            value={state}
            onChange={(value) => {
              setState(value);
              setPage(0);
            }}
            options={(["", "pending", "approved", "rejected", "cancelled"] as const).map((value) => ({
              key: value || "all",
              value,
              label: t(value ? `rework.localMarketplace.states.${value}` : "rework.localMarketplace.all"),
            }))}
          />
        )}
        <SearchInput
          size="small"
          value={search}
          onChange={(value) => {
            setSearch(value);
            setPage(0);
          }}
          placeholder={t("rework.localMarketplace.search")}
          ariaLabel={t("rework.localMarketplace.search")}
          clearAriaLabel={t("rework.localMarketplace.clearSearch")}
        />
        <Button
          size="small"
          color="primary"
          variant="outlined"
          icon={{ category: "outlined", type: "refresh" }}
          disabled={query.isFetching}
          onClick={() => {
            if (active())
              dispatch(
                enhancedControlPlaneApi.util.invalidateTags([{ type: "MarketplaceContent", id: marketplaceSpaceId }]),
              );
          }}
        >
          {t("rework.localMarketplace.refresh")}
        </Button>
      </div>
      {recoveries.length > 0 && (
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
        <p role="alert">{marketplaceError(query.error, t)}</p>
      ) : query.isFetching || !query.currentData ? (
        <p role="status">{t("common.loading")}</p>
      ) : !rows.length ? (
        <PageEmptyState
          icon="storefront"
          message={t(
            search || state
              ? "rework.localMarketplace.empty"
              : `rework.localMarketplace.${proposals ? "noProposals" : "noPublications"}`,
          )}
          description={t("rework.localMarketplace.catalogueHint")}
        />
      ) : (
        <>
          <div className={styles.grid}>
            {rows.slice(currentPage * 20, (currentPage + 1) * 20).map((item) => (
              <ResourceCard key={proposals ? item.proposal_id : item.entry_id}>
                <div className={cardStyles.header}>
                  <span className={cardStyles.category} title={marketplaceName(item.origin_name, t)}>
                    {marketplaceName(item.origin_name, t)}
                  </span>
                  <h2 className={cardStyles.name} title={item.display_name}>
                    {item.display_name}
                  </h2>
                </div>
                {item.description && item.description !== item.display_name && (
                  <p className={cardStyles.description} title={item.description}>
                    {item.description}
                  </p>
                )}
                <div className={styles.actions}>
                  <Chip
                    label={t(
                      "state" in item
                        ? `rework.localMarketplace.states.${item.state}`
                        : "rework.localMarketplace.published",
                    )}
                  />
                  <span className={styles.identity}>
                    {formatDateTime("submitted_at" in item ? item.submitted_at : item.published_at)}
                  </span>
                </div>
                {"state" in item && item.state === "approved" && (
                  <span className={styles.identity}>
                    {t(
                      item.published_proposal_id === item.proposal_id
                        ? "rework.localMarketplace.currentPublication"
                        : "rework.localMarketplace.previousProposal",
                    )}
                  </span>
                )}
                <div className={styles.actions}>
                  <Button
                    size="small"
                    color="primary"
                    variant={proposals ? "filled" : "outlined"}
                    onClick={() => open(proposals ? item.proposal_id : item.entry_id)}
                  >
                    {t("rework.localMarketplace.inspect")}
                  </Button>
                  {!proposals && (
                    <Button
                      size="small"
                      color="primary"
                      variant="filled"
                      icon={{ category: "outlined", type: "download" }}
                      onClick={() =>
                        setParams({ catalogue: marketplaceSpaceId, entry: item.entry_id, install: "true" })
                      }
                    >
                      {t("rework.localMarketplace.install")}
                    </Button>
                  )}
                </div>
              </ResourceCard>
            ))}
          </div>
          {rows.length > 20 && (
            <TablePagination
              totalItems={rows.length}
              currentPage={currentPage}
              pageCount={Math.ceil(rows.length / 20)}
              rowsPerPage={20}
              rowsPerPageOptions={[]}
              onFirst={() => setPage(0)}
              onPrev={() => setPage(currentPage - 1)}
              onNext={() => setPage(currentPage + 1)}
              onLast={() => setPage(Math.ceil(rows.length / 20) - 1)}
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
      {(params.get("entry") || params.get("proposal")) && (
        <MarketplaceDetailDialog
          key={params.get("proposal") ?? params.get("entry")}
          marketplaceSpaceId={marketplaceSpaceId}
          entryId={params.get("entry") ?? undefined}
          proposalId={params.get("proposal") ?? undefined}
          installFirst={params.has("install")}
          onClose={close}
        />
      )}
    </div>
  );
}
