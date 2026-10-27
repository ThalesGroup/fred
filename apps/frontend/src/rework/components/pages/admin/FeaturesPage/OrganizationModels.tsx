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
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useOrganizationModelsQuery,
  useRefreshModelSourceMutation,
  useReplaceOrganizationModelPolicyMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
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
  const [refreshSource, refreshing] = useRefreshModelSourceMutation();
  const [replacePolicy, saving] = useReplaceOrganizationModelPolicyMutation();
  const [filter, setFilter] = useState("");
  const [pendingRevoke, setPendingRevoke] = useState<StoredModelOffer | null>(null);
  const policy = inventory?.policy;
  const offers = inventory?.sources.flatMap((source) => source.offers) ?? [];
  const busy = isFetching || isError || refreshing.isLoading || saving.isLoading;
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
      default: sameOffer(policy.default, offer) ? null : (policy.default ?? null),
      fallback: sameOffer(policy.fallback, offer) ? null : (policy.fallback ?? null),
    });
  };
  const refresh = async (sourceId: string) => {
    try {
      await refreshSource({ organizationId, sourceId }).unwrap();
    } catch (error) {
      showError({
        summary: t("rework.admin.capabilities.discovery.refreshFailed"),
        detail: normalizeApiError(error).detail,
      });
    }
  };
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
      cellRenderer: () => (
        <Tooltip text={t("rework.admin.capabilities.organizationModels.reasoningUnavailable")}>
          <span className={styles.status}>{t("rework.admin.capabilities.organizationModels.unavailable")}</span>
        </Tooltip>
      ),
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
      <div className={styles.modelToolbar}>
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "refresh" }}
          disabled={isFetching || saving.isLoading || refreshing.isLoading}
          onClick={() => void refetch()}
        >
          {t("rework.admin.capabilities.organizationModels.reload")}
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
      {isFetching && <p className={styles.status}>{t("rework.admin.capabilities.loading")}</p>}
      {isError && (
        <p className={styles.statusError} role="alert">
          {t("rework.admin.capabilities.loadError")}
        </p>
      )}
      {!isError && inventory && (
        <>
          <div className={styles.discoveryStatus}>
            {inventory.sources.map(({ observation }) => (
              <div className={styles.discoverySource} key={observation.source_id}>
                <strong className={styles.discoveryReadOnlyUrl}>{observation.source_id}</strong>
                <span className={observation.state === "ok" ? styles.status : styles.statusWarning}>
                  {t("rework.admin.capabilities.organizationModels.sourceState", {
                    state: t(`rework.admin.capabilities.organizationModels.states.${observation.state}`, {
                      defaultValue: observation.state,
                    }),
                  })}
                  {!observation.enabled && ` - ${t("rework.admin.capabilities.organizationModels.disabled")}`}
                  {observation.snapshot_source_revision !== observation.source_revision &&
                    ` - ${t("rework.admin.capabilities.organizationModels.stale")}`}
                </span>
                {observation.last_success_at && (
                  <span className={styles.status}>
                    {t("rework.admin.capabilities.organizationModels.lastSuccess", {
                      date: new Date(observation.last_success_at).toLocaleString(),
                    })}
                  </span>
                )}
                {observation.error_code && <span className={styles.statusError}>{observation.error_code}</span>}
                <Button
                  color="on-surface"
                  variant="outlined"
                  size="small"
                  icon={{ category: "outlined", type: "refresh" }}
                  disabled={busy || !observation.enabled}
                  onClick={() => void refresh(observation.source_id)}
                >
                  {t("rework.admin.capabilities.organizationModels.refreshSource", { source: observation.source_id })}
                </Button>
              </div>
            ))}
          </div>
          {visible.length ? (
            <DataTable columns={columns} data={visible} rowKey={offerId} size="medium" />
          ) : (
            <PageEmptyState
              icon="tune"
              message={t(
                filter ? "rework.admin.capabilities.discovery.noMatches" : "rework.admin.capabilities.emptyModels",
              )}
            />
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
