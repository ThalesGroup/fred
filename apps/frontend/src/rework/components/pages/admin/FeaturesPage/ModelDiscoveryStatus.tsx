// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSetModelDiscoveryUrlMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  DiscoverySourceStatus,
  ModelDiscoveryStatus as Status,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./FeaturesPage.module.css";

function SourceUrlEditor({ source }: { source: DiscoverySourceStatus }) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [url, setUrl] = useState(source.override_url ?? source.yaml_url);
  const [setUrlMutation, { isLoading }] = useSetModelDiscoveryUrlMutation();

  useEffect(() => setUrl(source.override_url ?? source.yaml_url), [source.override_url, source.yaml_url]);

  const save = async (nextUrl: string | null) => {
    try {
      await setUrlMutation({ sourceId: source.source_id, setDiscoveryUrlRequest: { url: nextUrl } }).unwrap();
    } catch {
      showError({ summary: t("rework.admin.capabilities.discovery.saveError") });
    }
  };

  return (
    <div className={styles.discoverySource}>
      <strong>{source.source_id}</strong>
      <TextInput
        label={t("rework.admin.capabilities.discovery.url")}
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        disabled={isLoading}
      />
      <div className={styles.discoveryActions}>
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          disabled={isLoading || !url.trim()}
          onClick={() => void save(url.trim())}
        >
          {t("rework.admin.capabilities.discovery.save")}
        </Button>
        {source.override_url && (
          <Button color="on-surface" variant="text" size="small" disabled={isLoading} onClick={() => void save(null)}>
            {t("rework.admin.capabilities.discovery.reset")}
          </Button>
        )}
      </div>
      <span className={styles.status}>
        {t("rework.admin.capabilities.discovery.yamlUrl", { url: source.yaml_url })}
      </span>
      {source.last_success_at && (
        <span className={styles.status}>
          {t("rework.admin.capabilities.discovery.lastSuccess", {
            time: new Date(source.last_success_at).toLocaleString(),
          })}
        </span>
      )}
      {source.last_error && <span className={styles.statusError}>{source.last_error}</span>}
    </div>
  );
}

export function ModelDiscoveryStatus({
  data,
  discoveredSourceIds,
  refreshing,
  refreshError,
  refresh,
}: {
  data: Status | undefined;
  discoveredSourceIds: string[];
  refreshing: boolean;
  refreshError: boolean;
  refresh: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const sources = data?.sources ?? [];
  const registeredSourceIds = new Set(sources.map((source) => source.source_id));
  const missingSourceIds = [...new Set(discoveredSourceIds)].filter((id) => !registeredSourceIds.has(id));
  const newCount = sources.reduce((count, source) => count + (source.new_ids?.length ?? 0), 0);
  const removed = sources.flatMap((source) => source.removed_models ?? []);

  return (
    <section className={styles.discoveryStatus} aria-label={t("rework.admin.capabilities.discovery.title")}>
      <div className={styles.discoveryHeading}>
        <strong>{t("rework.admin.capabilities.discovery.title")}</strong>
        <Button color="on-surface" variant="outlined" size="small" disabled={refreshing} onClick={() => void refresh()}>
          {t("rework.admin.capabilities.discovery.refresh")}
        </Button>
      </div>
      {refreshing && <p className={styles.status}>{t("rework.admin.capabilities.discovery.refreshing")}</p>}
      {(refreshError || data?.refresh_error) && (
        <p className={styles.statusError}>{t("rework.admin.capabilities.discovery.refreshFailed")}</p>
      )}
      {data && !refreshing && missingSourceIds.length > 0 && (
        <p className={styles.statusError}>
          {t("rework.admin.capabilities.discovery.unregisteredSource", { sources: missingSourceIds.join(", ") })}
        </p>
      )}
      {sources.length === 0 ? (
        data &&
        !refreshing &&
        missingSourceIds.length === 0 && (
          <p className={styles.status}>{t("rework.admin.capabilities.discovery.none")}</p>
        )
      ) : (
        <>
          <p className={styles.status}>
            {t("rework.admin.capabilities.discovery.summary", { added: newCount, removed: removed.length })}
          </p>
          {sources.map((source) => (
            <SourceUrlEditor key={source.source_id} source={source} />
          ))}
          {removed.length > 0 && (
            <div className={styles.discoveryRemoved}>
              <strong>{t("rework.admin.capabilities.discovery.unavailable")}</strong>
              <ul>
                {removed.map((model) => (
                  <li key={model.id}>
                    {model.display_name ?? model.name} ({model.name})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      <p className={styles.status}>{t("rework.admin.capabilities.discovery.formatLimit")}</p>
    </section>
  );
}
