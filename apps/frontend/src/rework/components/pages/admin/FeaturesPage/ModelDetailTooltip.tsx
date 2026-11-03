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

import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { useTranslation } from "react-i18next";
import { useLazyModelDiscoveryDetailQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./FeaturesPage.module.css";

function DetailFields({ value }: { value: Record<string, unknown> }) {
  return (
    <dl className={styles.modelDetailFields}>
      {Object.entries(value).map(([key, field]) => (
        <div
          className={`${styles.modelDetailField} ${field !== null && typeof field === "object" ? styles.modelDetailGroup : ""}`}
          key={key}
        >
          <dt>{key}</dt>
          <dd>
            {field !== null && typeof field === "object" ? (
              <DetailFields
                value={
                  Array.isArray(field)
                    ? Object.fromEntries(field.map((item, index) => [index, item]))
                    : (field as Record<string, unknown>)
                }
              />
            ) : (
              String(field)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ModelDetailTooltip({
  sourceId,
  modelId,
  runtimeId,
}: {
  sourceId: string;
  modelId: string;
  runtimeId?: string;
}) {
  const { t } = useTranslation();
  const [loadDetail, { data, isFetching, isError }] = useLazyModelDiscoveryDetailQuery();
  const content = isFetching ? (
    t("rework.admin.capabilities.modelDetail.loading")
  ) : isError ? (
    t("rework.admin.capabilities.modelDetail.error")
  ) : data ? (
    <div className={styles.modelDetailPanel}>
      <DetailFields value={data} />
    </div>
  ) : (
    t("rework.admin.capabilities.modelDetail.openHint")
  );

  return (
    <span className={styles.modelDetailButton}>
      <Tooltip content={content} interactive>
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "info" }}
          type="button"
          aria-label={t("rework.admin.capabilities.modelDetail.openAria", { name: modelId })}
          onClick={() => void loadDetail({ sourceId, modelId, runtimeId })}
        />
      </Tooltip>
    </span>
  );
}
