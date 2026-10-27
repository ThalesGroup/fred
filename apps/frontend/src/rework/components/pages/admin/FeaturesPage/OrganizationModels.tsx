// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import Button from "@shared/atoms/Button/Button.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useOrganizationModelsQuery,
  useRefreshModelSourceMutation,
  useReplaceOrganizationModelPolicyMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ModelInventory,
  ModelOfferKey,
  ReplaceModelPolicy,
  StoredModelOffer,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { normalizeApiError } from "../../../../core/errors/normalizeApiError";
import { modelChoiceKey as offerId } from "../../../../features/capabilities/modelChoice";
import styles from "./FeaturesPage.module.css";
import panelStyles from "./PlatformModelBindingsPanel/PlatformModelBindingsPanel.module.css";

const sameOffer = (left: ModelOfferKey | null | undefined, right: ModelOfferKey) =>
  left?.source_id === right.source_id && left.upstream_model_id === right.upstream_model_id;

export function OrganizationModels({
  organizationId,
  defaultsOpen,
  onCloseDefaults,
}: {
  organizationId: string;
  defaultsOpen: boolean;
  onCloseDefaults: () => void;
}) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const {
    currentData: inventory,
    isFetching,
    isError,
    refetch,
  } = useOrganizationModelsQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const [refreshSource] = useRefreshModelSourceMutation();
  const [isRefreshingModels, setIsRefreshingModels] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const initialRefreshStarted = useRef(false);
  const [replacePolicy, saving] = useReplaceOrganizationModelPolicyMutation();
  const [filter, setFilter] = useState("");
  const [pendingRevoke, setPendingRevoke] = useState<StoredModelOffer | null>(null);
  const policy = inventory?.policy;
  const offers = inventory?.sources.flatMap((source) => source.offers) ?? [];
  const busy = isFetching || isError || isRefreshingModels || saving.isLoading;
  const permitted = (offer: ModelOfferKey) => policy?.permitted.some((key) => sameOffer(key, offer)) ?? false;
  const selectable = (offer: StoredModelOffer) => {
    const observation = inventory?.sources.find(
      (source) => source.observation.source_id === offer.source_id,
    )?.observation;
    return Boolean(
      offer.advertised &&
        offer.metadata.chat === true &&
        observation?.enabled &&
        observation.state === "ok" &&
        observation.snapshot_source_revision === observation.source_revision,
    );
  };
  const save = async (change: Partial<Omit<ReplaceModelPolicy, "expected_revision">>) => {
    if (!policy || busy) return;
    try {
      await replacePolicy({
        organizationId,
        replaceModelPolicy: {
          expected_revision: policy.revision,
          permitted: policy.permitted,
          reasoning_enabled: policy.reasoning_enabled,
          default: policy.default ?? null,
          fallback: policy.fallback ?? null,
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
  const revoke = (offer: StoredModelOffer) => {
    if (!policy) return;
    void save({
      permitted: policy.permitted.filter((key) => !sameOffer(key, offer)),
      reasoning_enabled: policy.reasoning_enabled.filter((key) => !sameOffer(key, offer)),
      default: sameOffer(policy.default, offer) ? null : (policy.default ?? null),
      fallback: sameOffer(policy.fallback, offer) ? null : (policy.fallback ?? null),
    });
  };
  const refreshModels = useCallback(
    async (knownSources?: ModelInventory[]) => {
      setIsRefreshingModels(true);
      setRefreshError(null);
      try {
        const sources = (knownSources ?? (await refetch().unwrap()).sources).filter(
          ({ observation }) => observation.enabled,
        );
        const results = await Promise.allSettled(
          sources.map(({ observation }) => refreshSource({ organizationId, sourceId: observation.source_id }).unwrap()),
        );
        const errors = results.flatMap((result, index) =>
          result.status === "rejected"
            ? [
                `${sources[index].observation.source_id}: ${normalizeApiError(result.reason).detail ?? t("rework.admin.capabilities.discovery.refreshFailed")}`,
              ]
            : [],
        );
        if (errors.length) setRefreshError(errors.join("; "));
        if (sources.length) await refetch().unwrap();
      } catch (error) {
        setRefreshError(normalizeApiError(error).detail ?? t("rework.admin.capabilities.discovery.refreshFailed"));
      } finally {
        setIsRefreshingModels(false);
      }
    },
    [organizationId, refreshSource, refetch, t],
  );
  useEffect(() => {
    if (!inventory || isFetching || isError || initialRefreshStarted.current) return;
    // Swift refreshes discovery on entry; keep known rows visible during the request.
    initialRefreshStarted.current = true;
    void refreshModels(inventory.sources);
  }, [inventory, isFetching, isError, refreshModels]);
  const columns: DataTableColumn<StoredModelOffer>[] = [
    {
      label: t("rework.admin.capabilities.organizationModels.permitted"),
      size: "1fr",
      cellRenderer: (offer) => (
        <div className={styles.centered}>
          <Switch
            size="small"
            checked={permitted(offer)}
            disabled={!permitted(offer) && !selectable(offer)}
            aria-disabled={busy || (!permitted(offer) && !selectable(offer))}
            aria-label={t("rework.admin.capabilities.organizationModels.permitAria", {
              name: `${offer.source_id} / ${offer.upstream_model_id}`,
            })}
            onChange={() => {
              if (busy) return;
              if (permitted(offer)) setPendingRevoke(offer);
              else
                void save({
                  permitted: [
                    ...(policy?.permitted ?? []),
                    { source_id: offer.source_id, upstream_model_id: offer.upstream_model_id },
                  ],
                });
            }}
          />
        </div>
      ),
    },
    {
      label: t("rework.admin.capabilities.col.capability"),
      size: "3fr",
      cellRenderer: (offer) => (
        <div className={styles.capText}>
          <EntityIdentity
            name={offer.metadata.display_name ?? offer.upstream_model_id}
            sourceId={`${offer.source_id} / ${offer.upstream_model_id}`}
            dimmed={!offer.advertised}
          />
          <span className={styles.modelSpecs}>
            {(["context_window_tokens", "max_input_tokens", "max_output_tokens"] as const).map(
              (field) =>
                offer.metadata[field] != null && (
                  <span className={styles.modelSpecChip} key={field}>
                    {t(`rework.admin.capabilities.organizationModels.${field}`, { count: offer.metadata[field] })}
                  </span>
                ),
            )}
            {sameOffer(policy?.default, offer) && (
              <span className={styles.modelSpecChip}>{t("rework.admin.capabilities.organizationModels.default")}</span>
            )}
            {sameOffer(policy?.fallback, offer) && (
              <span className={styles.modelSpecChip}>{t("rework.admin.capabilities.organizationModels.fallback")}</span>
            )}
          </span>
        </div>
      ),
    },
    {
      label: t("rework.admin.capabilities.col.health"),
      size: "1fr",
      cellRenderer: (offer) =>
        t(
          `rework.admin.capabilities.organizationModels.${!offer.advertised ? "withdrawn" : offer.metadata.chat === true ? "chat" : offer.metadata.chat === false ? "notChat" : "unknownChat"}`,
        ),
    },
    {
      label: t("rework.admin.capabilities.col.reasoning"),
      size: "1fr",
      cellRenderer: (offer) => {
        const enabled = policy?.reasoning_enabled.some((key) => sameOffer(key, offer)) ?? false;
        if (offer.metadata.reasoning !== true && !enabled) return <div className={styles.centered} />;
        return (
          <div className={styles.centered}>
            <Tooltip text={t("rework.admin.capabilities.reasoningHint")}>
              <Switch
                size="small"
                checked={enabled}
                disabled={
                  busy || (!enabled && (!permitted(offer) || !selectable(offer) || offer.metadata.reasoning !== true))
                }
                aria-label={t("rework.admin.capabilities.col.reasoning")}
                onChange={() =>
                  void save({
                    reasoning_enabled: enabled
                      ? (policy?.reasoning_enabled ?? []).filter((key) => !sameOffer(key, offer))
                      : [
                          ...(policy?.reasoning_enabled ?? []),
                          { source_id: offer.source_id, upstream_model_id: offer.upstream_model_id },
                        ],
                  })
                }
              />
            </Tooltip>
          </div>
        );
      },
    },
    {
      label: t("rework.admin.capabilities.col.actions"),
      size: "1.5fr",
      cellRenderer: () => (
        <Tooltip text={t("rework.admin.capabilities.organizationModels.teamsUnavailable")}>
          <span>
            <Button
              color="on-surface"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "groups" }}
              disabled
            >
              {t("rework.admin.capabilities.manageTeams")}
            </Button>
          </span>
        </Tooltip>
      ),
    },
  ];
  const visible = offers.filter((offer) =>
    [offer.source_id, offer.upstream_model_id, offer.metadata.display_name].some((value) =>
      value?.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase()),
    ),
  );
  const choiceOptions = (choice: ModelOfferKey | null | undefined) => [
    { key: "none", value: "", label: t("rework.admin.capabilities.organizationModels.none") },
    ...(policy?.permitted ?? []).map((key) => {
      const offer = offers.find((item) => sameOffer(key, item));
      return {
        key: offerId(key),
        value: offerId(key),
        label: `${key.source_id} / ${key.upstream_model_id}`,
        disabled: !sameOffer(choice, key) && (!offer || !selectable(offer)),
      };
    }),
  ];
  return (
    <>
      <div className={styles.modelListToolbar}>
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "refresh" }}
          disabled={isFetching || saving.isLoading || isRefreshingModels}
          onClick={() => void refreshModels()}
        >
          {t("rework.admin.capabilities.discovery.refresh")}
        </Button>
        <div className={styles.modelFilter}>
          <SearchInput
            size="small"
            value={filter}
            onChange={setFilter}
            ariaLabel={t("rework.admin.capabilities.discovery.filter")}
            placeholder={t("rework.admin.capabilities.discovery.filter")}
            clearAriaLabel={t("rework.admin.capabilities.discovery.clearFilter")}
          />
        </div>
      </div>
      {(isFetching || isRefreshingModels) && (
        <p className={styles.status}>
          {t(inventory ? "rework.admin.capabilities.discovery.refreshing" : "rework.admin.capabilities.loading")}
        </p>
      )}
      {refreshError && (
        <p className={styles.statusWarning} role="alert" title={refreshError}>
          {t("rework.admin.capabilities.discovery.refreshFailed")} {refreshError}
        </p>
      )}
      {isError && (
        <p className={styles.statusError} role="alert">
          {t("rework.admin.capabilities.loadError")}
        </p>
      )}
      {!isError && inventory && (
        <>
          {visible.length ? (
            <DataTable columns={columns} data={visible} rowKey={offerId} size="medium" />
          ) : (
            !isFetching &&
            !isRefreshingModels && (
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
        </>
      )}
      <InlineDrawer
        open={defaultsOpen}
        onClose={onCloseDefaults}
        title={t("rework.admin.platformModelBindings.title")}
        width="560px"
      >
        <div className={panelStyles.body}>
          <p className={panelStyles.hint}>{t("rework.admin.capabilities.organizationModels.policyHint")}</p>
          {(["default", "fallback"] as const).map((field) => (
            <Select
              key={field}
              size="small"
              label={t(`rework.admin.capabilities.organizationModels.${field}`)}
              value={policy?.[field] ? offerId(policy[field]) : ""}
              options={choiceOptions(policy?.[field])}
              disabled={busy || !policy}
              onChange={(value) =>
                void save({ [field]: policy?.permitted.find((key) => offerId(key) === value) ?? null })
              }
            />
          ))}
        </div>
      </InlineDrawer>
      <ConfirmationDialog
        open={pendingRevoke !== null}
        title={t("rework.admin.capabilities.organizationModels.revokeTitle")}
        message={t("rework.admin.capabilities.organizationModels.revokeMessage", {
          name: pendingRevoke ? `${pendingRevoke.source_id} / ${pendingRevoke.upstream_model_id}` : "",
        })}
        confirmLabel={t("rework.admin.capabilities.defaultOffConfirm.confirm")}
        cancelLabel={t("rework.admin.capabilities.defaultOffConfirm.cancel")}
        criticalAction
        confirmDisabled={busy}
        onConfirm={() => {
          if (pendingRevoke) revoke(pendingRevoke);
          setPendingRevoke(null);
        }}
        onCancel={() => setPendingRevoke(null)}
      />
    </>
  );
}
