// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import Select from "@shared/molecules/Select/Select";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import {
  useMcpConnectionsQuery,
  useMcpCredentialsQuery,
  useCreateMcpConnectionMutation,
  useUpdateMcpConnectionMutation,
  useTestMcpConnectionMutation,
  usePublishMcpConnectionMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { McpConnectionView, McpConfiguration } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./McpConnectionsPage.module.css";

const key = "rework.mcp";

function ConnectionForm({ connection, onClose }: { connection: McpConnectionView | null; onClose: () => void }) {
  const { t } = useTranslation();
  const [logicalName, setLogicalName] = useState(connection?.logical_name ?? "");
  const [name, setName] = useState(connection?.display_name ?? "");
  const [description, setDescription] = useState(connection?.description ?? "");
  const [url, setUrl] = useState(connection?.configuration.url ?? "");
  const [allowHttp, setAllowHttp] = useState(connection?.configuration.allow_insecure_http ?? false);
  const initialAuth = connection?.configuration.authentication;
  const [auth, setAuth] = useState<"none" | "bearer" | "api_key">(initialAuth?.kind ?? "none");
  const [credential, setCredential] = useState(
    initialAuth && initialAuth.kind !== "none" ? initialAuth.credential_binding : "",
  );
  const [header, setHeader] = useState(initialAuth?.kind === "api_key" ? initialAuth.header : "x-api-key");
  const [error, setError] = useState("");
  const credentials = useMcpCredentialsQuery(undefined, { refetchOnMountOrArgChange: true });
  const [create, creating] = useCreateMcpConnectionMutation();
  const [update, updating] = useUpdateMcpConnectionMutation();
  const busy = creating.isLoading || updating.isLoading;
  const ready =
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
          ? { kind: "none" }
          : auth === "bearer"
            ? { kind: "bearer", credential_binding: credential }
            : { kind: "api_key", credential_binding: credential, header },
    };
    try {
      if (connection)
        await update({
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
          createMcpConnection: { logical_name: logicalName, display_name: name, description, configuration },
        }).unwrap();
      onClose();
    } catch (e) {
      setError(normalizeApiError(e).detail ?? t(`${key}.error`));
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
        <TextInput
          size="small"
          label={t(`${key}.description`)}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={2000}
        />
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
        {auth !== "none" && (
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

export default function McpConnectionsPage() {
  const { t } = useTranslation();
  const access = useManagerPlatformAdmin(false, true);
  const query = useMcpConnectionsQuery(undefined, { skip: !access.isAdmin, refetchOnMountOrArgChange: true });
  const [editing, setEditing] = useState<McpConnectionView | null | undefined>();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [test] = useTestMcpConnectionMutation();
  const [publish] = usePublishMcpConnectionMutation();
  const [update] = useUpdateMcpConnectionMutation();
  const rows = access.isAdmin && !query.isError ? (query.currentData ?? []) : [];
  const selected = rows.find((row) => row.id === selectedId);
  const run = async (action: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(normalizeApiError(e).detail ?? t(`${key}.error`));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={styles.page}>
      <PageHeader
        title={t(`${key}.title`)}
        subtitle={t(`${key}.scope`)}
        actions={
          access.isAdmin && (
            <Button color="primary" variant="filled" size="medium" onClick={() => setEditing(null)}>
              {t(`${key}.add`)}
            </Button>
          )
        }
      />
      {(access.isError || query.isError || error) && <p role="alert">{error || t(`${key}.error`)}</p>}
      {!access.isLoading && !access.isAdmin && <p role="alert">{t("rework.spaceMembers.forbidden")}</p>}
      {access.isAdmin && (
        <>
          <DataTable
            data={rows}
            rowKey={(row) => row.id}
            onRowClick={(row) => setSelectedId(row.id)}
            size="medium"
            columns={[
              { label: t(`${key}.name`), cellRenderer: (row) => row.display_name },
              {
                label: t(`${key}.activation`),
                cellRenderer: (row) => t(`${key}.${row.enabled ? "enabled" : "disabled"}`),
              },
              {
                label: t(`${key}.observation`),
                cellRenderer: (row) => (
                  <StatusBadge
                    label={t(`${key}.state.${row.observation_state}`)}
                    tone={row.observation_state === "available" ? "success" : "neutral"}
                  />
                ),
              },
              {
                label: t(`${key}.execution`),
                cellRenderer: (row) => t(`${key}.${row.available ? "available" : "unavailable"}`),
              },
            ]}
          />
          {selected && (
            <section className={styles.detail}>
              <h2>{selected.display_name}</h2>
              <p>{selected.description}</p>
              <p>{t(`${key}.revision`, { revision: selected.revision })}</p>
              <p>{t(`${key}.discoveryScope`)}</p>
              {selected.error_code && <p role="status">{t(`${key}.diagnostic`, { code: selected.error_code })}</p>}
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
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      test({ id: selected.id, mcpRevision: { expected_revision: selected.revision } }).unwrap(),
                    )
                  }
                >
                  {t(`${key}.test`)}
                </Button>
                <Button
                  color="primary"
                  variant="outlined"
                  size="small"
                  disabled={
                    busy ||
                    selected.observation_state !== "available" ||
                    selected.observation_revision !== selected.revision ||
                    !selected.observed_tools.length ||
                    !selected.checked_at
                  }
                  onClick={() =>
                    void run(() =>
                      publish({
                        id: selected.id,
                        mcpPublication: {
                          expected_revision: selected.revision,
                          expected_checked_at: selected.checked_at!,
                        },
                      }).unwrap(),
                    )
                  }
                >
                  {t(`${key}.publish`)}
                </Button>
                <Button
                  color="primary"
                  variant="outlined"
                  size="small"
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      update({
                        id: selected.id,
                        updateMcpConnection: {
                          expected_revision: selected.revision,
                          display_name: selected.display_name,
                          description: selected.description,
                          configuration: selected.configuration,
                          enabled: !selected.enabled,
                        },
                      }).unwrap(),
                    )
                  }
                >
                  {t(`${key}.${selected.enabled ? "disable" : "enable"}`)}
                </Button>
              </div>
              <p>{t(`${key}.publicationHint`)}</p>
              <DataTable
                data={selected.observed_tools}
                rowKey={(tool) => tool.name}
                size="small"
                columns={[
                  { label: t(`${key}.tool`), cellRenderer: (tool) => tool.name },
                  { label: t(`${key}.description`), cellRenderer: (tool) => tool.description },
                  {
                    label: t(`${key}.publication`),
                    cellRenderer: (tool) =>
                      t(
                        `${key}.${selected.published_tools.some((p) => p.name === tool.name) ? "published" : "unpublished"}`,
                      ),
                  },
                ]}
              />
              <details>
                <summary>{t(`${key}.contracts`)}</summary>
                <pre className={styles.contracts}>
                  {JSON.stringify({ observed: selected.observed_tools, published: selected.published_tools }, null, 2)}
                </pre>
              </details>
              <p>{t(`${key}.impact`, { count: selected.affected_instance_count })}</p>
            </section>
          )}
          {editing !== undefined && <ConnectionForm connection={editing} onClose={() => setEditing(undefined)} />}
        </>
      )}
    </div>
  );
}
