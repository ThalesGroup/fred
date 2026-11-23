// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import Button from "@shared/atoms/Button/Button.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { MaterialIcon } from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocalStorageState } from "../../../../../hooks/useLocalStorageState";
import {
  useOrganizationModelsQuery,
  useReplaceOrganizationModelPolicyMutation,
  useDeleteModelCatalogMutation,
  useStartVectorReindexMutation,
  useVectorReindexStatusQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ModelInventory,
  ModelOfferKey,
  ReplaceModelPolicy,
  StoredModelOffer,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import {
  modelChoiceKey as offerId,
  modelUsageNotice,
  reportedUsageFirst,
} from "../../../../features/capabilities/modelChoice";
import { safeHttpUrl } from "../../../../utils/externalUrl";
import styles from "./FeaturesPage.module.css";
import panelStyles from "./PlatformModelBindingsPanel/PlatformModelBindingsPanel.module.css";
import { ModelCatalogForm } from "./ModelCatalogForm";
import { LicenseBadge, ModelMetadataDialog } from "./ModelMetadataDialog";
import { ModelAccessDialog } from "./ModelAccessDialog";
import catalogStyles from "./ModelCatalog.module.css";

const sameOffer = (left: ModelOfferKey | null | undefined, right: ModelOfferKey) =>
  left?.source_id === right.source_id && left.upstream_model_id === right.upstream_model_id;

const compactTokens = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 0 });
const usageKey = "rework.admin.capabilities.organizationModels.usages";

type Choice = "default" | "fallback" | "title" | "creation_assistant" | "embedding" | "vision" | "transcription";

const fits = (choice: Choice, { metadata, uses }: StoredModelOffer) => {
  if (choice === "embedding") return uses?.embedding ?? metadata.embedding === true;
  if (choice === "transcription") return uses?.transcription ?? metadata.audio_transcription === true;
  if (choice === "vision") return uses?.vision ?? (metadata.chat === true && metadata.vision !== false);
  return uses?.chat ?? metadata.chat === true;
};

export function OrganizationModels({ organizationId }: { organizationId: string }) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const {
    currentData: inventory,
    isFetching,
    isError,
    refetch: refetchInventory,
  } = useOrganizationModelsQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const [replacePolicy, saving] = useReplaceOrganizationModelPolicyMutation();
  const [filter, setFilter] = useState("");
  const [pendingPermission, setPendingPermission] = useState<{ offer: StoredModelOffer; authorize: boolean } | null>(
    null,
  );
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [catalogActionsOpen, setCatalogActionsOpen] = useState(false);
  const [addingSource, setAddingSource] = useState<"catalog" | "model" | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ModelInventory | null>(null);
  const [modelEditor, setModelEditor] = useState<{ offer: StoredModelOffer; usageOnly?: boolean } | null>(null);
  const [accessOffer, setAccessOffer] = useState<StoredModelOffer | null>(null);
  const [defaultsOpen, setDefaultsOpen] = useState(false);
  const [deleteCatalog, deleting] = useDeleteModelCatalogMutation();
  const [startReindex, startingReindex] = useStartVectorReindexMutation();
  const { currentData: reindex, refetch: refetchReindex } = useVectorReindexStatusQuery(
    { organizationId },
    { pollingInterval: 2500, skipPollingIfUnfocused: true, refetchOnMountOrArgChange: true },
  );
  const [dismissedReindexId, setDismissedReindexId] = useLocalStorageState<string | null>(
    `vector-reindex-dismissed:${organizationId}`,
    null,
  );
  const [reindexRequest, setReindexRequest] = useState<{ id: string; target: string } | null>(null);
  const chooseReindex = (target: string, id: string = crypto.randomUUID()) => setReindexRequest({ id, target });
  const catalogKey = "rework.admin.capabilities.organizationModels.catalogs";
  const defaultsKey = "rework.admin.capabilities.organizationModels.defaults";
  const reindexKey = "rework.admin.capabilities.organizationModels.reindex";
  const policy = inventory?.policy;
  const selectedSource =
    inventory?.sources.find((source) => source.observation.source_id === activeSourceId) ?? inventory?.sources[0];
  const platformTerms = selectedSource?.platform_terms_url && safeHttpUrl(selectedSource.platform_terms_url);
  const offers = inventory?.sources.flatMap((source) => source.offers) ?? [];
  const busy = isFetching || isError || saving.isLoading || deleting.isLoading;
  const rebuilding = reindex?.status === "pending" || reindex?.status === "running";
  useEffect(() => {
    if (reindex?.status === "succeeded") void refetchInventory();
  }, [reindex?.id, reindex?.status, refetchInventory]);
  const removeCatalog = async () => {
    if (!pendingDelete) return;
    try {
      await deleteCatalog({ organizationId, sourceId: pendingDelete.observation.source_id }).unwrap();
      setPendingDelete(null);
    } catch (error) {
      showError({ summary: t(`${catalogKey}.deleteFailed`), detail: normalizeApiError(error).detail });
    }
  };
  const rebuild = async () => {
    const embedding = policy?.permitted.find((key) => offerId(key) === reindexRequest?.target);
    if (!embedding || !policy || !reindexRequest) return;
    try {
      await startReindex({
        organizationId,
        startVectorReindex: { id: reindexRequest.id, expected_policy_revision: policy.revision, embedding },
      }).unwrap();
      setReindexRequest(null);
      await refetchReindex();
    } catch (error) {
      showError({ summary: t(`${reindexKey}.startFailed`), detail: normalizeApiError(error).detail });
    }
  };
  const permitted = (offer: ModelOfferKey) => policy?.permitted.some((key) => sameOffer(key, offer)) ?? false;
  const save = async (change: Partial<Omit<ReplaceModelPolicy, "expected_revision">>) => {
    if (!policy || busy) return;
    try {
      await replacePolicy({
        organizationId,
        replaceModelPolicy: {
          expected_revision: policy.revision,
          permitted: policy.permitted,
          default: policy.default ?? null,
          fallback: policy.fallback ?? null,
          title: policy.title ?? null,
          creation_assistant: policy.creation_assistant ?? null,
          embedding: policy.embedding ?? null,
          vision: policy.vision ?? null,
          ...change,
        },
      }).unwrap();
      showSuccess({ summary: t("rework.admin.capabilities.organizationModels.saved") });
    } catch (error) {
      showError({
        summary: t("rework.admin.capabilities.organizationModels.saveError"),
        detail: normalizeApiError(error).detail,
      });
    }
  };
  const authorize = (offer: StoredModelOffer) => {
    if (!policy || permitted(offer) || !offer.selectable) return;
    const { source_id, upstream_model_id } = offer;
    void save({ permitted: [...policy.permitted, { source_id, upstream_model_id }] });
  };
  const revoke = (offer: StoredModelOffer) => {
    if (!policy) return;
    void save({
      permitted: policy.permitted.filter((key) => !sameOffer(key, offer)),
      default: sameOffer(policy.default, offer) ? null : (policy.default ?? null),
      fallback: sameOffer(policy.fallback, offer) ? null : (policy.fallback ?? null),
      title: sameOffer(policy.title, offer) ? null : (policy.title ?? null),
      creation_assistant: sameOffer(policy.creation_assistant, offer) ? null : (policy.creation_assistant ?? null),
      embedding: sameOffer(policy.embedding, offer) ? null : (policy.embedding ?? null),
      vision: sameOffer(policy.vision, offer) ? null : (policy.vision ?? null),
      ...(sameOffer(policy.transcription, offer) ? { transcription: null } : {}),
    });
  };
  // The indexed corpus keeps its embedding model, so it stays permitted.
  const corpusModel = (offer: ModelOfferKey) =>
    (policy?.embedding_locked ?? false) && sameOffer(policy?.embedding, offer);
  const describeUsages = ({ metadata }: StoredModelOffer) => {
    const capabilities = metadata.provider_capabilities ?? {};
    const fileTranscription = metadata.audio_transcription ?? capabilities.audio_transcription;
    const manual = (field: string) =>
      metadata.provenance?.[field] === "manual" &&
      (field !== "audio_transcription" || metadata.audio_transcription === true);
    const combinedVision = metadata.chat === true && metadata.vision === true && manual("chat") === manual("vision");
    const usages = [
      ...(metadata.chat === true ? [combinedVision ? "chatVision" : "chat"] : []),
      ...(!combinedVision && metadata.vision === true ? ["vision"] : []),
      ...(metadata.embedding === true ? ["embedding"] : []),
      ...["completion_fim", "classification", "ocr", "audio_generation", "speech_generation"].filter(
        (capability) => capabilities[capability] === true,
      ),
      ...(fileTranscription === true
        ? ["audio_transcription"]
        : capabilities.audio_transcription_realtime === true
          ? ["audio_transcription_realtime"]
          : []),
    ].map((key) => ({ key, label: t(`${usageKey}.${key}`), manual: manual(key === "chatVision" ? "chat" : key) }));
    return {
      usages,
      label: usages.length ? usages.map((usage) => usage.label).join(", ") : t(`${usageKey}.unknown`),
      hint: t(`${usageKey}.${usages.length ? "hint" : "unknownHint"}`),
      unverified: usages.length === 0,
    };
  };
  const unverified = (offer?: StoredModelOffer) =>
    offer ? (offer.uses?.unverified ?? describeUsages(offer).unverified) : false;
  const columns: DataTableColumn<StoredModelOffer>[] = [
    {
      label: t("rework.admin.capabilities.organizationModels.permitted"),
      size: "7rem",
      sortable: true,
      sortValue: (offer) => Number(permitted(offer)),
      cellRenderer: (offer) => (
        <div className={styles.centered}>
          <Switch
            size="small"
            checked={permitted(offer)}
            disabled={corpusModel(offer) || (!permitted(offer) && !offer.selectable)}
            aria-disabled={busy || corpusModel(offer) || (!permitted(offer) && !offer.selectable)}
            aria-label={t("rework.admin.capabilities.organizationModels.permitAria", {
              name: `${offer.source_id} / ${offer.upstream_model_id}`,
            })}
            onChange={() => {
              if (busy) return;
              if (permitted(offer)) setPendingPermission({ offer, authorize: false });
              else if (unverified(offer)) setPendingPermission({ offer, authorize: true });
              else authorize(offer);
            }}
          />
        </div>
      ),
    },
    {
      label: t("rework.admin.capabilities.col.capability"),
      size: "minmax(18rem, 2fr)",
      sortable: true,
      sortValue: (offer) => offer.metadata.display_name ?? offer.upstream_model_id,
      cellRenderer: (offer) => {
        const limits = (
          [
            ["context_window_tokens", "context"],
            ["max_input_tokens", "input"],
            ["max_output_tokens", "output"],
          ] as const
        ).flatMap(([field, label]) => {
          const count = offer.metadata[field];
          return count == null
            ? []
            : [
                {
                  compact: t(`rework.admin.capabilities.modelSpecs.${label}`, { value: compactTokens.format(count) }),
                  exact: t(`rework.admin.capabilities.organizationModels.${field}`, { count }),
                },
              ];
        });
        return (
          <div className={styles.capText}>
            <EntityIdentity name={offer.metadata.display_name ?? offer.upstream_model_id} dimmed={!offer.advertised} />
            <span className={styles.modelSpecs}>
              {limits.length > 0 && (
                <Tooltip content={limits.map(({ exact }) => exact).join(" · ")} asChild>
                  <span className={styles.modelSpecChip} tabIndex={0}>
                    {limits.map(({ compact }) => compact).join(" · ")}{" "}
                    {t("rework.admin.capabilities.modelSpecs.tokens")}
                  </span>
                </Tooltip>
              )}
              {sameOffer(policy?.default, offer) && (
                <span className={styles.modelSpecChip}>
                  {t("rework.admin.capabilities.organizationModels.default")}
                </span>
              )}
              {sameOffer(policy?.fallback, offer) && (
                <span className={styles.modelSpecChip}>
                  {t("rework.admin.capabilities.organizationModels.fallback")}
                </span>
              )}
              {sameOffer(policy?.embedding, offer) && (
                <span className={styles.modelSpecChip}>
                  {t("rework.admin.capabilities.organizationModels.embedding")}
                </span>
              )}
              {sameOffer(policy?.vision, offer) && (
                <span className={styles.modelSpecChip}>{t("rework.admin.capabilities.organizationModels.vision")}</span>
              )}
            </span>
          </div>
        );
      },
    },
    {
      label: t(`${usageKey}.label`),
      size: "minmax(9rem, 1.25fr)",
      sortable: true,
      sortValue: (offer) => describeUsages(offer).label,
      cellRenderer: (offer) => {
        const { label, hint, usages } = describeUsages(offer);
        return (
          <div className={catalogStyles.usageCell}>
            <Tooltip text={hint}>
              <span>
                {usages.length
                  ? usages.map((usage, index) => (
                      <Fragment key={usage.key}>
                        {index > 0 && ", "}
                        {usage.label}
                        {usage.manual && (
                          <>
                            {" "}
                            <StatusBadge label={t(`${usageKey}.manual`)} tone="neutral" />
                          </>
                        )}
                      </Fragment>
                    ))
                  : label}
              </span>
            </Tooltip>
            <IconButton
              variant="icon"
              size="2xs"
              icon={{ category: "outlined", type: "edit" }}
              title={t(`${usageKey}.edit`)}
              aria-label={t(`${usageKey}.editForModel`, {
                name: offer.metadata.display_name ?? offer.upstream_model_id,
              })}
              onClick={() => setModelEditor({ offer, usageOnly: true })}
            />
          </div>
        );
      },
    },
    {
      label: t("rework.admin.capabilities.organizationModels.metadata.details"),
      size: "9rem",
      cellRenderer: (offer) => (
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "tune" }}
          onClick={() => setModelEditor({ offer })}
        >
          {t("rework.admin.capabilities.organizationModels.metadata.details")}
        </Button>
      ),
    },
    {
      label: t("rework.admin.capabilities.organizationModels.access.manage"),
      size: "13.5rem",
      cellRenderer: (offer) => (
        <Tooltip
          text={t(
            `rework.admin.capabilities.organizationModels.access.${offer.metadata.embedding ? "sharedEmbedding" : "hint"}`,
          )}
        >
          <Button
            color="on-surface"
            variant="outlined"
            size="small"
            icon={{ category: "outlined", type: "groups" }}
            disabled={!fits("default", offer) && !fits("transcription", offer)}
            onClick={() => setAccessOffer(offer)}
          >
            {t("rework.admin.capabilities.organizationModels.access.manage")}
          </Button>
        </Tooltip>
      ),
    },
  ];
  const query = filter.trim().toLocaleLowerCase();
  const visible = offers
    .filter((offer) => offer.advertised && offer.source_id === selectedSource?.observation.source_id)
    .filter(
      (offer) =>
        !query ||
        [offer.source_id, offer.upstream_model_id, offer.metadata.display_name, describeUsages(offer).label].some(
          (value) => value?.toLocaleLowerCase().includes(query),
        ),
    );
  const choiceLabel = (key: ModelOfferKey, offer?: StoredModelOffer) => {
    const name = offer?.metadata.display_name ?? key.upstream_model_id;
    const catalogue = inventory?.sources.find(({ observation }) => observation.source_id === key.source_id)?.name;
    return catalogue ? `${catalogue} / ${name}` : name;
  };
  const modelOption = (field: Choice, key: ModelOfferKey, offer?: StoredModelOffer) => ({
    key: offerId(key),
    value: offerId(key),
    label: choiceLabel(key, offer),
    disabled: !offer || !offer.selectable || !fits(field, offer),
    ...modelUsageNotice(unverified(offer), t(`${usageKey}.unverifiedHint`)),
  });
  const choiceOptions = (field: Choice) => {
    const choice = policy?.[field];
    const eligible = (policy?.permitted ?? []).flatMap((key) => {
      const offer = offers.find((item) => sameOffer(key, item));
      return sameOffer(choice, key) || (offer?.advertised && fits(field, offer)) ? [{ key, offer }] : [];
    });
    return [
      {
        key: "none",
        value: "",
        label: t(
          field === "creation_assistant"
            ? `${defaultsKey}.spaceModel`
            : field === "title"
              ? `${defaultsKey}.answerModel`
              : field === "transcription"
                ? `${defaultsKey}.dictationDisabled`
                : "rework.admin.capabilities.organizationModels.none",
        ),
      },
      ...reportedUsageFirst(eligible, ({ offer }) => unverified(offer)).map(({ key, offer }) =>
        modelOption(field, key, offer),
      ),
    ];
  };
  const choiceSelect = (field: Choice, locked = false) => (
    <Select
      key={field}
      size="small"
      compact
      label={t(`${defaultsKey}.fields.${field}`)}
      value={policy?.[field] ? offerId(policy[field]) : ""}
      options={choiceOptions(field)}
      disabled={busy || !policy || locked}
      onChange={(value) => {
        if (field === "embedding" && policy?.embedding && value && value !== offerId(policy.embedding)) {
          chooseReindex(value);
          return;
        }
        void save({ [field]: policy?.permitted.find((key) => offerId(key) === value) ?? null });
      }}
    />
  );
  const canDismissReindex = reindex?.status === "succeeded" && !reindex.cleanup_pending;
  const reindexProgress = reindex && (!canDismissReindex || reindex.id !== dismissedReindexId) && (
    <div role="status" className={catalogStyles.form}>
      <div className={catalogStyles.reindexHeader}>
        <span>
          {t(`${reindexKey}.target`, {
            model: choiceLabel(
              reindex.embedding,
              offers.find((offer) => sameOffer(offer, reindex.embedding)),
            ),
          })}
        </span>
        {canDismissReindex && (
          <Button
            type="button"
            color="on-surface"
            variant="text"
            size="small"
            onClick={() => setDismissedReindexId(reindex.id)}
          >
            {t(`${reindexKey}.dismiss`)}
          </Button>
        )}
      </div>
      <span>
        {t(`${reindexKey}.states.${reindex.cleanup_pending ? "cleaning" : reindex.status}`)} ·{" "}
        {t(`${reindexKey}.progress`, { completed: reindex.completed, total: reindex.total })}
      </span>
      <ProgressBar
        theme={reindex.status === "failed" ? "error" : reindex.status === "succeeded" ? "success" : "info"}
        current={reindex.total === 0 && reindex.status === "succeeded" ? 1 : reindex.completed}
        max={Math.max(1, reindex.total)}
        aria-label={t(`${reindexKey}.progressLabel`)}
      />
      {reindex.status === "failed" && (
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          disabled={busy || startingReindex.isLoading}
          onClick={() => chooseReindex(offerId(reindex.embedding), reindex.id)}
        >
          {t(`${reindexKey}.resume`)}
        </Button>
      )}
    </div>
  );
  return (
    <>
      <div className={catalogStyles.header}>
        <div className={catalogStyles.toolbar}>
          {!!inventory?.sources.length && (
            <div className={catalogStyles.tabs}>
              <ButtonGroup
                variant="tabs"
                aria-label={t(`${catalogKey}.tabs`)}
                color="primary"
                size="small"
                selectedIndex={inventory.sources.findIndex((source) => source === selectedSource)}
                onSelectedIndexChange={(index) => {
                  setActiveSourceId(inventory.sources[index].observation.source_id);
                }}
                items={inventory.sources.map((source) => ({
                  label: source.name,
                  title: source.url ?? t(`${catalogKey}.${source.managed ? "singleModel" : "configured"}`),
                  "aria-controls": `model-catalog-${source.observation.source_id}`,
                  id: `model-catalog-tab-${source.observation.source_id}`,
                }))}
              />
            </div>
          )}
          <IconButton
            variant="outlined"
            size="small"
            icon={{ category: "outlined", type: "edit" }}
            title={t(`${catalogKey}.manage`)}
            onClick={() => setCatalogActionsOpen(true)}
            disabled={!selectedSource || deleting.isLoading}
          />
          <IconButtonMenu<"catalog" | "model">
            iconButton={{
              variant: "outlined",
              size: "small",
              icon: { category: "outlined", type: "add" },
              title: t(`${catalogKey}.addSource`),
              disabled: busy,
            }}
            options={[
              { key: "catalog", value: "catalog", label: t(`${catalogKey}.add`) },
              { key: "model", value: "model", label: t(`${catalogKey}.addModel`) },
            ]}
            onSelect={setAddingSource}
          />
          <div className={catalogStyles.listActions}>
            <div className={catalogStyles.filter}>
              <SearchInput
                size="xs"
                value={filter}
                onChange={setFilter}
                ariaLabel={t("rework.admin.capabilities.discovery.filter")}
                placeholder={t("rework.admin.capabilities.discovery.filter")}
                clearAriaLabel={t("rework.admin.capabilities.discovery.clearFilter")}
              />
            </div>
            <Button
              color="on-surface"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "tune" }}
              onClick={() => setDefaultsOpen(true)}
            >
              {t("rework.admin.platformModelBindings.openButton")}
            </Button>
          </div>
        </div>
        {platformTerms && <LicenseBadge label={t(`${catalogKey}.platformTerms`)} href={platformTerms} />}
        {selectedSource && (!selectedSource.observation.enabled || selectedSource.observation.state !== "ok") && (
          <span role="status" className={styles.statusWarning}>
            {t(
              `${catalogKey}.sourceStates.${selectedSource.observation.enabled ? selectedSource.observation.state : "disabled"}`,
            )}
          </span>
        )}
        {!defaultsOpen && reindexProgress}
      </div>
      {!isError && inventory && (
        <div
          role={selectedSource ? "tabpanel" : undefined}
          id={selectedSource ? `model-catalog-${selectedSource.observation.source_id}` : undefined}
          aria-labelledby={selectedSource ? `model-catalog-tab-${selectedSource.observation.source_id}` : undefined}
        >
          {visible.length ? (
            <DataTable columns={columns} data={visible} rowKey={offerId} size="medium" />
          ) : (
            !isFetching && (
              <PageEmptyState
                icon="tune"
                message={t(
                  filter
                    ? "rework.admin.capabilities.discovery.noMatches"
                    : inventory.sources.length === 0
                      ? "rework.admin.capabilities.organizationModels.noSources"
                      : "rework.admin.capabilities.organizationModels.noModels",
                )}
              />
            )
          )}
        </div>
      )}
      <InlineDrawer
        open={defaultsOpen}
        onClose={() => setDefaultsOpen(false)}
        title={t("rework.admin.platformModelBindings.title")}
        width="560px"
        compactHeader
      >
        <div className={catalogStyles.defaults}>
          <section className={catalogStyles.defaultSection}>
            <h3>
              <MaterialIcon type="forum" />
              {t(`${defaultsKey}.conversations`)}
            </h3>
            {choiceSelect("default")}
            {choiceSelect("fallback")}
            <p className={panelStyles.hint}>{t(`${defaultsKey}.fallbackHint`)}</p>
            {choiceSelect("title")}
          </section>
          <section className={catalogStyles.defaultSection}>
            <h3>
              <MaterialIcon type="smart_toy" />
              {t(`${defaultsKey}.agentDesign`)}
            </h3>
            {choiceSelect("creation_assistant")}
          </section>
          {policy?.transcription !== undefined && (
            <section className={catalogStyles.defaultSection}>
              <h3>
                <MaterialIcon type="mic" />
                {t(`${defaultsKey}.dictation`)}
              </h3>
              {choiceSelect("transcription")}
              <p className={panelStyles.hint}>{t(`${defaultsKey}.dictationHint`)}</p>
            </section>
          )}
          <section className={catalogStyles.defaultSection}>
            <h3>
              <MaterialIcon type="description" />
              {t("rework.admin.capabilities.organizationModels.documents")}
            </h3>
            {choiceSelect("embedding", policy?.embedding_locked || rebuilding)}
            <div className={catalogStyles.toolbar}>
              <Button
                color="on-surface"
                variant="outlined"
                size="small"
                disabled={busy || rebuilding || !policy?.embedding}
                onClick={() => chooseReindex(policy?.embedding ? offerId(policy.embedding) : "")}
              >
                {t(`${reindexKey}.title`)}
              </Button>
              <p className={panelStyles.hint}>
                {t(
                  `rework.admin.capabilities.organizationModels.${policy?.embedding_locked ? "embeddingLockedHint" : "embeddingHint"}`,
                )}
              </p>
            </div>
            {reindexProgress}
            {choiceSelect("vision")}
            <p className={panelStyles.hint}>{t(`${defaultsKey}.documentHint`)}</p>
          </section>
        </div>
      </InlineDrawer>
      {pendingPermission && (
        <ConfirmationDialog
          open
          title={t(
            `rework.admin.capabilities.organizationModels.${pendingPermission.authorize ? "authorizeUnverifiedTitle" : "revokeTitle"}`,
          )}
          message={t(
            `rework.admin.capabilities.organizationModels.${pendingPermission.authorize ? "authorizeUnverifiedMessage" : "revokeMessage"}`,
            {
              name: choiceLabel(pendingPermission.offer, pendingPermission.offer),
            },
          )}
          confirmLabel={t(
            pendingPermission.authorize
              ? "rework.admin.capabilities.organizationModels.authorizeUnverifiedConfirm"
              : "rework.admin.capabilities.defaultOffConfirm.confirm",
          )}
          cancelLabel={t("rework.admin.capabilities.defaultOffConfirm.cancel")}
          criticalAction={!pendingPermission.authorize}
          confirmDisabled={busy}
          onConfirm={() => {
            if (pendingPermission.authorize) authorize(pendingPermission.offer);
            else revoke(pendingPermission.offer);
            setPendingPermission(null);
          }}
          onCancel={() => setPendingPermission(null)}
        />
      )}
      {(addingSource || (catalogActionsOpen && selectedSource)) && (
        <ModelCatalogForm
          key={addingSource ?? selectedSource?.observation.source_id}
          source={addingSource ? undefined : selectedSource}
          singleModel={addingSource === "model"}
          organizationId={organizationId}
          inventoryFetching={isFetching}
          onDelete={() => {
            setCatalogActionsOpen(false);
            setPendingDelete(selectedSource ?? null);
          }}
          onClose={() => {
            setAddingSource(null);
            setCatalogActionsOpen(false);
          }}
          onCreated={setActiveSourceId}
        />
      )}
      {modelEditor && (
        <ModelMetadataDialog
          key={offerId(modelEditor.offer)}
          organizationId={organizationId}
          platformTermsUrl={
            selectedSource?.observation.source_id === modelEditor.offer.source_id
              ? platformTerms || undefined
              : undefined
          }
          {...modelEditor}
          onClose={() => setModelEditor(null)}
        />
      )}
      {accessOffer && (
        <ModelAccessDialog
          key={offerId(accessOffer)}
          organizationId={organizationId}
          offer={accessOffer}
          onClose={() => setAccessOffer(null)}
        />
      )}
      <ConfirmationDialog
        open={pendingDelete !== null}
        title={t(`${catalogKey}.deleteTitle`, { name: pendingDelete?.name })}
        message={t(`${catalogKey}.deleteWarning`)}
        details={
          pendingDelete?.observation.source_id === policy?.embedding?.source_id ? (
            <p>{t(`${catalogKey}.deleteEmbeddingWarning`)}</p>
          ) : undefined
        }
        confirmLabel={t(`${catalogKey}.delete`)}
        cancelLabel={t("common.cancel")}
        criticalAction
        confirmDisabled={deleting.isLoading}
        onConfirm={() => void removeCatalog()}
        onCancel={() => setPendingDelete(null)}
      />
      <Dialog
        open={reindexRequest !== null}
        title={t(`${reindexKey}.title`)}
        confirmLabel={t(`${reindexKey}.confirm`)}
        onConfirm={() => void rebuild()}
        onCancel={() => setReindexRequest(null)}
        confirmDisabled={
          startingReindex.isLoading ||
          !reindexRequest?.target ||
          rebuilding ||
          !offers.some(
            (offer) =>
              offerId(offer) === reindexRequest.target &&
              permitted(offer) &&
              offer.selectable &&
              fits("embedding", offer),
          )
        }
      >
        <div className={catalogStyles.form}>
          <p>{t(`${reindexKey}.warning`)}</p>
          <Select
            size="small"
            label={t("rework.admin.capabilities.organizationModels.embedding")}
            value={reindexRequest?.target ?? ""}
            options={reportedUsageFirst(
              offers.filter((offer) => permitted(offer) && offer.advertised && fits("embedding", offer)),
              unverified,
            ).map((offer) => modelOption("embedding", offer, offer))}
            onChange={(value) => chooseReindex(value)}
            disabled={startingReindex.isLoading}
          />
        </div>
      </Dialog>
    </>
  );
}
