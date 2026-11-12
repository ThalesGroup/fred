// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import Switch from "@shared/atoms/Switch/Switch";
import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { formatDateTime } from "@rework/utils/formatDateTime";
import TextArea from "@shared/atoms/TextArea/TextArea";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import Select from "@shared/molecules/Select/Select";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import {
  useMcpConnectionsQuery,
  useOrganizationCapabilitiesQuery,
  useSetOrganizationCapabilityDefaultMutation,
  useMcpCredentialsQuery,
  useCreateMcpConnectionMutation,
  useUpdateMcpConnectionMutation,
  useTestMcpConnectionMutation,
  usePublishMcpConnectionMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { McpConnectionView, McpConfiguration } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./McpConnectionsPage.module.css";

const key = "rework.mcp";

function ConnectionForm({
  spaceId,
  connection,
  canSave,
  onClose,
  onSaved,
}: {
  spaceId: string;
  connection: McpConnectionView | null;
  canSave: boolean;
  onClose: () => void;
  onSaved: (connection: McpConnectionView) => void;
}) {
  const { t } = useTranslation();
  const [logicalName, setLogicalName] = useState(connection?.logical_name ?? "");
  const [name, setName] = useState(connection?.display_name ?? "");
  const [description, setDescription] = useState(connection?.description ?? "");
  const [url, setUrl] = useState(connection?.configuration.url ?? "");
  const [allowHttp, setAllowHttp] = useState(connection?.configuration.allow_insecure_http ?? false);
  const initialAuth = connection?.configuration.authentication;
  const [auth, setAuth] = useState<"none" | "bearer" | "api_key">(initialAuth?.kind ?? "none");
  const [credential, setCredential] = useState(
    initialAuth && "credential_binding" in initialAuth ? initialAuth.credential_binding : "",
  );
  const [header, setHeader] = useState(initialAuth?.kind === "api_key" ? initialAuth.header : "x-api-key");
  const [error, setError] = useState("");
  const credentials = useMcpCredentialsQuery({ spaceId }, { refetchOnMountOrArgChange: true });
  const [create, creating] = useCreateMcpConnectionMutation();
  const [update, updating] = useUpdateMcpConnectionMutation();
  const busy = creating.isLoading || updating.isLoading;
  const ready =
    canSave &&
    name.trim() &&
    url.trim() &&
    (connection || /^[a-z0-9_-]{1,64}$/.test(logicalName)) &&
    (auth === "none" ||
      credentials.currentData?.some((c) => c.available && c.url === url && c.credential_binding === credential));
  const save = async () => {
    if (!ready || busy) return;
    const configuration: McpConfiguration = {
      url,
      allow_insecure_http: allowHttp,
      authentication:
        auth === "none"
          ? { kind: auth }
          : auth === "bearer"
            ? { kind: "bearer", credential_binding: credential }
            : { kind: "api_key", credential_binding: credential, header },
    };
    try {
      const saved = connection
        ? await update({
            spaceId,
            id: connection.id,
            updateMcpConnection: {
              expected_revision: connection.revision,
              display_name: name,
              description,
              configuration,
              enabled: connection.enabled,
            },
          }).unwrap()
        : await create({
            spaceId,
            createMcpConnection: { logical_name: logicalName, display_name: name, description, configuration },
          }).unwrap();
      onSaved(saved);
    } catch (e) {
      setError(t(`${key}.${normalizeApiError(e).status === 409 ? "conflict" : "error"}`));
    }
  };
  return (
    <Dialog
      open
      title={t(`${key}.${connection ? "edit" : "add"}`)}
      confirmLabel={t(`${key}.save`)}
      confirmDisabled={!ready || busy}
      onConfirm={() => void save()}
      onCancel={onClose}
      dismissible={false}
      maxWidth={640}
    >
      <div className={styles.form}>
        {error && <p role="alert">{error}</p>}
        <TextInput
          size="small"
          label={t(`${key}.logicalName`)}
          value={logicalName}
          disabled={!!connection}
          onChange={(e) => setLogicalName(e.target.value)}
          maxLength={64}
          required
        />
        <TextInput
          size="small"
          label={t(`${key}.name`)}
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={255}
          required
        />
        <TextArea
          rows={3}
          label={t(`${key}.description`)}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={2000}
        />
        <>
          <TextInput
            size="small"
            label={t(`${key}.url`)}
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setCredential("");
            }}
            required
          />
          <label className={styles.checkbox}>
            <Checkbox checked={allowHttp} onChange={(e) => setAllowHttp(e.target.checked)} />
            {t(`${key}.allowHttp`)}
          </label>
        </>
        <Select
          size="small"
          label={t(`${key}.authentication`)}
          value={auth}
          onChange={setAuth}
          options={(["none", "bearer", "api_key"] as const).map((kind) => ({
            key: kind,
            value: kind,
            label: t(`${key}.auth.${kind}`),
          }))}
        />
        {(auth === "bearer" || auth === "api_key") && (
          <Select
            size="small"
            label={t(`${key}.credential`)}
            value={credential}
            onChange={setCredential}
            options={(credentials.currentData ?? [])
              .filter((c) => c.url === url)
              .map((c) => ({
                key: c.credential_binding,
                value: c.credential_binding,
                label: c.credential_binding,
                disabled: !c.available,
                description: t(`${key}.${c.available ? "credentialReady" : "credentialMissing"}`),
              }))}
          />
        )}
        {auth === "api_key" && (
          <TextInput
            size="small"
            label={t(`${key}.header`)}
            value={header}
            onChange={(e) => setHeader(e.target.value)}
          />
        )}
        {credentials.isError && <p role="alert">{t(`${key}.error`)}</p>}
        <p>{t(`${key}.provisioning`)}</p>
      </div>
    </Dialog>
  );
}

export default function McpConnectionsPage({ spaceId }: { spaceId: string }) {
  return <Connections key={spaceId} spaceId={spaceId} />;
}

function Connections({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const access = useSpaceAccess(spaceId, "manage");
  const query = useMcpConnectionsQuery({ spaceId }, { skip: !access.allowed, refetchOnMountOrArgChange: true });
  const inventory = useOrganizationCapabilitiesQuery(
    { organizationId: spaceId },
    { skip: !access.allowed, refetchOnMountOrArgChange: true },
  );
  const source = inventory.currentData?.find((item) => item.origin === "managed_mcp");
  const [setPermission] = useSetOrganizationCapabilityDefaultMutation();
  const [editing, setEditing] = useState<McpConnectionView | null | undefined>();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viewStep, setViewStep] = useState<number>();
  const [pending, setPending] = useState<{ row: McpConnectionView; action: "revoke" | "disable" } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [test] = useTestMcpConnectionMutation();
  const [publish] = usePublishMcpConnectionMutation();
  const [update] = useUpdateMcpConnectionMutation();
  const rows = access.offered && !query.isError ? (query.currentData ?? []) : [];
  const selected = rows.find((row) => row.id === selectedId);
  const changes = selected?.tool_changes;
  const hasChanges = changes && !!(changes.added.length + changes.modified.length + changes.removed.length);
  const toolRows = selected
    ? changes
      ? [...selected.observed_tools, ...selected.published_tools.filter((tool) => changes.removed.includes(tool.name))]
      : selected.published_tools
    : [];
  const offer =
    !inventory.isError && source?.capabilities.find((item) => item.capability_id === selected?.capability_id);
  const checked =
    selected?.observation_state === "available" &&
    selected.observation_revision === selected.revision &&
    !!selected.checked_at;
  const validated =
    checked &&
    !!changes &&
    !hasChanges &&
    selected.published_revision === selected.revision &&
    selected.published_tools.length > 0;
  const ready = selected?.available && !!offer && offer.default_on;
  // Server facts determine progress; the only local choice is viewing an earlier step.
  const nextStep = !checked ? 0 : !validated ? 1 : ready ? 3 : 2;
  const step = Math.min(viewStep ?? nextStep, nextStep);
  const blocked = busy || !access.allowed || query.isFetching || query.isError;
  const run = async (action: () => Promise<unknown>) => {
    if (inFlight.current || blocked) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
      setViewStep(undefined);
    } catch (e) {
      setError(t(`${key}.${normalizeApiError(e).status === 409 ? "conflict" : "error"}`));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const permit = async (row: McpConnectionView, default_on: boolean) => {
    if (!source || inventory.isError) throw new Error("MCP authorization unavailable");
    return setPermission({
      organizationId: spaceId,
      sourceId: source.source_id,
      capabilityId: row.capability_id,
      setDefaultOnRequest: { default_on },
    }).unwrap();
  };
  const activate = (row: McpConnectionView, enabled: boolean) =>
    update({
      spaceId,
      id: row.id,
      updateMcpConnection: {
        expected_revision: row.revision,
        display_name: row.display_name,
        description: row.description,
        configuration: row.configuration,
        enabled,
      },
    }).unwrap();
  const advance = () => {
    if (!selected || blocked) return;
    if (step === 1 && (!checked || !changes || !selected.observed_tools.length)) return;
    if (step === 2 && (!validated || !offer || inventory.isFetching || inventory.isError)) return;
    void run(async () => {
      if (step === 0) {
        await test({ spaceId, id: selected.id, mcpRevision: { expected_revision: selected.revision } }).unwrap();
      } else if (step === 1 && !validated) {
        await publish({
          spaceId,
          id: selected.id,
          mcpPublication: { expected_revision: selected.revision, expected_checked_at: selected.checked_at! },
        }).unwrap();
      } else if (step === 2 && offer) {
        const active = selected.enabled ? selected : await activate(selected, true);
        if (!active.available) throw new Error("MCP connection unavailable");
        // Do not grant usage if activation failed. A permission failure leaves the
        // server's activation intact; the refreshed step retries only authorization.
        if (!offer.default_on) await permit(active, true);
      }
    });
  };
  const permissionControl = (row: McpConnectionView) => {
    const offer = !inventory.isError && source?.capabilities.find((item) => item.capability_id === row.capability_id);
    if (!offer) return <span>{t(`${key}.permissionUnknown`)}</span>;
    const blocked = !offer.default_on && !offer.advertised;
    const control = (
      <Switch
        size="small"
        checked={offer.default_on}
        disabled={!access.allowed || busy || query.isFetching || inventory.isFetching || blocked}
        aria-label={t(`${key}.allowNamed`, { name: row.display_name })}
        onChange={() => (offer.default_on ? setPending({ row, action: "revoke" }) : void run(() => permit(row, true)))}
      />
    );
    return blocked ? (
      <Tooltip text={t(`${key}.permissionRequiresReady`)}>
        <span tabIndex={0}>{control}</span>
      </Tooltip>
    ) : (
      control
    );
  };
  return (
    <div className={styles.page}>
      <PageHeader
        title={t(`${key}.title`)}
        subtitle={t(`${key}.scope`)}
        actions={
          access.allowed && (
            <Button color="primary" variant="filled" size="medium" onClick={() => setEditing(null)}>
              {t(`${key}.add`)}
            </Button>
          )
        }
      />
      {(access.error || query.isError || inventory.isError || error) && (
        <p role="alert">{error || t(`${key}.error`)}</p>
      )}
      {access.settled && !access.allowed && <p role="alert">{t("rework.spaceMembers.forbidden")}</p>}
      {(!access.settled || query.isFetching) && <p role="status">{t("common.loading")}</p>}
      {access.allowed && !query.isError && !query.isFetching && !rows.length && (
        <PageEmptyState icon="extension" message={t(`${key}.empty`)} />
      )}
      {access.offered && rows.length > 0 && (
        <DataTable
          data={rows}
          rowKey={(row) => row.id}
          size="medium"
          columns={[
            { label: t(`${key}.permission`), size: "1.5fr", cellRenderer: permissionControl },
            {
              label: t(`${key}.name`),
              size: "3fr",
              cellRenderer: (row) => (
                <div className={styles.identity}>
                  <EntityIdentity name={row.display_name} sourceId={row.logical_name} icon="extension" />
                  <p className={styles.description} title={row.description}>
                    {row.description}
                  </p>
                </div>
              ),
            },
            {
              label: t(`${key}.observation`),
              size: "1.8fr",
              cellRenderer: (row) => (
                <div className={styles.identity}>
                  <StatusBadge
                    label={t(`${key}.state.${row.observation_state}`)}
                    tone={row.observation_state === "unavailable" ? "error" : "neutral"}
                  />
                  {!row.enabled && <p className={styles.description}>{t(`${key}.disabled`)}</p>}
                </div>
              ),
            },
            { label: t(`${key}.tools`), size: "1fr", cellRenderer: (row) => row.published_tools.length },
            {
              label: t("rework.admin.capabilities.col.actions"),
              size: "1fr",
              cellRenderer: (row) => (
                <Button
                  color="on-surface"
                  variant="outlined"
                  size="small"
                  disabled={busy}
                  onClick={() => {
                    setSelectedId(row.id);
                    setViewStep(undefined);
                    setError("");
                  }}
                  aria-label={t(`${key}.detailsNamed`, { name: row.display_name })}
                >
                  {t(`${key}.details`)}
                </Button>
              ),
            },
          ]}
        />
      )}
      {access.offered && selectedId && (
        <InlineDrawer
          open
          width="960px"
          onClose={() => {
            if (!busy && editing === undefined && !pending) setSelectedId(null);
          }}
          title={selected?.display_name ?? t(`${key}.connectionUnavailable`)}
          closeLabel={t("common.close")}
        >
          {selected ? (
            <div className={styles.detail}>
              <ol className={styles.steps} aria-label={t(`${key}.setupSteps`)}>
                {["connectionStep", "toolsStep", "activationStep"].map((label, index) => (
                  <li key={label} aria-current={step === index ? "step" : undefined} data-complete={index < nextStep}>
                    {index + 1}. {t(`${key}.${label}`)}
                  </li>
                ))}
              </ol>
              {error && <p role="alert">{error}</p>}
              <div className={styles.detail} aria-busy={busy}>
                <h3 aria-live="polite">{t(`${key}.${["test", "reviewTools", "activationTitle", "ready"][step]}`)}</h3>
                {step === 0 && (
                  <>
                    <p>{t(`${key}.discoveryHint`)}</p>
                    <StatusBadge
                      label={t(`${key}.state.${selected.observation_state}`)}
                      tone={selected.observation_state === "unavailable" ? "error" : "neutral"}
                    />
                    {selected.observation_state === "unavailable" && <p role="alert">{t(`${key}.discoveryFailed`)}</p>}
                    <details>
                      <summary>{t(`${key}.technicalDetails`)}</summary>
                      <p>{selected.logical_name}</p>
                      <p>{selected.description}</p>
                      <p>{t(`${key}.checkedAt`, { date: formatDateTime(selected.checked_at) })}</p>
                      <p>{t(`${key}.discoveryScope`)}</p>
                    </details>
                  </>
                )}
                {step === 1 && (
                  <>
                    <p>{t(`${key}.reviewHint`)}</p>
                    <p role="status">
                      {validated
                        ? t(`${key}.upToDate`)
                        : hasChanges
                          ? t(`${key}.changes`, {
                              added: changes!.added.length,
                              modified: changes!.modified.length,
                              removed: changes!.removed.length,
                            })
                          : t(`${key}.validationRequired`)}
                    </p>
                    <div>
                      {toolRows.map((tool) => {
                        const change = changes?.removed.includes(tool.name)
                          ? "removed"
                          : changes?.modified.includes(tool.name)
                            ? "modified"
                            : changes?.added.includes(tool.name)
                              ? "added"
                              : null;
                        return (
                          <details key={tool.name} className={styles.tool}>
                            <summary>
                              <span className={styles.toolDescription}>{tool.name}</span>
                              {change && (
                                <StatusBadge
                                  label={t(`${key}.${change}`)}
                                  tone={change === "removed" ? "warning" : "info"}
                                />
                              )}
                            </summary>
                            {tool.description && <p>{tool.description}</p>}
                          </details>
                        );
                      })}
                    </div>
                    {!toolRows.length && <p role="status">{t(`${key}.noTools`)}</p>}
                    <details>
                      <summary>{t(`${key}.contracts`)}</summary>
                      <pre className={styles.contracts}>
                        {JSON.stringify(
                          { observed: selected.observed_tools, published: selected.published_tools },
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  </>
                )}
                {step === 2 && (
                  <>
                    <StatusBadge label={t(`${key}.upToDate`)} tone="success" />
                    <p>{t(`${key}.permissionHint`)}</p>
                    {!offer && <p role="alert">{t(`${key}.permissionUnknown`)}</p>}
                    {selected.enabled && offer && !offer.default_on && (
                      <p role="status">{t(`${key}.authorizationPending`)}</p>
                    )}
                  </>
                )}
                {step === 3 && (
                  <>
                    <StatusBadge label={t(`${key}.authorized`)} tone="success" />
                    <p>{t(`${key}.readyHint`)}</p>
                    <p>{t(`${key}.impact`, { count: selected.affected_instance_count })}</p>
                    <Button
                      color="on-surface"
                      variant="text"
                      size="small"
                      onClick={() => setViewStep(1)}
                      disabled={blocked}
                    >
                      {t(`${key}.inventory`)}
                    </Button>
                  </>
                )}
                {step < 3 && (
                  <div className={styles.footer}>
                    {step > 0 && (
                      <Button
                        color="on-surface"
                        variant="text"
                        size="medium"
                        disabled={blocked}
                        onClick={() => setViewStep(step - 1)}
                      >
                        {t("rework.back")}
                      </Button>
                    )}
                    <Button
                      color="primary"
                      variant="filled"
                      size="medium"
                      onClick={advance}
                      disabled={
                        blocked ||
                        (step === 1 && (!changes || !selected.observed_tools.length)) ||
                        (step === 2 && (!offer || inventory.isFetching || inventory.isError))
                      }
                    >
                      {busy
                        ? t("common.loading")
                        : t(
                            `${key}.${step === 0 ? "test" : step === 1 ? (validated ? "continue" : selected.published_revision === null ? "publish" : "applyChanges") : offer && offer.default_on ? "enable" : selected.enabled ? "authorize" : "activateAndAuthorize"}`,
                          )}
                    </Button>
                  </div>
                )}
              </div>
              <details className={styles.management}>
                <summary>{t(`${key}.manage`)}</summary>
                <div className={styles.detail}>
                  <p>{t(`${key}.impact`, { count: selected.affected_instance_count })}</p>
                  <div className={styles.actions}>
                    <Button
                      color="on-surface"
                      variant="outlined"
                      size="small"
                      disabled={blocked}
                      onClick={() => setEditing(selected)}
                    >
                      {t(`${key}.edit`)}
                    </Button>
                    {step !== 0 && (
                      <Button
                        color="on-surface"
                        variant="outlined"
                        size="small"
                        disabled={blocked}
                        onClick={() => setViewStep(0)}
                      >
                        {t(`${key}.test`)}
                      </Button>
                    )}
                    {selected.enabled && (
                      <Button
                        color="on-surface"
                        variant="outlined"
                        size="small"
                        disabled={blocked}
                        onClick={() => setPending({ row: selected, action: "disable" })}
                      >
                        {t(`${key}.disable`)}
                      </Button>
                    )}
                    {offer && offer.default_on && (
                      <Button
                        color="on-surface"
                        variant="outlined"
                        size="small"
                        disabled={blocked || inventory.isFetching}
                        onClick={() => setPending({ row: selected, action: "revoke" })}
                      >
                        {t(`${key}.revoke`)}
                      </Button>
                    )}
                  </div>
                </div>
              </details>
            </div>
          ) : (
            <p role="status">{query.isFetching ? t("common.loading") : t(`${key}.connectionUnavailable`)}</p>
          )}
        </InlineDrawer>
      )}
      <ConfirmationDialog
        open={pending !== null}
        title={t(`${key}.${pending?.action ?? "revoke"}Title`, { name: pending?.row.display_name })}
        message={t(`${key}.${pending?.action ?? "revoke"}Hint`)}
        details={pending && <p>{t(`${key}.impact`, { count: pending.row.affected_instance_count })}</p>}
        criticalAction
        confirmLabel={t(`${key}.${pending?.action ?? "revoke"}`)}
        cancelLabel={t("common.cancel")}
        confirmDisabled={blocked || inventory.isFetching}
        onCancel={() => setPending(null)}
        onConfirm={() => {
          if (pending)
            void run(() => (pending.action === "revoke" ? permit(pending.row, false) : activate(pending.row, false)));
          setPending(null);
        }}
      />
      {access.offered && editing !== undefined && (
        <ConnectionForm
          spaceId={spaceId}
          connection={editing}
          canSave={access.allowed}
          onClose={() => setEditing(undefined)}
          onSaved={(connection) => {
            setSelectedId(connection.id);
            setViewStep(undefined);
            setEditing(undefined);
          }}
        />
      )}
    </div>
  );
}
