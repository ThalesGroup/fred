// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import { useStore } from "react-redux";
import type { AppState } from "../../../../common/store";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CodeBlock } from "@shared/molecules/CodeBlock/CodeBlock";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import Chip from "@shared/atoms/Chip/Chip";
import { formatDateTime } from "@rework/utils/formatDateTime";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import TextArea from "@shared/atoms/TextArea/TextArea";
import Select from "@shared/molecules/Select/Select";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  enhancedControlPlaneApi,
  useMarketplaceEntryQuery,
  useMarketplaceProposalQuery,
  useMarketplaceProposalsQuery,
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
import {
  installationPath,
  marketplaceError,
  marketplaceName,
  type AttemptContext,
  useMarketplaceAttempt,
  useMarketplaceSession,
} from "./marketplace";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import styles from "./Marketplace.module.css";

import { KeyCloakService } from "../../../../security/KeycloakService";

type InstallationRequest = Omit<InstallMarketplaceEntryApiArg, "Idempotency-Key">;

type DetailProps = {
  marketplaceSpaceId: string;
  entryId?: string;
  proposalId?: string;
  onClose: () => void;
  installFirst?: boolean;
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

function ReviewContext({ marketplaceSpaceId, entryId, proposalId, onClose, installFirst = false }: DetailProps) {
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
  const installAttempt = async (args: InstallationRequest, context?: AttemptContext) => {
    if (!active() || (!attempt.started && !verified())) return;
    await attempt.run(args, (request, key) => install({ ...request, "Idempotency-Key": key }).unwrap(), context);
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
      if (active()) {
        if (close) onClose();
        else void query.refetch();
      }
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
  const history = useMarketplaceProposalsQuery(sessionQueryArgs({ marketplaceSpaceId, kind: detail?.kind }), {
    skip: !detail,
    refetchOnMountOrArgChange: true,
  });
  const related = history.isError
    ? []
    : (history.currentData?.items ?? [])
        .filter((item) => item.entry_id === detail?.entry_id)
        .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at));
  return (
    <Dialog
      open
      title={detail?.display_name ?? t("rework.localMarketplace.inspect")}
      onCancel={busy || attempt.busy ? () => {} : onClose}
      hideConfirm
      confirmLabel=""
      onConfirm={() => {}}
      cancelLabel={t("rework.localMarketplace.close")}
      dense
      className={styles.detailDialog}
    >
      <div className={styles.content}>
        {query.isFetching && detail && <p role="status">{t("common.loading")}</p>}
        {error != null && <p role="alert">{marketplaceError(error, t, undefined, true)}</p>}
        {query.isError ? (
          <p role="alert">{marketplaceError(query.error, t)}</p>
        ) : !detail ? (
          <p role="status">{t("common.loading")}</p>
        ) : (
          <>
            <p>{detail.description}</p>
            <div className={styles.actions}>
              <Chip
                label={t(
                  proposal ? `rework.localMarketplace.states.${proposal.state}` : "rework.localMarketplace.published",
                )}
              />
              <span className={styles.identity}>
                {marketplaceName(detail.origin_name, t)} ·{" "}
                {formatDateTime(proposal ? proposal.submitted_at : entry?.published_at)}
              </span>
            </div>
            {proposal && <p>{t("rework.localMarketplace.proposalSnapshot")}</p>}
            <Disclosure title={t("rework.localMarketplace.inspect")} defaultOpen={!installFirst}>
              <MarketplacePackageView value={detail.package} />
            </Disclosure>
            {proposal && (
              <>
                {proposal.decided_at && (
                  <p className={styles.identity}>
                    {t("rework.localMarketplace.decidedAt", { date: formatDateTime(proposal.decided_at) })}
                  </p>
                )}
                {proposal.decision_reason && <p className={styles.text}>{proposal.decision_reason}</p>}
                <p>
                  {t(
                    proposal.published_proposal_id === proposal.proposal_id
                      ? "rework.localMarketplace.currentPublication"
                      : proposal.published_proposal_id
                        ? "rework.localMarketplace.otherPublication"
                        : "rework.localMarketplace.noCurrentPublication",
                  )}
                </p>
                {proposal.published_proposal_id && proposal.published_proposal_id !== proposal.proposal_id && (
                  <Link to={`?catalogue=${marketplaceSpaceId}&entry=${proposal.entry_id}`}>
                    {t("rework.localMarketplace.viewCurrentPublication")}
                  </Link>
                )}
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
                    variant="outlined"
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
          </>
        )}
        {entryId && (entry || attempt.started || attempt.error != null) && (
          <section className={styles.content}>
            <h3>{t("rework.localMarketplace.install")}</h3>
            {entry && (
              <div hidden={attempt.started}>
                <InstallForm
                  key={entry.proposal_id}
                  entry={entry}
                  checking={query.isFetching}
                  onInstall={installAttempt}
                />
              </div>
            )}
            {attempt.busy && <p role="status">{t("common.loading")}</p>}
            {attempt.context && (
              <p className={styles.identity}>
                {attempt.context.name !== detail?.display_name && `${attempt.context.name} · `}
                {attempt.context.destination} · {formatDateTime(attempt.context.startedAt)}
              </p>
            )}
            {attempt.args && entry && attempt.args.installRequest.proposal_id !== entry.proposal_id && (
              <p>{t("rework.localMarketplace.earlierInstallation")}</p>
            )}
            {attempt.started && !attempt.busy && !attempt.canReset && (
              <p role="status">{t("rework.localMarketplace.resumeAttempt")}</p>
            )}
            {attempt.error != null && (
              <p role="alert">
                {marketplaceError(
                  attempt.error,
                  t,
                  attempt.context?.destination ?? t("rework.localMarketplace.destination"),
                  true,
                )}
              </p>
            )}
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
            ) : attempt.args && !attempt.canReset ? (
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
            {entry && attempt.canReset && normalizeApiError(attempt.error).code !== "publication_changed" && (
              <Button
                size="small"
                color="primary"
                variant="outlined"
                disabled={query.isFetching}
                onClick={() => {
                  if (verified()) attempt.reset();
                }}
              >
                {t(
                  attempt.result ? "rework.localMarketplace.installAnother" : "rework.localMarketplace.correctRequest",
                )}
              </Button>
            )}
          </section>
        )}
        {detail && (
          <Disclosure title={t("rework.localMarketplace.history")}>
            {history.isError ? (
              <p role="alert">{marketplaceError(history.error, t)}</p>
            ) : !history.currentData ? (
              <p role="status">{t("common.loading")}</p>
            ) : (
              <ul className={styles.history}>
                {related.map((item) => (
                  <li key={item.proposal_id}>
                    <Link to={`?catalogue=${marketplaceSpaceId}&proposal=${item.proposal_id}`}>
                      {item.display_name} · {formatDateTime(item.submitted_at)}
                    </Link>
                    <Chip label={t(`rework.localMarketplace.states.${item.state}`)} />
                    {item.published_proposal_id === item.proposal_id && (
                      <span>{t("rework.localMarketplace.currentPublication")}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <p className={styles.identity}>{t("rework.localMarketplace.historyHint")}</p>
          </Disclosure>
        )}
        {entry && entry.can_withdraw && (
          <Button
            size="small"
            color="error"
            variant="outlined"
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
        {detail && (
          <Disclosure title={t("rework.localMarketplace.diagnostics")}>
            <CodeBlock
              language="json"
              code={JSON.stringify(
                {
                  marketplace_space_id: marketplaceSpaceId,
                  entry_id: detail.entry_id,
                  proposal_id: detail.proposal_id,
                  publication_version: detail.publication_version,
                  submitted_by: proposal?.submitted_by,
                  decided_by: proposal?.decided_by,
                },
                null,
                2,
              )}
            />
          </Disclosure>
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
    </Dialog>
  );
}

function InstallForm({
  entry,
  onInstall,
  checking,
}: {
  entry: MarketplaceEntryDetail;
  checking: boolean;
  onInstall: (args: InstallationRequest, context: AttemptContext) => Promise<void>;
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
          label: `${space.kind === "personal" ? t("rework.userSettings.personalSpace") : space.name} · ${t(`rework.localMarketplace.spaceKinds.${space.kind}`)}`,
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
          void onInstall(
            {
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
            },
            {
              name: entry.display_name,
              destination:
                destination?.kind === "personal" ? t("rework.userSettings.personalSpace") : (destination?.name ?? ""),
            },
          )
        }
      >
        {t("rework.localMarketplace.install")}
      </Button>
    </>
  );
}
