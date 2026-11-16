// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import Switch from "@shared/atoms/Switch/Switch";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { modelChoiceKey } from "@rework/features/capabilities/modelChoice";
import {
  useSpaceModelsQuery,
  useReplaceSpaceModelPolicyMutation,
  useListAgentInstancesQuery,
  type ModelOfferKey,
  type ReplaceSpaceModelPolicy,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamSettingsPage.module.scss";

const same = (a: ModelOfferKey | null | undefined, b: ModelOfferKey | null | undefined) =>
  a && b ? modelChoiceKey(a) === modelChoiceKey(b) : a === b;
const includes = (keys: ModelOfferKey[], key: ModelOfferKey) => keys.some((entry) => same(entry, key));

export function SpaceModels({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const access = useSpaceAccess(spaceId, "manage");
  const readAccess = useSpaceAccess(spaceId, "read");
  const canRead = access.allowed || readAccess.allowed;
  const query = useSpaceModelsQuery({ spaceId }, { skip: !canRead, refetchOnMountOrArgChange: true });
  const [replace, saving] = useReplaceSpaceModelPolicyMutation();
  const [error, setError] = useState<string>();
  const [pending, setPending] = useState<ModelOfferKey | null>(null);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const agents = useListAgentInstancesQuery(
    { spaceId, after: cursors[cursors.length - 1] },
    { skip: !pending || !readAccess.allowed, refetchOnMountOrArgChange: true },
  );
  const data = query.currentData;
  const busy = !access.allowed || saving.isLoading || query.isFetching || query.isError;
  // A first local policy must not copy parent preferences which are no longer admissible.
  // Already-local references remain saved even after their permission is revoked.
  const reasoningDefaults = data?.policy.revision
    ? data.policy.reasoning_default_on
    : (data?.models.reasoning_default_on ?? []).filter((key) =>
        data?.models.offers.some(
          (offer) =>
            same(offer.key, key) &&
            offer.selectable &&
            offer.metadata?.reasoning === true &&
            includes(data.models.policy.reasoning_enabled, key),
        ),
      );
  const save = async (patch: Partial<ReplaceSpaceModelPolicy>) => {
    if (!data || busy || !access.allowed) return;
    setError(undefined);
    try {
      await replace({
        spaceId,
        replaceSpaceModelPolicy: {
          expected_revision: data.policy.revision,
          default: data.policy.default,
          disabled: data.policy.disabled,
          reasoning_default_on: reasoningDefaults,
          ...patch,
        },
      }).unwrap();
      await query.refetch();
    } catch (failure) {
      setError(normalizeApiError(failure).status === 409 ? "conflict" : "failed");
      void query.refetch();
    }
  };
  const defaultKey = data?.models.default;
  const affected = agents.currentData?.items.filter((agent) => same(agent.recommended_model, pending)) ?? [];
  return (
    <div className={`${styles.teamSettingsPage} ${styles.modelsPage}`}>
      <PageHeader
        title={t("rework.spaceModels.title")}
        actions={
          <Tooltip
            content={
              <span className={styles.modelsHelp}>
                <strong>{t("rework.spaceModels.help")}</strong>
                <span>{t("rework.spaceModels.ceiling")}</span>
                <span>{t("rework.spaceModels.effects")}</span>
              </span>
            }
          >
            <Button color="primary" variant="text" size="small" icon={{ category: "outlined", type: "info" }}>
              {t("rework.spaceModels.help")}
            </Button>
          </Tooltip>
        }
      />
      {error && <p role="alert">{t(`rework.toolGovernance.${error}`)}</p>}
      {!access.allowed && readAccess.allowed && <p>{t("rework.teamSettings.routing.readOnly")}</p>}
      {access.error || readAccess.error || query.isError ? (
        <p role="alert">{t("rework.manager.unavailable")}</p>
      ) : !access.settled || !readAccess.settled ? (
        <p role="status">{t("common.loading")}</p>
      ) : !canRead ? (
        <p role="alert">{t("rework.spaceMembers.forbidden")}</p>
      ) : !data ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <>
          <div className={styles.modelsToolbar}>
            <p>
              {t("rework.spaceModels.currentDefault", {
                model: defaultKey
                  ? `${defaultKey.upstream_model_id} (${defaultKey.source_id})`
                  : t("rework.spaceModels.noDefault"),
              })}
            </p>
            <Button
              color="primary"
              variant="text"
              size="small"
              disabled={
                busy ||
                !data.policy.default ||
                !!(data.inherited_default && includes(data.policy.disabled, data.inherited_default))
              }
              onClick={() => void save({ default: null })}
            >
              {t("rework.spaceModels.followParent")}
            </Button>
          </div>
          {defaultKey && !data.models.offers.some((offer) => same(offer.key, defaultKey) && offer.candidate) && (
            <p role="alert">{t("rework.spaceModels.defaultUnavailable")}</p>
          )}

          {data.models.offers.length === 0 ? (
            <p role="status">{t("rework.spaceModels.empty")}</p>
          ) : (
            <div className={styles.modelsTable}>
              <DataTable
                data={data.models.offers.filter((offer) => offer.metadata?.chat !== false)}
                rowKey={(offer) => modelChoiceKey(offer.key)}
                columns={[
                  {
                    label: t("rework.spaceModels.model"),
                    size: "minmax(14rem, 2fr)",
                    cellRenderer: (offer) => (
                      <span className={styles.offerName}>
                        {offer.metadata?.display_name ?? offer.key.upstream_model_id} ({offer.key.source_id})
                      </span>
                    ),
                  },
                  {
                    label: t("rework.spaceModels.parent"),
                    size: "8rem",
                    cellRenderer: (offer) => (
                      <span>
                        {t(
                          `rework.toolGovernance.${includes(data.parent_permitted, offer.key) ? "allowed" : "denied"}`,
                        )}
                      </span>
                    ),
                  },
                  {
                    label: t("rework.spaceModels.local"),
                    size: "10rem",
                    cellRenderer: (offer) => (
                      <div className={styles.modelControl}>
                        <Switch
                          size="small"
                          checked={!includes(data.policy.disabled, offer.key)}
                          disabled={
                            busy ||
                            same(defaultKey, offer.key) ||
                            (!includes(data.parent_permitted, offer.key) && !includes(data.policy.disabled, offer.key))
                          }
                          aria-label={t("rework.spaceModels.enabledLabel", { model: offer.key.upstream_model_id })}
                          onChange={(event) =>
                            event.target.checked
                              ? void save({ disabled: data.policy.disabled.filter((key) => !same(key, offer.key)) })
                              : (setCursors([undefined]), setPending(offer.key))
                          }
                        />
                        {same(defaultKey, offer.key) && (
                          <Tooltip content={t("rework.spaceModels.protectedDefault")}>
                            <span tabIndex={0} className={styles.modelHint}>
                              {t("rework.teamSettings.routing.isDefault")}
                            </span>
                          </Tooltip>
                        )}
                      </div>
                    ),
                  },
                  {
                    label: t("rework.spaceModels.effective"),
                    size: "9rem",
                    cellRenderer: (offer) => (
                      <span>
                        {t(
                          `rework.spaceModels.${!offer.permitted ? "denied" : !offer.candidate ? "unavailable" : "allowed"}`,
                        )}
                      </span>
                    ),
                  },
                  {
                    label: t("rework.spaceModels.reasoning"),
                    size: "12rem",
                    cellRenderer: (offer) => (
                      <div className={styles.modelControl}>
                        <Switch
                          size="small"
                          checked={includes(data.models.reasoning_default_on, offer.key)}
                          disabled={
                            busy ||
                            !offer.candidate ||
                            !includes(data.models.policy.reasoning_enabled, offer.key) ||
                            offer.metadata?.reasoning !== true
                          }
                          aria-label={t("rework.spaceModels.reasoningLabel", { model: offer.key.upstream_model_id })}
                          onChange={(event) =>
                            void save({
                              reasoning_default_on: event.target.checked
                                ? [...reasoningDefaults, offer.key]
                                : reasoningDefaults.filter((key) => !same(key, offer.key)),
                            })
                          }
                        />
                        {(!includes(data.models.policy.reasoning_enabled, offer.key) ||
                          offer.metadata?.reasoning !== true) && (
                          <Tooltip content={t("rework.spaceModels.reasoningRestricted")}>
                            <span tabIndex={0} className={styles.modelHint}>
                              {t("rework.spaceModels.unavailable")}
                            </span>
                          </Tooltip>
                        )}
                      </div>
                    ),
                  },
                  {
                    label: t("rework.spaceModels.default"),
                    size: "11rem",
                    cellRenderer: (offer) => (
                      <Button
                        color="primary"
                        variant="text"
                        size="small"
                        disabled={busy || !offer.selectable || same(defaultKey, offer.key)}
                        onClick={() => void save({ default: offer.key })}
                      >
                        {t(`rework.teamSettings.routing.${same(defaultKey, offer.key) ? "isDefault" : "setDefault"}`)}
                      </Button>
                    ),
                  },
                ]}
              />
            </div>
          )}
        </>
      )}
      <ConfirmationDialog
        open={pending !== null}
        title={t("rework.spaceModels.disableTitle")}
        confirmLabel={t("common.confirm")}
        cancelLabel={t("common.cancel")}
        criticalAction
        confirmDisabled={
          busy ||
          !readAccess.settled ||
          !!readAccess.error ||
          (readAccess.allowed && (agents.isFetching || agents.isError || !agents.currentData))
        }
        onCancel={() => setPending(null)}
        onConfirm={() => {
          if (
            !pending ||
            !data ||
            !readAccess.settled ||
            readAccess.error ||
            (readAccess.allowed && (agents.isFetching || agents.isError || !agents.currentData))
          )
            return;
          void save({
            disabled: [...data.policy.disabled, pending],
            reasoning_default_on: reasoningDefaults.filter((key) => !same(key, pending)),
          });
          setPending(null);
        }}
        details={
          <>
            <p>{t("rework.spaceModels.effects")}</p>
            {!readAccess.allowed ? (
              <p>{t("rework.spaceModels.impactRestricted")}</p>
            ) : agents.isError ? (
              <p role="alert">{t("rework.manager.unavailable")}</p>
            ) : agents.isFetching || !agents.currentData ? (
              <p role="status">{t("common.loading")}</p>
            ) : (
              <>
                <p>{t("rework.spaceModels.affected")}</p>
                <div className={styles.actions}>
                  <Button
                    color="primary"
                    variant="text"
                    size="small"
                    disabled={cursors.length < 2}
                    onClick={() => setCursors((values) => values.slice(0, -1))}
                  >
                    {t("dataTable.pagination.prev")}
                  </Button>
                  <Button
                    color="primary"
                    variant="text"
                    size="small"
                    disabled={!agents.currentData.next_cursor}
                    onClick={() => setCursors((values) => [...values, agents.currentData?.next_cursor ?? undefined])}
                  >
                    {t("dataTable.pagination.next")}
                  </Button>
                </div>
                {affected.length ? (
                  <ul>
                    {affected.map((agent) => (
                      <li key={agent.agent_instance_id}>{agent.display_name}</li>
                    ))}
                  </ul>
                ) : (
                  <p>{t("rework.spaceModels.noAgents")}</p>
                )}
              </>
            )}
          </>
        }
      />
    </div>
  );
}
