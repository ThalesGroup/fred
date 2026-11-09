// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useDispatch } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
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
import { marketplaceError, savedProposalRequests, useMarketplaceSession } from "./marketplace";
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
          variant="text"
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
          {recoveries.map(({ submitProposalRequest: source }) => (
            <div key={JSON.stringify([source.source_space_id, source.source_resource_id])}>
              <span className={styles.identity}>
                {source.source_space_id} · {source.source_resource_id}
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
        <p>{t("rework.localMarketplace.empty")}</p>
      ) : (
        <>
          <div className={styles.grid}>
            {rows.slice(currentPage * 20, (currentPage + 1) * 20).map((item) => (
              <article className={styles.card} key={proposals ? item.proposal_id : item.entry_id}>
                <h2>{item.display_name}</h2>
                <p>{item.description}</p>
                <p>{item.origin_name}</p>
                <p className={styles.identity}>
                  {t("rework.localMarketplace.entryIdentity")} {item.entry_id}
                </p>
                {"state" in item && <Chip label={t(`rework.localMarketplace.states.${item.state}`)} />}
                <Button
                  size="small"
                  color="primary"
                  variant="outlined"
                  onClick={() => open(proposals ? item.proposal_id : item.entry_id)}
                >
                  {t("rework.localMarketplace.inspect")}
                </Button>
              </article>
            ))}
          </div>
          <div className={styles.actions}>
            <Button
              size="small"
              color="primary"
              variant="text"
              disabled={currentPage === 0}
              onClick={() => setPage(currentPage - 1)}
            >
              {t("rework.localMarketplace.previous")}
            </Button>
            <span>
              {t("rework.localMarketplace.page", { page: currentPage + 1, count: Math.ceil(rows.length / 20) })}
            </span>
            <Button
              size="small"
              color="primary"
              variant="text"
              disabled={(currentPage + 1) * 20 >= rows.length}
              onClick={() => setPage(currentPage + 1)}
            >
              {t("rework.localMarketplace.next")}
            </Button>
          </div>
        </>
      )}
      {(params.get("entry") || params.get("proposal")) && (
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
