// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useSpaceCapabilityPoliciesQuery,
  useReplaceSpaceCapabilityPolicyMutation,
  type SpaceCapabilityPolicy,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamSettingsPage.module.scss";

export function SpaceOffers({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const access = useSpaceAccess(spaceId, "manage");
  const query = useSpaceCapabilityPoliciesQuery(
    { spaceId },
    { skip: !access.allowed, refetchOnMountOrArgChange: true },
  );
  const [replace, mutation] = useReplaceSpaceCapabilityPolicyMutation();
  const [error, setError] = useState<string>();
  const busy = mutation.isLoading || query.isFetching;
  const save = async (policy: SpaceCapabilityPolicy, restricted: boolean, ids: string[]) => {
    if (busy || !access.allowed) return;
    setError(undefined);
    try {
      await replace({
        spaceId,
        runtimeId: policy.runtime_id,
        replaceSpaceCapabilityPolicy: {
          expected_revision: policy.revision,
          restricted,
          permitted_ids: ids,
        },
      }).unwrap();
      await query.refetch();
    } catch (failure) {
      setError(normalizeApiError(failure).status === 409 ? "conflict" : "failed");
      void query.refetch();
    }
  };
  return (
    <div className={styles.teamSettingsPage}>
      <PageHeader title={t("rework.toolGovernance.title")} />
      <p>{t("rework.toolGovernance.ceiling")}</p>
      {error && <p role="alert">{t(`rework.toolGovernance.${error}`)}</p>}
      {access.error || query.isError ? (
        <p role="alert">{t("rework.manager.unavailable")}</p>
      ) : !access.settled ? (
        <p role="status">{t("common.loading")}</p>
      ) : !access.allowed ? (
        <p role="alert">{t("rework.spaceMembers.forbidden")}</p>
      ) : !query.currentData ? (
        <p role="status">{t("common.loading")}</p>
      ) : !query.currentData.length ? (
        <p role="status">{t("rework.admin.capabilities.organizationCapabilities.noPods")}</p>
      ) : (
        query.currentData.map((policy) => (
          <section key={policy.runtime_id} className={styles.offerSource}>
            <h2>{policy.runtime_id}</h2>
            {(!policy.source_enabled || !policy.reachable) && (
              <p role="status">
                {t(`rework.toolGovernance.source.${!policy.source_enabled ? "disabled" : "unavailable"}`)}
              </p>
            )}
            <label>
              <Checkbox
                checked={policy.restricted}
                disabled={busy}
                onChange={(event) =>
                  void save(
                    policy,
                    event.target.checked,
                    event.target.checked
                      ? policy.offers.filter((offer) => offer.permitted).map((offer) => offer.capability_id)
                      : [],
                  )
                }
              />
              {t("rework.toolGovernance.restrict")}
            </label>
            {!policy.restricted && <p>{t("rework.toolGovernance.inherit")}</p>}
            {policy.restricted && (
              <Button
                color="primary"
                variant="text"
                size="small"
                disabled={busy}
                onClick={() => void save(policy, true, [])}
              >
                {t("rework.toolGovernance.denyAll")}
              </Button>
            )}
            <DataTable
              data={policy.offers}
              rowKey={(offer) => offer.capability_id}
              columns={[
                {
                  label: t("rework.toolGovernance.offer"),
                  cellRenderer: (offer) => (
                    <span className={styles.offerName}>
                      {t(offer.descriptor.name, { defaultValue: offer.descriptor.name })}
                    </span>
                  ),
                },
                {
                  label: t("rework.toolGovernance.parent"),
                  cellRenderer: (offer) => (
                    <span>{t(`rework.toolGovernance.${offer.parent_permitted ? "allowed" : "denied"}`)}</span>
                  ),
                },
                {
                  label: t("rework.toolGovernance.local"),
                  cellRenderer: (offer) => (
                    <Checkbox
                      aria-label={offer.descriptor.name}
                      checked={policy.restricted ? policy.permitted_ids.includes(offer.capability_id) : offer.permitted}
                      disabled={
                        busy ||
                        !policy.restricted ||
                        (!offer.advertised && !policy.permitted_ids.includes(offer.capability_id))
                      }
                      onChange={(event) =>
                        void save(
                          policy,
                          true,
                          event.target.checked
                            ? [...policy.permitted_ids, offer.capability_id]
                            : policy.permitted_ids.filter((id) => id !== offer.capability_id),
                        )
                      }
                    />
                  ),
                },
                {
                  label: t("rework.toolGovernance.effective"),
                  cellRenderer: (offer) => (
                    <span>
                      {t(
                        `rework.toolGovernance.${!offer.advertised ? "withdrawn" : offer.permitted ? "allowed" : "denied"}`,
                      )}
                    </span>
                  ),
                },
              ]}
            />
          </section>
        ))
      )}
    </div>
  );
}
