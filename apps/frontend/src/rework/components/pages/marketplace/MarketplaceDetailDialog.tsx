// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import { useStore } from "react-redux";
import type { AppState } from "../../../../common/store";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import TextArea from "@shared/atoms/TextArea/TextArea";
import Select from "@shared/molecules/Select/Select";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  enhancedControlPlaneApi,
  useMarketplaceEntryQuery,
  useMarketplaceProposalQuery,
  useDecideMarketplaceProposalMutation,
  useCancelMarketplaceProposalMutation,
  useWithdrawMarketplaceEntryMutation,
  useMarketplaceProposalSpacesQuery,
  useInstallMarketplaceEntryMutation,
  useMarketplaceInstallationQuery,
  useListPromptCategoriesQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  MarketplaceEntryDetail,
  InstallMarketplaceEntryApiArg,
  InstallationReceipt,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import MarketplacePackageView from "./MarketplacePackageView";
import { installationPath, marketplaceError, useMarketplaceAttempt, useMarketplaceSession } from "./marketplace";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import styles from "./Marketplace.module.css";

import { KeyCloakService } from "../../../../security/KeycloakService";

type InstallationRequest = Omit<InstallMarketplaceEntryApiArg, "Idempotency-Key">;

type DetailProps = {
  marketplaceSpaceId: string;
  entryId?: string;
  proposalId?: string;
  onClose: () => void;
};

export default function MarketplaceDetailDialog(props: DetailProps) {
  // RTK serializes by actor, but an existing hook subscription must also be renewed.
  return (
    <ReviewContext
      key={JSON.stringify([
        KeyCloakService.GetSessionIdentity(),
        props.marketplaceSpaceId,
        props.entryId,
        props.proposalId,
      ])}
      {...props}
    />
  );
}

function ReviewContext({ marketplaceSpaceId, entryId, proposalId, onClose }: DetailProps) {
  const active = useMarketplaceSession();
  const store = useStore<AppState>();
  const { t } = useTranslation();
  const attempt = useMarketplaceAttempt<InstallationRequest, InstallationReceipt>([
    "installation",
    marketplaceSpaceId,
    entryId ?? "",
  ]);
  const [install] = useInstallMarketplaceEntryMutation();
  const receipt = useMarketplaceInstallationQuery(
    sessionQueryArgs({
      spaceId: attempt.result?.space_id ?? "",
      installationId: attempt.result?.installation_id ?? "",
    }),
    { skip: !attempt.result, refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(receipt.refetch, !attempt.result);
  const currentReceipt = !receipt.isError && !receipt.isFetching ? receipt.currentData : undefined;
  const entryQuery = useMarketplaceEntryQuery(sessionQueryArgs({ marketplaceSpaceId, entryId: entryId ?? "" }), {
    ...crossSessionRefreshOptions(!entryId),
    refetchOnMountOrArgChange: true,
  });
  const proposalQuery = useMarketplaceProposalQuery(
    sessionQueryArgs({ marketplaceSpaceId, proposalId: proposalId ?? "" }),
    { ...crossSessionRefreshOptions(!proposalId), refetchOnMountOrArgChange: true },
  );
  const query = proposalId ? proposalQuery : entryQuery;
  useRefetchOnWindowFocus(entryQuery.refetch, !entryId);
  useRefetchOnWindowFocus(proposalQuery.refetch, !proposalId);
  // RTK retains currentData after a refusal; a subsequent pending read must not
  // resurrect that package before it has succeeded.
  const showCachedDetail = useRef(false);
  if (!query.isFetching) showCachedDetail.current = query.isSuccess;
  const detail = showCachedDetail.current ? query.currentData : undefined;
  const verified = () => {
    if (!active() || !detail) return false;
    // Read the store at command time too: a refresh can start before React commits.
    const current = proposalId
      ? enhancedControlPlaneApi.endpoints.marketplaceProposal.select({ marketplaceSpaceId, proposalId })(
          store.getState(),
        )
      : enhancedControlPlaneApi.endpoints.marketplaceEntry.select({ marketplaceSpaceId, entryId: entryId! })(
          store.getState(),
        );
    return current.isSuccess && current.requestId === query.requestId && current.data === detail;
  };
  const installAttempt = async (args: InstallationRequest) => {
    if (!active() || (!attempt.started && !verified())) return;
    await attempt.run(args, (request, key) => install({ ...request, "Idempotency-Key": key }).unwrap());
  };
  const [decide] = useDecideMarketplaceProposalMutation();
  const [cancel] = useCancelMarketplaceProposalMutation();
  const [withdraw] = useWithdrawMarketplaceEntryMutation();
  const [confirmWithdrawal, setConfirmWithdrawal] = useState<(() => void) | undefined>();
  const running = useRef(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>();
  const [reviewAgain, setReviewAgain] = useState(false);
  const mutate = async (action: () => Promise<unknown>, close = false) => {
    if (!verified() || running.current || reviewAgain) return;
    running.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await action();
      if (active() && close) onClose();
    } catch (failure) {
      if (!active()) return;
      setError(failure);
      if (normalizeApiError(failure).status === 409) setReviewAgain(true);
      void query.refetch();
    } finally {
      if (active()) {
        running.current = false;
        setBusy(false);
      }
    }
  };
  const proposal = proposalId && detail && "actions" in detail ? detail : undefined;
  const entry = entryId && detail && "can_withdraw" in detail ? detail : undefined;
  return (
    <FullPageModal
      isOpen
      onClose={busy || attempt.busy ? () => {} : onClose}
      id="marketplace-detail"
      background="scrim"
    >
      <div className={styles.dialog}>
        <h2 id="marketplace-detail-title">{detail?.display_name ?? t("rework.localMarketplace.inspect")}</h2>
        <Button size="small" color="on-surface" variant="text" disabled={busy || attempt.busy} onClick={onClose}>
          {t("rework.localMarketplace.close")}
        </Button>
        {query.isFetching && detail && <p role="status">{t("common.loading")}</p>}
        {error != null && <p role="alert">{marketplaceError(error, t)}</p>}
        {query.isError ? (
          <p role="alert">{marketplaceError(query.error, t)}</p>
        ) : !detail ? (
          <p role="status">{t("common.loading")}</p>
        ) : (
          <>
            <p>{detail.description}</p>
            <p className={styles.identity}>
              {detail.origin_name} · {t("rework.localMarketplace.entryIdentity")} {detail.entry_id} ·{" "}
              {t("rework.localMarketplace.proposalIdentity")} {detail.proposal_id}
            </p>
            <MarketplacePackageView value={detail.package} />
            {proposal && (
              <>
                <p>
                  {t(`rework.localMarketplace.states.${proposal.state}`)} · {proposal.submitted_by} ·{" "}
                  {proposal.submitted_at}
                </p>
                {proposal.decided_at && (
                  <p>
                    {proposal.decided_by} · {proposal.decided_at}
                  </p>
                )}
                {proposal.decision_reason && <p className={styles.text}>{proposal.decision_reason}</p>}
                <p>{t("rework.localMarketplace.reviewVersion", { version: proposal.publication_version })}</p>
                <p className={styles.identity}>
                  {t("rework.localMarketplace.currentPublication")}:{" "}
                  {proposal.published_proposal_id ?? t("rework.localMarketplace.none")}
                </p>
                {proposal.actions.can_decide && (
                  <>
                    <TextArea
                      label={t("rework.localMarketplace.reason")}
                      value={reason}
                      maxLength={2000}
                      disabled={busy || query.isFetching}
                      onChange={(event) => setReason(event.target.value)}
                    />
                    <div className={styles.actions}>
                      {[true, false].map((approve) => (
                        <Button
                          key={String(approve)}
                          size="small"
                          color={approve ? "primary" : "error"}
                          variant="outlined"
                          disabled={busy || reviewAgain || query.isFetching}
                          onClick={() =>
                            void mutate(() =>
                              decide({
                                marketplaceSpaceId,
                                proposalId: proposal.proposal_id,
                                proposalDecisionRequest: {
                                  approve,
                                  reason: reason || null,
                                  expected_publication_version: proposal.publication_version,
                                },
                              }).unwrap(),
                            )
                          }
                        >
                          {t(approve ? "rework.localMarketplace.approve" : "rework.localMarketplace.reject")}
                        </Button>
                      ))}
                    </div>
                  </>
                )}
                {proposal.actions.can_cancel && (
                  <Button
                    size="small"
                    color="error"
                    variant="text"
                    disabled={busy || reviewAgain || query.isFetching}
                    onClick={() =>
                      void mutate(() => cancel({ marketplaceSpaceId, proposalId: proposal.proposal_id }).unwrap())
                    }
                  >
                    {t("rework.localMarketplace.cancelProposal")}
                  </Button>
                )}
              </>
            )}
            {entry && entry.can_withdraw && (
              <Button
                size="small"
                color="error"
                variant="text"
                disabled={busy || reviewAgain || query.isFetching}
                onClick={() =>
                  setConfirmWithdrawal(
                    () => () =>
                      void mutate(
                        () =>
                          withdraw({
                            marketplaceSpaceId,
                            entryId: entry.entry_id,
                            withdrawRequest: { expected_publication_version: entry.publication_version },
                          }).unwrap(),
                        true,
                      ),
                  )
                }
              >
                {t("rework.localMarketplace.withdraw")}
              </Button>
            )}
          </>
        )}
        {entryId && (entry || attempt.started || attempt.error != null) && (
          <section className={styles.content}>
            <h3>{t("rework.localMarketplace.install")}</h3>
            {!attempt.started && entry && (
              <InstallForm
                key={entry.proposal_id}
                entry={entry}
                checking={query.isFetching}
                onInstall={installAttempt}
              />
            )}
            {attempt.started && !attempt.busy && !attempt.canReset && (
              <p role="status">{t("rework.localMarketplace.resumeAttempt")}</p>
            )}
            {attempt.error != null && <p role="alert">{marketplaceError(attempt.error, t)}</p>}
            {attempt.result ? (
              <>
                <p role="status">{t("rework.localMarketplace.installed")}</p>
                {receipt.isError ? (
                  <p role="alert">{marketplaceError(receipt.error, t)}</p>
                ) : !currentReceipt ? (
                  <p role="status">{t("common.loading")}</p>
                ) : currentReceipt.resource_exists ? (
                  <Link to={installationPath(currentReceipt)}>{t("rework.localMarketplace.openResource")}</Link>
                ) : (
                  <p>{t("rework.localMarketplace.resourceDeleted")}</p>
                )}
                <Button size="small" color="on-surface" variant="text" onClick={() => void receipt.refetch()}>
                  {t("rework.localMarketplace.refresh")}
                </Button>
              </>
            ) : attempt.args ? (
              <Button
                size="small"
                color="primary"
                variant="filled"
                disabled={attempt.busy}
                onClick={() => void installAttempt(attempt.args!)}
              >
                {t("rework.localMarketplace.retry")}
              </Button>
            ) : null}
            {entry && attempt.canReset && (
              <Button
                size="small"
                color="on-surface"
                variant="text"
                disabled={query.isFetching}
                onClick={() => {
                  if (verified()) attempt.reset();
                }}
              >
                {t("rework.localMarketplace.newOperation")}
              </Button>
            )}
          </section>
        )}
        {(reviewAgain ||
          query.isError ||
          (attempt.error != null && normalizeApiError(attempt.error).code === "publication_changed")) && (
          <Button
            size="small"
            color="primary"
            variant="outlined"
            disabled={busy || attempt.busy || query.isFetching}
            onClick={async () => {
              if (!active()) return;
              const refreshed = await query.refetch();
              if (active() && !refreshed.error) {
                if (normalizeApiError(attempt.error).code === "publication_changed") attempt.reset();
                setReviewAgain(false);
                setError(undefined);
              }
            }}
          >
            {t("rework.localMarketplace.reviewAgainAction")}
          </Button>
        )}
      </div>
      <ConfirmationDialog
        open={!!confirmWithdrawal}
        title={t("rework.localMarketplace.withdraw")}
        message={t("rework.localMarketplace.withdrawExplanation")}
        criticalAction
        confirmDisabled={query.isFetching || busy}
        confirmLabel={t("confirmationDialog.defaultConfirmButtonLabel")}
        cancelLabel={t("confirmationDialog.defaultCancelButtonLabel")}
        onCancel={() => setConfirmWithdrawal(undefined)}
        onConfirm={() => {
          confirmWithdrawal?.();
          setConfirmWithdrawal(undefined);
        }}
      />
    </FullPageModal>
  );
}

function InstallForm({
  entry,
  onInstall,
  checking,
}: {
  entry: MarketplaceEntryDetail;
  checking: boolean;
  onInstall: (args: InstallationRequest) => Promise<void>;
}) {
  const { t } = useTranslation();
  const spaces = useMarketplaceProposalSpacesQuery(sessionQueryArgs({}), { refetchOnMountOrArgChange: true });
  const [spaceId, setSpaceId] = useState("");
  const [logicalName, setLogicalName] = useState(
    entry.package.kind === "skill" ? "" : entry.package.content.logical_name,
  );
  const [displayName, setDisplayName] = useState(entry.display_name);
  const [category, setCategory] = useState("");
  const destinations = spaces.isError
    ? []
    : (spaces.currentData?.items.filter(
        (space) =>
          space.resource_kinds.includes(entry.kind) && space.marketplace_space_ids.includes(entry.marketplace_space_id),
      ) ?? []);
  const destination = destinations.find((space) => space.id === spaceId);
  const categories = useListPromptCategoriesQuery(sessionQueryArgs({ spaceId }), {
    skip: !destination || entry.kind !== "prompt",
    refetchOnMountOrArgChange: true,
  });
  return (
    <>
      <p>{t("rework.localMarketplace.installExplanation")}</p>
      {spaces.isError && <p role="alert">{marketplaceError(spaces.error, t)}</p>}
      {!spaces.isFetching && !destinations.length && <p>{t("rework.localMarketplace.noDestination")}</p>}
      <Select
        size="small"
        label={t("rework.localMarketplace.destination")}
        value={spaceId}
        disabled={spaces.isFetching}
        options={destinations.map((space) => ({
          key: space.id,
          value: space.id,
          label: `${space.name} (${space.id})`,
        }))}
        onChange={(id) => {
          setSpaceId(id);
          setCategory("");
        }}
      />
      {entry.kind !== "skill" && (
        <TextInput
          size="small"
          label={t("rework.localMarketplace.logicalName")}
          value={logicalName}
          onChange={(event) => setLogicalName(event.target.value)}
        />
      )}
      {entry.kind === "agent" && (
        <TextInput
          size="small"
          label={t("rework.localMarketplace.displayName")}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
        />
      )}
      {entry.kind === "prompt" && (
        <Select
          size="small"
          label={t("rework.promptCategories.pickerTitle")}
          value={category}
          disabled={!destination || categories.isFetching}
          options={[
            { key: "none", value: "", label: t("rework.promptCategories.noCategory") },
            ...(categories.currentData?.items ?? []).map((item) => ({
              key: item.id,
              value: item.id,
              label: item.name,
            })),
          ]}
          onChange={setCategory}
        />
      )}
      {categories.isError && <p role="alert">{marketplaceError(categories.error, t)}</p>}
      <Button
        size="small"
        color="primary"
        variant="filled"
        disabled={
          checking ||
          !destination ||
          spaces.isFetching ||
          (entry.kind === "prompt" &&
            (!logicalName.trim() || !categories.currentData || categories.isError || categories.isFetching)) ||
          (entry.kind === "agent" && !displayName.trim())
        }
        onClick={() =>
          void onInstall({
            marketplaceSpaceId: entry.marketplace_space_id,
            entryId: entry.entry_id,
            installRequest: {
              destination_space_id: spaceId,
              proposal_id: entry.proposal_id,
              options:
                entry.kind === "prompt"
                  ? { kind: "prompt", logical_name: logicalName, category_id: category || null }
                  : entry.kind === "agent"
                    ? { kind: "agent", logical_name: logicalName || null, display_name: displayName }
                    : { kind: "skill" },
            },
          })
        }
      >
        {t("rework.localMarketplace.install")}
      </Button>
    </>
  );
}
