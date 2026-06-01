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

import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useTranslation } from "react-i18next";
import { KnowledgeHub } from "../../../../pages/KnowledgeHub";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./KnowledgeHubPage.module.css";

/**
 * Shell for the knowledge hub that owns the KF health-check lifecycle.
 *
 * Three states — identical to TeamAgentsPage:
 *   1. isLoading  → centered loading text
 *   2. isError    → ServiceNotice centered (no header rendered)
 *   3. ok         → KnowledgeHub (tabs + content)
 *
 * RTK Query deduplicates the tag query so child components that run the same
 * query pay no extra network cost.
 */
export default function KnowledgeHubPage() {
  const { t } = useTranslation();

  const {
    isError: isKfDown,
    isLoading: isKfLoading,
    isFetching: isKfFetching,
    isUninitialized: isKfUninitialized,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document",
    limit: 1,
    offset: 0,
  });
  const kfQueryState = getQueryUiState({
    isLoading: isKfLoading,
    isFetching: isKfFetching,
    isUninitialized: isKfUninitialized,
    isError: isKfDown,
  });

  if (kfQueryState === "loading") {
    return <div className={styles.loadingState}>{t("rework.knowledgeHub.loading")}</div>;
  }

  if (kfQueryState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.knowledgeService.title")}
        description={t("rework.serviceNotice.knowledgeService.description")}
        centered
      />
    );
  }

  return <KnowledgeHub />;
}
