// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Select from "@shared/molecules/Select/Select";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal";
import {
  useMarketplacesQuery,
  useMarketplaceProposalSpacesQuery,
  useMarketplaceEntriesQuery,
  useMarketplaceProposalsQuery,
  useSubmitMarketplaceProposalMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  SubmitProposalRequest,
  SubmitMarketplaceProposalApiArg,
  MarketplaceProposal,
  ProposalSummary,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { marketplaceError, useMarketplaceAttempt } from "./marketplace";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import styles from "./Marketplace.module.css";

type ProposalProps = {
  source: Omit<SubmitProposalRequest, "entry_id">;
  onClose: () => void;
  recoveryOnly?: boolean;
};

export default function MarketplaceProposalDialog(props: ProposalProps) {
  return (
    <ProposalContext
      key={JSON.stringify([
        KeyCloakService.GetSessionIdentity(),
        props.source.source_space_id,
        props.source.kind,
        props.source.source_resource_id,
      ])}
      {...props}
    />
  );
}

function ProposalContext({ source, onClose, recoveryOnly = false }: ProposalProps) {
  const { t } = useTranslation();
  const attempt = useMarketplaceAttempt<Omit<SubmitMarketplaceProposalApiArg, "Idempotency-Key">, MarketplaceProposal>([
    "proposal",
    source.source_space_id,
    source.kind,
    source.source_resource_id,
  ]);
  const spaces = useMarketplaceProposalSpacesQuery(sessionQueryArgs({}), { refetchOnMountOrArgChange: true });
  const catalogues = useMarketplacesQuery(sessionQueryArgs({}), { refetchOnMountOrArgChange: true });
  const [catalogue, setCatalogue] = useState("");
  const permitted = spaces.currentData?.items.find(
    (space) => space.id === source.source_space_id && space.resource_kinds.includes(source.kind),
  );
  const choices =
    catalogues.currentData?.items.filter((item) => permitted?.marketplace_space_ids.includes(item.space_id)) ?? [];
  const selected =
    attempt.args?.marketplaceSpaceId ??
    choices.find((item) => item.space_id === catalogue)?.space_id ??
    choices[0]?.space_id;
  return (
    <FullPageModal isOpen onClose={attempt.busy ? () => {} : onClose} id="marketplace-proposal" background="scrim">
      <div className={styles.dialog}>
        <h2 id="marketplace-proposal-title">{t("rework.localMarketplace.propose")}</h2>
        <p>{t("rework.localMarketplace.snapshotExplanation")}</p>
        {attempt.started && selected ? (
          <ProposalForm
            source={source}
            marketplaceSpaceId={selected}
            attempt={attempt}
            checkingAccess={false}
            canStart={
              !recoveryOnly &&
              !spaces.isError &&
              !catalogues.isError &&
              !spaces.isFetching &&
              !catalogues.isFetching &&
              choices.some((item) => item.space_id === selected)
            }
          />
        ) : recoveryOnly ? null : spaces.isError || catalogues.isError ? (
          <p role="alert">{t("rework.localMarketplace.failed")}</p>
        ) : !spaces.currentData || !catalogues.currentData ? (
          <p role="status">{t("common.loading")}</p>
        ) : !selected || !choices.some((item) => item.space_id === selected) ? (
          <p>{t("rework.localMarketplace.noSource")}</p>
        ) : (
          <>
            <Select
              size="small"
              label={t("rework.localMarketplace.catalogue")}
              value={selected}
              disabled={attempt.started}
              options={choices.map((item) => ({
                key: item.space_id,
                value: item.space_id,
                label: `${item.name} (${item.space_id})`,
              }))}
              onChange={setCatalogue}
            />
            <ProposalForm
              key={selected}
              source={source}
              marketplaceSpaceId={selected}
              attempt={attempt}
              checkingAccess={spaces.isFetching || catalogues.isFetching}
              canStart
            />
          </>
        )}
        <Button size="small" color="on-surface" variant="text" disabled={attempt.busy} onClick={onClose}>
          {t("rework.localMarketplace.close")}
        </Button>
      </div>
    </FullPageModal>
  );
}

function ProposalForm({
  source,
  marketplaceSpaceId,
  attempt,
  checkingAccess,
  canStart,
}: {
  source: Omit<SubmitProposalRequest, "entry_id">;
  marketplaceSpaceId: string;
  checkingAccess: boolean;
  canStart: boolean;
  attempt: ReturnType<
    typeof useMarketplaceAttempt<Omit<SubmitMarketplaceProposalApiArg, "Idempotency-Key">, MarketplaceProposal>
  >;
}) {
  const { t } = useTranslation();
  const [entryId, setEntryId] = useState(attempt.args?.submitProposalRequest.entry_id ?? "");
  const entries = useMarketplaceEntriesQuery(sessionQueryArgs({ marketplaceSpaceId, kind: source.kind }), {
    skip: attempt.started,
    refetchOnMountOrArgChange: true,
  });
  const proposals = useMarketplaceProposalsQuery(sessionQueryArgs({ marketplaceSpaceId, kind: source.kind }), {
    skip: attempt.started,
    refetchOnMountOrArgChange: true,
  });
  const [submit] = useSubmitMarketplaceProposalMutation();
  const existing = new Map<string, Pick<ProposalSummary, "entry_id" | "display_name" | "origin_name">>([
    ...(entries.currentData?.items ?? []).map((item) => [item.entry_id, item] as const),
    ...(proposals.currentData?.items ?? []).map((item) => [item.entry_id, item] as const),
  ]);
  return (
    <div className={styles.content}>
      {!attempt.started && (
        <Select
          size="small"
          label={t("rework.localMarketplace.proposalTarget")}
          value={entryId}
          disabled={attempt.started}
          options={[
            { key: "new", value: "", label: t("rework.localMarketplace.newEntry") },
            ...[...existing.values()].map((item) => ({
              key: item.entry_id,
              value: item.entry_id,
              label: `${item.display_name} - ${item.origin_name} (${item.entry_id})`,
            })),
          ]}
          onChange={setEntryId}
        />
      )}
      <p>{t(entryId ? "rework.localMarketplace.replaceExplanation" : "rework.localMarketplace.newExplanation")}</p>
      {(entries.isError || proposals.isError) && <p role="alert">{t("rework.localMarketplace.targetsError")}</p>}
      {attempt.started && !attempt.busy && !attempt.canReset && (
        <p role="status">{t("rework.localMarketplace.resumeAttempt")}</p>
      )}
      {attempt.error != null && <p role="alert">{marketplaceError(attempt.error, t)}</p>}
      {attempt.result ? (
        <>
          <p role="status">{t("rework.localMarketplace.submitted")}</p>
          <Link
            to={`/marketplace/${source.kind}s?catalogue=${marketplaceSpaceId}&proposal=${attempt.result.proposal_id}`}
          >
            {t("rework.localMarketplace.followProposal")}
          </Link>
        </>
      ) : (
        <Button
          size="small"
          color="primary"
          variant="filled"
          disabled={
            attempt.busy ||
            (!attempt.started &&
              (checkingAccess || entries.isFetching || proposals.isFetching || entries.isError || proposals.isError))
          }
          onClick={() =>
            void attempt.run(
              attempt.args ?? {
                marketplaceSpaceId,
                submitProposalRequest: { ...source, entry_id: entryId || undefined },
              },
              (args, key) => submit({ ...args, "Idempotency-Key": key }).unwrap(),
            )
          }
        >
          {t(attempt.started ? "rework.localMarketplace.retry" : "rework.localMarketplace.submit")}
        </Button>
      )}
      {canStart && attempt.canReset && (
        <Button size="small" color="on-surface" variant="text" onClick={attempt.reset}>
          {t("rework.localMarketplace.newOperation")}
        </Button>
      )}
    </div>
  );
}
