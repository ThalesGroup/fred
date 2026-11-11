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
  onClose,
}: {
  spaceId: string;
  connection: McpConnectionView | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [logicalName, setLogicalName] = useState(connection?.logical_name ?? "");
  const [name, setName] = useState(connection?.display_name ?? "");
  const [description, setDescription] = useState(connection?.description ?? "");
  const [url, setUrl] = useState(connection?.configuration.url ?? "");
  const [allowHttp, setAllowHttp] = useState(connection?.configuration.allow_insecure_http ?? false);
  const initialAuth = connection?.configuration.authentication;
  const [auth, setAuth] = useState<"none" | "bearer" | "api_key" | "knowledge_flow_tabular">(
    initialAuth?.kind ?? "none",
  );
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
    name.trim() &&
    (auth === "knowledge_flow_tabular" || url.trim()) &&
    (connection || /^[a-z0-9_-]{1,64}$/.test(logicalName)) &&
    (auth === "none" ||
      auth === "knowledge_flow_tabular" ||
      credentials.currentData?.some((c) => c.available && c.url === url && c.credential_binding === credential));
  const save = async () => {
    if (!ready || busy) return;
    const configuration: McpConfiguration = {
      url: auth === "knowledge_flow_tabular" ? "" : url,
      allow_insecure_http:
        auth === "knowledge_flow_tabular"
          ? initialAuth?.kind === "knowledge_flow_tabular"
            ? connection!.configuration.allow_insecure_http
            : false
          : allowHttp,
      authentication:
        auth === "none" || auth === "knowledge_flow_tabular"
          ? { kind: auth }
          : auth === "bearer"
            ? { kind: "bearer", credential_binding: credential }
            : { kind: "api_key", credential_binding: credential, header },
    };
    try {
      if (connection)
        await update({
          spaceId,
          id: connection.id,
          updateMcpConnection: {
            expected_revision: connection.revision,
            display_name: name,
            description,
            configuration,
            enabled: connection.enabled,
          },
        }).unwrap();
      else
        await create({
          spaceId,
          createMcpConnection: { logical_name: logicalName, display_name: name, description, configuration },
        }).unwrap();
      onClose();
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
        {auth !== "knowledge_flow_tabular" && (
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
        )}
        {auth === "knowledge_flow_tabular" && <p>{t(`${key}.trustedService`)}</p>}
        <Select
          size="small"
          label={t(`${key}.authentication`)}
          value={auth}
          onChange={setAuth}
          options={(["none", "bearer", "api_key", "knowledge_flow_tabular"] as const).map((kind) => ({
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
  const [pending, setPending] = useState<{ row: McpConnectionView; action: "revoke" | "disable" } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [test] = useTestMcpConnectionMutation();
  const [publish] = usePublishMcpConnectionMutation();
  const [update] = useUpdateMcpConnectionMutation();
  const rows = access.allowed && !query.isError ? (query.currentData ?? []) : [];
  const selected = rows.find((row) => row.id === selectedId);
  const changes = selected?.tool_changes;
  const hasChanges = changes && !!(changes.added.length + changes.modified.length + changes.removed.length);
  const toolRows = selected
    ? changes
      ? [...selected.observed_tools, ...selected.published_tools.filter((tool) => changes.removed.includes(tool.name))]
      : selected.published_tools
    : [];
  const run = async (action: () => Promise<unknown>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(t(`${key}.${normalizeApiError(e).status === 409 ? "conflict" : "error"}`));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const permit = (row: McpConnectionView, default_on: boolean) => {
    if (!source || inventory.isError) return;
    return run(() =>
      setPermission({
        organizationId: spaceId,
        sourceId: source.source_id,
        capabilityId: row.capability_id,
        setDefaultOnRequest: { default_on },
      }).unwrap(),
    );
  };
  const activate = (row: McpConnectionView, enabled: boolean) =>
    run(() =>
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
      }).unwrap(),
    );
  const permissionControl = (row: McpConnectionView) => {
    const offer = !inventory.isError && source?.capabilities.find((item) => item.capability_id === row.capability_id);
    if (!offer) return <span>{t(`${key}.permissionUnknown`)}</span>;
    const blocked = !offer.default_on && !offer.advertised;
    const control = (
      <Switch
        size="small"
        checked={offer.default_on}
        disabled={busy || query.isFetching || inventory.isFetching || blocked}
        aria-label={t(`${key}.allowNamed`, { name: row.display_name })}
        onChange={() => (offer.default_on ? setPending({ row, action: "revoke" }) : void permit(row, true))}
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
      {access.allowed && rows.length > 0 && (
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
                  onClick={() => setSelectedId(row.id)}
                  aria-label={t(`${key}.detailsNamed`, { name: row.display_name })}
                >
                  {t(`${key}.details`)}
                </Button>
              ),
            },
          ]}
        />
      )}
      {access.allowed && selectedId && (
        <InlineDrawer
          open
          width="var(--content-prose-max-width)"
          onClose={() => {
            if (editing === undefined && !pending) setSelectedId(null);
          }}
          title={selected?.display_name ?? t(`${key}.connectionUnavailable`)}
          closeLabel={t("common.close")}
        >
          {selected ? (
            <div className={styles.detail}>
              <p>{selected.logical_name}</p>
              <p>{selected.description}</p>
              {error && <p role="alert">{error}</p>}
              <div className={styles.actions}>
                <Button
                  color="primary"
                  variant="outlined"
                  size="small"
                  disabled={busy}
                  onClick={() => setEditing(selected)}
                >
                  {t(`${key}.edit`)}
                </Button>
                <Button
                  color="primary"
                  variant="outlined"
                  size="small"
                  disabled={busy || query.isFetching}
                  onClick={() =>
                    void run(() =>
                      test({
                        spaceId,
                        id: selected.id,
                        mcpRevision: { expected_revision: selected.revision },
                      }).unwrap(),
                    )
                  }
                >
                  {t(`${key}.test`)}
                </Button>
              </div>
              <h3>{t(`${key}.observation`)}</h3>
              <div className={styles.actions}>
                <StatusBadge
                  label={t(`${key}.state.${selected.observation_state}`)}
                  tone={selected.observation_state === "unavailable" ? "error" : "neutral"}
                />
              </div>
              <p>{t(`${key}.checkedAt`, { date: formatDateTime(selected.checked_at) })}</p>
              <p>{t(`${key}.discoveryScope`)}</p>
              {selected.observation_state === "unavailable" && <p role="alert">{t(`${key}.discoveryFailed`)}</p>}
              <h3>{t(`${key}.inventory`)}</h3>
              {!changes ? (
                <p role="status">{t(`${key}.previousInventory`)}</p>
              ) : selected.published_revision !== null && !hasChanges ? (
                <p role="status">
                  {t(`${key}.${selected.published_revision === selected.revision ? "upToDate" : "validationRequired"}`)}
                </p>
              ) : (
                <p role="status">
                  {t(`${key}.changes`, {
                    added: changes.added.length,
                    modified: changes.modified.length,
                    removed: changes.removed.length,
                  })}
                </p>
              )}
              <DataTable
                data={toolRows}
                rowKey={(tool) => tool.name}
                size="small"
                columns={[
                  { label: t(`${key}.tool`), size: "1.5fr", cellRenderer: (tool) => tool.name },
                  {
                    label: t(`${key}.description`),
                    size: "3fr",
                    cellRenderer: (tool) => <span className={styles.toolDescription}>{tool.description}</span>,
                  },
                  ...(hasChanges
                    ? [
                        {
                          label: t(`${key}.change`),
                          size: "1.3fr",
                          cellRenderer: (tool: McpConnectionView["observed_tools"][number]) => {
                            const change = changes.removed.includes(tool.name)
                              ? "removed"
                              : changes.modified.includes(tool.name)
                                ? "modified"
                                : changes.added.includes(tool.name)
                                  ? "added"
                                  : null;
                            return change ? (
                              <StatusBadge
                                label={t(`${key}.${change}`)}
                                tone={change === "removed" ? "warning" : "info"}
                              />
                            ) : null;
                          },
                        },
                      ]
                    : []),
                ]}
              />
              {!toolRows.length && <p>{t(`${key}.noTools`)}</p>}
              <details>
                <summary>{t(`${key}.contracts`)}</summary>
                <pre className={styles.contracts}>
                  {JSON.stringify({ observed: selected.observed_tools, published: selected.published_tools }, null, 2)}
                </pre>
              </details>
              <p>{t(`${key}.publicationHint`)}</p>
              <Button
                color="primary"
                variant="filled"
                size="small"
                disabled={
                  busy ||
                  query.isFetching ||
                  !changes ||
                  !selected.observed_tools.length ||
                  !selected.checked_at ||
                  (!hasChanges && selected.published_revision === selected.revision)
                }
                onClick={() =>
                  void run(() =>
                    publish({
                      spaceId,
                      id: selected.id,
                      mcpPublication: {
                        expected_revision: selected.revision,
                        expected_checked_at: selected.checked_at!,
                      },
                    }).unwrap(),
                  )
                }
              >
                {t(`${key}.${selected.published_revision === null ? "publish" : "applyChanges"}`)}
              </Button>
              <h3>{t(`${key}.permission`)}</h3>
              {permissionControl(selected)}
              <p>{t(`${key}.permissionHint`)}</p>
              <h3>{t(`${key}.activation`)}</h3>
              <p>{t(`${key}.${selected.enabled ? "enabled" : "disabled"}`)}</p>
              <p>{t(`${key}.activationHint`)}</p>
              <Button
                color="on-surface"
                variant="outlined"
                size="small"
                disabled={busy || query.isFetching}
                onClick={() =>
                  selected.enabled ? setPending({ row: selected, action: "disable" }) : void activate(selected, true)
                }
              >
                {t(`${key}.${selected.enabled ? "disable" : "enable"}`)}
              </Button>
              <p>{t(`${key}.impact`, { count: selected.affected_instance_count })}</p>
            </div>
          ) : (
            <p role="status">{t(`${key}.connectionUnavailable`)}</p>
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
        confirmDisabled={busy}
        onCancel={() => setPending(null)}
        onConfirm={() => {
          if (pending) void (pending.action === "revoke" ? permit(pending.row, false) : activate(pending.row, false));
          setPending(null);
        }}
      />
      {access.allowed && editing !== undefined && (
        <ConnectionForm spaceId={spaceId} connection={editing} onClose={() => setEditing(undefined)} />
      )}
    </div>
  );
}
