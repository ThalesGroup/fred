// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Switch from "@shared/atoms/Switch/Switch";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import {
  useOrganizationKnowledgeBaseServicesQuery,
  useRegisterKnowledgeBaseServiceMutation,
  useUpdateKnowledgeBaseServiceMutation,
  useOrganizationCapabilitiesQuery,
  useSetOrganizationCapabilityDefaultMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  KnowledgeBaseService,
  RegisterKnowledgeBaseService,
  CapabilityInventoryOffer,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./FeaturesPage.module.css";
const prefix = "rework.knowledgeBases.registry";

export default function OrganizationKnowledgeBases({ organizationId }: { organizationId: string }) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const services = useOrganizationKnowledgeBaseServicesQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const inventory = useOrganizationCapabilitiesQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const [form, setForm] = useState<KnowledgeBaseService | "create" | null>(null);
  const [setDefault, mutation] = useSetOrganizationCapabilityDefaultMutation();
  const changing = useRef(false);
  const [changingId, setChangingId] = useState<string | null>(null);
  const toggle = async (offer: CapabilityInventoryOffer) => {
    if (changing.current) return;
    changing.current = true;
    setChangingId(offer.capability_id);
    try {
      await setDefault({
        organizationId,
        sourceId: offer.source_id,
        capabilityId: offer.capability_id,
        setDefaultOnRequest: { default_on: !offer.default_on },
      }).unwrap();
    } catch (error) {
      showError({
        summary: t("rework.admin.capabilities.defaultToggleError"),
        detail: normalizeApiError(error).detail,
      });
    } finally {
      changing.current = false;
      setChangingId(null);
    }
  };
  const authorize = (offer: CapabilityInventoryOffer) => {
    if (!offer.default_on) {
      void toggle(offer);
      return;
    }
    showConfirmationDialog({
      criticalAction: true,
      title: t(`${prefix}.disableTitle`),
      message: t(`${prefix}.disableMessage`),
      confirmButtonLabel: t("rework.admin.capabilities.defaultOffConfirm.confirm"),
      cancelButtonLabel: t("common.cancel"),
      onConfirm: () => toggle(offer),
    });
  };
  return (
    <div>
      <p>{t(`${prefix}.hint`)}</p>
      <div className={styles.modelListToolbar}>
        <Button
          color="on-surface"
          variant="outlined"
          size="medium"
          onClick={() => {
            void services.refetch();
            void inventory.refetch();
          }}
        >
          {t("common.refresh")}
        </Button>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: "add" }}
          onClick={() => setForm("create")}
        >
          {t(`${prefix}.create`)}
        </Button>
      </div>
      {services.isError || inventory.isError ? (
        <p role="alert">{t("rework.admin.capabilities.loadError")}</p>
      ) : !services.currentData || !inventory.currentData ? (
        <p role="status">{t("common.loading")}</p>
      ) : services.currentData.length === 0 ? (
        <p>{t("rework.admin.capabilities.emptyKnowledgeBases")}</p>
      ) : (
        services.currentData.map((service) => {
          const offers =
            inventory.currentData?.find(
              (source) => source.source_id === service.runtime_id && source.origin === "knowledge_base",
            )?.capabilities ?? [];
          return (
            <section key={service.runtime_id}>
              <div className={styles.modelListToolbar}>
                <h3>{service.runtime_id}</h3>
                <Button color="on-surface" variant="outlined" size="small" onClick={() => setForm(service)}>
                  {t("common.edit")}
                </Button>
              </div>
              {offers.length === 0 ? (
                <p>{t(`${prefix}.awaitingPublication`)}</p>
              ) : (
                <DataTable
                  data={offers}
                  rowKey={(offer) => offer.capability_id}
                  columns={[
                    {
                      label: t("rework.admin.capabilities.col.defaultOn"),
                      cellRenderer: (offer) => (
                        <Switch
                          checked={offer.default_on}
                          disabled={
                            (mutation.isLoading && changingId !== offer.capability_id) ||
                            (!offer.advertised && !offer.default_on)
                          }
                          aria-label={t(`${prefix}.authorize`, { name: offer.descriptor.name })}
                          onChange={() => authorize(offer)}
                        />
                      ),
                    },
                    {
                      label: t("rework.admin.capabilities.col.capability"),
                      cellRenderer: (offer) => offer.descriptor.name,
                    },
                    { label: t("common.description"), cellRenderer: (offer) => offer.descriptor.description },
                  ]}
                />
              )}
            </section>
          );
        })
      )}
      {form && (
        <CollectorForm
          organizationId={organizationId}
          service={form === "create" ? undefined : form}
          onClose={() => setForm(null)}
        />
      )}
    </div>
  );
}

function CollectorForm({
  organizationId,
  service,
  onClose,
}: {
  organizationId: string;
  service?: KnowledgeBaseService;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<RegisterKnowledgeBaseService>({
    runtime_id: service?.runtime_id ?? "",
    issuer: service?.issuer ?? "",
    audience: service?.audience ?? "",
    client_id: service?.client_id ?? "",
  });
  const [bindings, setBindings] = useState(service?.credential_bindings.join(", ") ?? "");
  const [register, registering] = useRegisterKnowledgeBaseServiceMutation();
  const [update, updating] = useUpdateKnowledgeBaseServiceMutation();
  const [error, setError] = useState<string>();
  const saving = useRef(false);
  const busy = registering.isLoading || updating.isLoading;
  const save = async () => {
    if (saving.current) return;
    saving.current = true;
    setError(undefined);
    const credential_bindings = bindings
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    try {
      if (service)
        await update({
          organizationId,
          runtimeId: service.runtime_id,
          updateKnowledgeBaseService: { expected_revision: service.revision, credential_bindings },
        }).unwrap();
      else await register({ organizationId, registerKnowledgeBaseService: { ...draft, credential_bindings } }).unwrap();
      onClose();
    } catch (failure) {
      setError(normalizeApiError(failure).status === 409 ? "conflict" : "saveFailed");
    } finally {
      saving.current = false;
    }
  };
  return (
    <Dialog
      open
      title={t(`${prefix}.${service ? "edit" : "create"}`)}
      confirmLabel={t("common.save")}
      confirmDisabled={
        busy || ![draft.runtime_id, draft.issuer, draft.client_id, draft.audience].every((value) => value.trim())
      }
      onConfirm={save}
      onCancel={onClose}
    >
      <p>{t(`${prefix}.identityHint`)}</p>
      {(["runtime_id", "issuer", "client_id", "audience"] as const).map((field) => (
        <TextInput
          key={field}
          label={t(`${prefix}.${field}`)}
          value={draft[field]}
          disabled={!!service || busy}
          onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
        />
      ))}
      <TextInput
        label={t(`${prefix}.bindings`)}
        value={bindings}
        disabled={busy}
        onChange={(event) => setBindings(event.target.value)}
      />
      <p>{t(`${prefix}.bindingsHint`)}</p>
      {error && <p role="alert">{t(`${prefix}.${error}`)}</p>}
    </Dialog>
  );
}
