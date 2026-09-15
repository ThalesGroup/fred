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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { useTranslation } from "react-i18next";
import { fileIconSpec } from "../../../../utils/fileIconSpec.ts";
import { DocumentMetadata } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { documentDisplayName, embeddedTitle } from "./documentNaming.ts";
import styles from "./DocumentNameCell.module.css";

export interface DocumentNameCellProps {
  doc: DocumentMetadata;
}

/** How a document is named wherever one is listed.
 *
 * One component so a document reads the same in a team's resources and in the
 * library a Knowledge Base fills: same icon for a kind of file, same truncation,
 * same hint when the file's own metadata claims a different title.
 */
export default function DocumentNameCell({ doc }: DocumentNameCellProps) {
  const { t } = useTranslation();
  const spec = fileIconSpec(doc.file?.file_type);
  const title = embeddedTitle(doc);

  return (
    <span className={styles.nameCell}>
      <span className={styles.rowIcon} style={{ color: spec.color }}>
        <Icon category="outlined" type={spec.type} filled={spec.filled} />
      </span>
      <span>{documentDisplayName(doc)}</span>
      {title && (
        <span className={styles.titleHintWrapper}>
          <Tooltip text={t("rework.resources.embeddedTitleHint", { title })}>
            <span
              className={styles.titleHintIcon}
              tabIndex={0}
              aria-label={t("rework.resources.embeddedTitleHint", { title })}
            >
              <Icon category="outlined" type="info" />
            </span>
          </Tooltip>
        </span>
      )}
    </span>
  );
}
