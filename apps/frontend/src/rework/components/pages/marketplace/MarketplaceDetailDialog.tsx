// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useRef, useState, type ReactNode } from "react";
import { useStore } from "react-redux";
import type { AppState } from "../../../../common/store";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Chip from "@shared/atoms/Chip/Chip";
import { formatDateTime } from "@rework/utils/formatDateTime";
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
  DiscoverableResource,
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
import layout from "../PromptsPage/PromptsPage.module.scss";

import { KeyCloakService } from "../../../../security/KeycloakService";

type InstallationRequest = Omit<InstallMarketplaceEntryApiArg, "Idempotency-Key">;

type DetailProps = {
  marketplaceSpaceId: string;
  resource?: DiscoverableResource;
  entryId?: string;
  proposalId?: string;
  onClose: () => void;
};

export default function MarketplaceDetailDialog(props: DetailProps) {
  const { t } = useTranslation();
  if (props.resource) {
    const resource = props.resource;
    return (
      <ResourceDetailFrame title={resource.display_name} onClose={props.onClose}>
        <p>{resource.description}</p>
        <p>
          {resource.space_name} · {t(`rework.localMarketplace.spaceKinds.${resource.space_kind}`)}
        </p>
        <Chip label={t("rework.resourceDiscovery.metadataOnly")} />
        <p>{t("rework.resourceDiscovery.hint")}</p>
        {resource.can_read && (
          <Link
            to={`/team/${encodeURIComponent(resource.space_id)}/${resource.kind}s?resource=${encodeURIComponent(resource.resource_id)}`}
          >
            {t("rework.resourceDiscovery.openSource")}
          </Link>
        )}
      </ResourceDetailFrame>
    );
  }
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
  return (
    <ResourceDetailFrame
      title={detail?.display_name ?? t("rework.localMarketplace.inspect")}
      onClose={busy || attempt.busy ? () => {} : onClose}
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
            {detail.kind !== "prompt" && <p>{detail.description}</p>}
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
            <MarketplacePackageView value={detail.package} canDownload={!query.isFetching} />
            {proposal && (
              <>
                {proposal.decided_at && (
                  <p className={styles.identity}>
                    {t("rework.localMarketplace.decidedAt", { date: formatDateTime(proposal.decided_at) })}
                  </p>
                )}
                {proposal.decision_reason && <p className={styles.text}>{proposal.decision_reason}</p>}
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
                            void mutate(
                              () =>
                                decide({
                                  marketplaceSpaceId,
                                  proposalId: proposal.proposal_id,
                                  proposalDecisionRequest: {
                                    approve,
                                    reason: reason || null,
                                    expected_publication_version: proposal.publication_version,
                                  },
                                }).unwrap(),
                              true,
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
                      void mutate(() => cancel({ marketplaceSpaceId, proposalId: proposal.proposal_id }).unwrap(), true)
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
    </ResourceDetailFrame>
  );
}

function ResourceDetailFrame({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <FullPageModal isOpen onClose={onClose} id="marketplace-resource-modal" background="scrim">
      <div className={layout.modalCard}>
        <div className={layout.modalHeader}>
          <span id="marketplace-resource-modal-title" className={layout.modalTitle}>
            {title}
          </span>
          <Button size="small" variant="text" color="on-surface" onClick={onClose}>
            {t("rework.localMarketplace.close")}
          </Button>
        </div>
        {children}
      </div>
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
