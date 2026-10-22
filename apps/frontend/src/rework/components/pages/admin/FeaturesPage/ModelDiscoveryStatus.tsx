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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useUserCapabilities } from "@rework/core/hooks/useUserCapabilities";
import { useSetModelDiscoveryUrlMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  DiscoverySourceStatus,
  ModelDiscoveryStatus as Status,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./FeaturesPage.module.css";

function SourceUrlEditor({ source }: { source: DiscoverySourceStatus }) {
  const { t } = useTranslation();
  const { canAdmin } = useUserCapabilities();
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
      <h3 className={styles.discoverySourceTitle}>{source.source_id}</h3>
      {canAdmin ? (
        <>
          <TextInput
            aria-label={t("rework.admin.capabilities.discovery.sourceUrlAria", { source: source.source_id })}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            disabled={isLoading}
            compact
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
            <Button
              color="on-surface"
              variant="text"
              size="small"
              disabled={isLoading || (!source.override_url && url === source.yaml_url)}
              onClick={() => {
                if (source.override_url) void save(null);
                else setUrl(source.yaml_url);
              }}
            >
              {t("rework.admin.capabilities.discovery.reset")}
            </Button>
          </div>
        </>
      ) : (
        <code className={styles.discoveryReadOnlyUrl}>{source.effective_url}</code>
      )}
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
  refreshErrorMessage,
  unverifiedRuntimes = [],
  verifiedSourceIds = [],
  refresh,
}: {
  data: Status | undefined;
  discoveredSourceIds: string[];
  refreshing: boolean;
  refreshError: boolean;
  refreshErrorMessage?: string | null;
  unverifiedRuntimes?: { runtime_id: string; base_url: string }[];
  verifiedSourceIds?: string[];
  refresh: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const sources = data?.sources ?? [];
  const registeredSourceIds = new Set(sources.map((source) => source.source_id));
  const missingSourceIds = [...new Set(discoveredSourceIds)].filter((id) => !registeredSourceIds.has(id));
  const visibleMissingSourceIds =
    unverifiedRuntimes.length > 0 ? missingSourceIds.filter((id) => verifiedSourceIds.includes(id)) : missingSourceIds;
  const failedSourceIds = sources.filter((source) => source.last_error).map((source) => source.source_id);
  const newCount = sources.reduce((count, source) => count + (source.new_ids?.length ?? 0), 0);
  const removed = sources.flatMap((source) =>
    (source.removed_models ?? []).map((model) => ({ ...model, discoverySourceId: source.source_id })),
  );

  return (
    <section className={styles.discoveryStatus} aria-label={t("rework.admin.capabilities.discovery.title")}>
      <div className={styles.discoveryHeading}>
        <span className={styles.status}>
          {sources.length > 0
            ? t("rework.admin.capabilities.discovery.summary", { added: newCount, removed: removed.length })
            : t("rework.admin.capabilities.discovery.title")}
        </span>
        <Button
          color="on-surface"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "refresh" }}
          disabled={refreshing}
          onClick={() => void refresh()}
        >
          {t("rework.admin.capabilities.discovery.refresh")}
        </Button>
      </div>
      {refreshing && <p className={styles.status}>{t("rework.admin.capabilities.discovery.refreshing")}</p>}
      {unverifiedRuntimes.length > 0 && (
        <p className={styles.statusWarning}>
          <Icon category="outlined" type="warning" />
          <span>
            {t("rework.admin.capabilities.discovery.unverifiedRuntimes")}{" "}
            {unverifiedRuntimes.map((runtime, index) => (
              <span key={`${runtime.runtime_id}:${runtime.base_url}`}>
                {index > 0 && ", "}
                <code>{runtime.runtime_id}</code> (<code>{runtime.base_url}</code>)
              </span>
            ))}
          </span>
        </p>
      )}
      {(refreshError || data?.refresh_error) && (
        <p className={styles.statusError}>
          {t("rework.admin.capabilities.discovery.refreshFailed")}
          {refreshErrorMessage && refreshErrorMessage !== t("rework.admin.capabilities.discovery.refreshFailed") && (
            <> {refreshErrorMessage}</>
          )}
        </p>
      )}
      {failedSourceIds.length > 0 && (
        <p className={styles.statusError}>
          {t("rework.admin.capabilities.discovery.failedSources", { sources: failedSourceIds.join(", ") })}
        </p>
      )}
      {data && !refreshing && !refreshError && visibleMissingSourceIds.length > 0 && (
        <p className={styles.statusError}>
          {t("rework.admin.capabilities.discovery.unregisteredSource", { sources: visibleMissingSourceIds.join(", ") })}
        </p>
      )}
      {sources.length === 0 ? (
        data &&
        !refreshing &&
        !refreshError &&
        unverifiedRuntimes.length === 0 &&
        visibleMissingSourceIds.length === 0 && (
          <p className={styles.status}>{t("rework.admin.capabilities.discovery.none")}</p>
        )
      ) : (
        <>
          <details className={styles.discoverySettings}>
            <summary className={styles.discoverySettingsToggle}>
              <span>{t("rework.admin.capabilities.discovery.advancedSettings")}</span>
              <span className={styles.discoverySettingsChevron}>
                <Icon category="outlined" type="expand_more" />
              </span>
            </summary>
            <div className={styles.discoverySettingsContent}>
              {sources.map((source) => (
                <SourceUrlEditor key={source.source_id} source={source} />
              ))}
            </div>
          </details>
          {removed.length > 0 && (
            <div className={styles.discoveryRemoved}>
              <strong>{t("rework.admin.capabilities.discovery.unavailable")}</strong>
              <ul>
                {removed.map((model) => (
                  <li key={`${model.discoverySourceId}:${model.id}`}>
                    {model.display_name ?? model.name} ({model.name}) - {model.discoverySourceId}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
