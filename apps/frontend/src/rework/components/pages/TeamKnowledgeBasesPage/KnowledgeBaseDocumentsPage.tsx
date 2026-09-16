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
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useKnowledgeBaseQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import DocumentWorkspace from "../TeamResourcesPage/DocumentWorkspace/DocumentWorkspace.tsx";
import styles from "./KnowledgeBaseDocumentsPage.module.css";

/** What one Knowledge Base has put in its library, and nothing else.
 *
 * This is the Resources explorer, rooted at the library and offering no way to
 * write — deliberately the same component rather than a second table that
 * happens to look like it. A library mirrors the shape of the source it
 * follows, so it is browsed as a tree, folder by folder, exactly as a corpus
 * folder is.
 *
 * Read only by design, not by omission: these documents belong to a source the
 * base mirrors, so removing one here would only last until the next run. The
 * way to stop taking them is to delete the base, from the list this page came
 * from.
 */
export default function KnowledgeBaseDocumentsPage() {
  const { teamId, instanceId } = useParams<{ teamId: string; instanceId: string }>();
  const { t } = useTranslation();

  const {
    data: instance,
    isLoading: isLoadingInstance,
    isError: instanceError,
  } = useKnowledgeBaseQuery({ instanceId: instanceId ?? "" }, { skip: !instanceId });

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Link to={`/team/${teamId}/knowledge-bases`} className={styles.back}>
          <Button
            color="on-surface-retreat"
            variant="text"
            size="medium"
            icon={{ category: "outlined", type: "arrow_back" }}
          >
            {t("rework.knowledgeBases.documents.back")}
          </Button>
        </Link>
        <span className={styles.title}>{instance?.library_name ?? ""}</span>
        {instance && <span className={styles.kind}>{instance.definition_name}</span>}
      </div>

      {isLoadingInstance ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
        </div>
      ) : instanceError || !instance ? (
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.knowledgeBases.documents.unavailable.title")}
          description={t("rework.knowledgeBases.documents.unavailable.description")}
          centered
        />
      ) : (
        <DocumentWorkspace
          teamId={teamId ?? ""}
          // A Knowledge Base is always a team's: an instance is created from a
          // team's screen and its library is owned by that team.
          isPersonalTeam={false}
          rootTagId={instance.library_id}
          readOnly
        />
      )}
    </div>
  );
}
