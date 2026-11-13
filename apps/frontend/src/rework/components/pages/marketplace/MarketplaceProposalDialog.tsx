import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "@rework/utils/formatDateTime";
import Button from "@shared/atoms/Button/Button";
import Select from "@shared/molecules/Select/Select";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import {
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
import { marketplaceError, marketplaceName, useMarketplaceAttempt } from "./marketplace";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import styles from "./Marketplace.module.css";

type ProposalProps = {
  source: Omit<SubmitProposalRequest, "entry_id">;
  onClose: () => void;
  recoveryOnly?: boolean;
  sourceName?: string;
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

function ProposalContext({ source, onClose, recoveryOnly = false, sourceName }: ProposalProps) {
  const { t } = useTranslation();
  const attempt = useMarketplaceAttempt<Omit<SubmitMarketplaceProposalApiArg, "Idempotency-Key">, MarketplaceProposal>([
    "proposal",
    source.source_space_id,
    source.kind,
    source.source_resource_id,
  ]);
  const spaces = useMarketplaceProposalSpacesQuery(sessionQueryArgs({}), { refetchOnMountOrArgChange: true });
  const { marketplaces: catalogues, organizationId } = useWorkingOrganization();
  const permitted = spaces.currentData?.items.find(
    (space) => space.id === source.source_space_id && space.resource_kinds.includes(source.kind),
  );
  const choices =
    catalogues.currentData?.items.filter(
      (item) => item.space_id === organizationId && permitted?.marketplace_space_ids.includes(item.space_id),
    ) ?? [];
  const selected = attempt.args?.marketplaceSpaceId ?? choices[0]?.space_id;
  return (
    <Dialog
      open
      onCancel={attempt.busy ? () => {} : onClose}
      title={sourceName ?? attempt.context?.name ?? t("rework.localMarketplace.propose")}
      hideConfirm
      confirmLabel=""
      onConfirm={() => {}}
      cancelLabel={t("rework.localMarketplace.close")}
      dense
    >
      <div className={styles.content}>
        <p>{t("rework.localMarketplace.snapshotExplanation")}</p>
        {!attempt.started && recoveryOnly ? null : !attempt.started && (spaces.isError || catalogues.isError) ? (
          <p role="alert">{t("rework.localMarketplace.failed")}</p>
        ) : !attempt.started && (!spaces.currentData || !catalogues.currentData) ? (
          <p role="status">{t("common.loading")}</p>
        ) : !selected || (!attempt.started && !choices.some((item) => item.space_id === selected)) ? (
          <p>{t("rework.localMarketplace.noSource")}</p>
        ) : (
          <>
            <ProposalForm
              key={selected}
              sourceName={sourceName}
              catalogueName={catalogues.currentData?.items.find((item) => item.space_id === selected)?.name}
              source={source}
              marketplaceSpaceId={selected}
              attempt={attempt}
              checkingAccess={spaces.isFetching || catalogues.isFetching}
              canStart={
                !recoveryOnly &&
                !spaces.isError &&
                !catalogues.isError &&
                !spaces.isFetching &&
                !catalogues.isFetching &&
                choices.some((item) => item.space_id === selected)
              }
            />
          </>
        )}
      </div>
    </Dialog>
  );
}

function ProposalForm({
  source,
  marketplaceSpaceId,
  attempt,
  checkingAccess,
  canStart,
  sourceName,
  catalogueName,
}: {
  source: Omit<SubmitProposalRequest, "entry_id">;
  marketplaceSpaceId: string;
  checkingAccess: boolean;
  canStart: boolean;
  sourceName?: string;
  catalogueName?: string;
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
    ...[...(proposals.currentData?.items ?? [])]
      .sort((a, b) => a.submitted_at.localeCompare(b.submitted_at))
      .map((item) => [item.entry_id, item] as const),
    ...(entries.currentData?.items ?? []).map((item) => [item.entry_id, item] as const),
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
              label: t("rework.localMarketplace.updateEntry", {
                name: item.display_name,
                origin: marketplaceName(item.origin_name, t),
              }),
            })),
          ]}
          onChange={setEntryId}
        />
      )}
      <p>{t(entryId ? "rework.localMarketplace.replaceExplanation" : "rework.localMarketplace.newExplanation")}</p>
      {(entries.isError || proposals.isError) && <p role="alert">{t("rework.localMarketplace.targetsError")}</p>}
      {attempt.context && (
        <p className={styles.identity}>
          {attempt.context.name} · {attempt.context.destination} · {formatDateTime(attempt.context.startedAt)}
        </p>
      )}
      {attempt.started && !attempt.busy && !attempt.canReset && (
        <p role="status">{t("rework.localMarketplace.resumeAttempt")}</p>
      )}
      {attempt.error != null && <p role="alert">{marketplaceError(attempt.error, t, undefined, true)}</p>}
      {attempt.result ? (
        <>
          <p role="status">{t("rework.localMarketplace.submitted")}</p>
          <Link
            to={`/marketplace/${source.kind}s?catalogue=${marketplaceSpaceId}&proposal=${attempt.result.proposal_id}`}
          >
            {t("rework.localMarketplace.followProposal")}
          </Link>
        </>
      ) : !attempt.canReset ? (
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
              {
                name: sourceName ?? t(`rework.localMarketplace.kinds.${source.kind}`),
                destination: catalogueName ?? t("rework.localMarketplace.catalogue"),
              },
            )
          }
        >
          {t(attempt.started ? "rework.localMarketplace.retry" : "rework.localMarketplace.submit")}
        </Button>
      ) : null}
      {canStart && attempt.canReset && normalizeApiError(attempt.error).code !== "source_changed" && (
        <Button size="small" color="on-surface" variant="text" onClick={attempt.reset}>
          {t(attempt.result ? "rework.localMarketplace.newOperation" : "rework.localMarketplace.correctRequest")}
        </Button>
      )}
    </div>
  );
}
