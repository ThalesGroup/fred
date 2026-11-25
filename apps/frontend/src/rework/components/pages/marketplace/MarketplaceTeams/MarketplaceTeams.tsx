// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import TeamCard from "@shared/organisms/TeamCard/TeamCard";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import TablePagination from "@shared/molecules/TablePagination/TablePagination";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import Button from "@shared/atoms/Button/Button";
import { useOrganizationTeamsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { sessionQueryArgs } from "../../../../../slices/controlPlane/controlPlaneApi";
import styles from "./MarketplaceTeams.module.scss";

export default function MarketplaceTeams() {
  const { t } = useTranslation();
  const context = useWorkingOrganization();
  if (context.loading)
    return (
      <span className={styles.line} role="status">
        {t("common.loading")}
      </span>
    );
  if (context.error || !context.organizationId) return <ServiceNotice title={t("rework.manager.unavailable")} />;
  return <Directory key={context.organizationId} organizationId={context.organizationId} />;
}

function Directory({ organizationId }: { organizationId: string }) {
  const { t } = useTranslation();
  const { memberships } = useWorkingOrganization();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const query = useOrganizationTeamsQuery(sessionQueryArgs({ organizationId, search, page }), {
    ...crossSessionRefreshOptions(false),
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(query.refetch, false, true);
  const total = query.currentData?.total;
  const pageCount = Math.max(1, Math.ceil((total ?? 0) / 20));
  useEffect(() => {
    if (total !== undefined && page >= pageCount) setPage(pageCount - 1);
  }, [total, page, pageCount]);
  // Never render a previous organization/search/page or failed authorization response.
  const teams = !query.isError && !query.isFetching ? query.currentData?.items : undefined;
  return (
    <div className={styles.marketplaceTeamsContainer} data-shell-scroll="none">
      <div className={styles.marketplaceTeamsHeader}>
        <h1 className={styles.marketplaceTeamsTitle}>{t("rework.marketplace.teams.title")}</h1>
        <div className={styles.marketplaceTeamsSearch}>
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value);
              setPage(0);
            }}
            placeholder={t("rework.marketplace.teams.search.placeholder")}
            ariaLabel={t("rework.marketplace.teams.search.ariaLabel")}
            clearAriaLabel={t("rework.marketplace.teams.search.clearAriaLabel")}
            size="small"
          />
        </div>
        <Button
          size="small"
          color="primary"
          variant="outlined"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          {t("rework.localMarketplace.refresh")}
        </Button>
      </div>
      <span className={styles.line}>{t("rework.teamDiscovery.catalogueHint")}</span>
      {query.isError ? (
        <span className={styles.line} role="alert">
          {t("rework.manager.unavailable")}
        </span>
      ) : !teams ? (
        <span className={styles.line} role="status">
          {t("common.loading")}
        </span>
      ) : !teams.length ? (
        <PageEmptyState
          icon="groups"
          message={t(search ? "rework.marketplace.teams.emptySearch.title" : "rework.marketplace.teams.empty.title")}
        />
      ) : (
        <div className={styles.marketplaceTeamsList}>
          {teams.map((team) => (
            <TeamCard
              key={team.id}
              team={team}
              onJoined={() => {
                // RTK invalidation can wait behind unrelated pending queries.
                void query.refetch();
                void memberships.refetch();
              }}
            />
          ))}
        </div>
      )}
      {teams && total !== undefined && total > 20 && (
        <TablePagination
          totalItems={total}
          currentPage={page}
          pageCount={pageCount}
          rowsPerPage={20}
          rowsPerPageOptions={[]}
          onFirst={() => setPage(0)}
          onPrev={() => setPage(page - 1)}
          onNext={() => setPage(page + 1)}
          onLast={() => setPage(pageCount - 1)}
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
    </div>
  );
}
