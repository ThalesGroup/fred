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

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { MaterialIcon } from "../../../atoms/Icon/Icon";
import type { DocumentTreeTrace, TreeDocument } from "../../../../../utils/documentTreeTrace";
import styles from "./DocumentTreeDetail.module.css";

export function DocumentTreeDetail({ data }: { data: DocumentTreeTrace }) {
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState<string | null>(null);
  const id = useId();
  const locale = i18n.language;
  const dateFormat = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const unknown = t("rework.chatTrace.documentTree.unknown");
  const label = (name: string) => t(`rework.chatTrace.documentTree.${name}`);
  const fullDate = (value: string | null) => (value ? value.replace("T", " ").replace("+00:00", " UTC") : unknown);

  function metadata(document: TreeDocument) {
    const fields: [string, string][] = [
      [label("addedToKb"), fullDate(document.addedToKb)],
      [label("created"), fullDate(document.created)],
      [label("modified"), fullDate(document.modified)],
    ];
    if (document.title && document.title !== document.name) fields.unshift([label("title"), document.title]);
    if (document.legacyUploaded)
      fields.unshift([
        label("legacyUploaded"),
        document.legacyUploaded === "unknown date" ? unknown : document.legacyUploaded,
      ]);
    if (document.format) fields.push([label("format"), document.format.toUpperCase()]);
    if (document.mimeType) fields.push([label("mimeType"), document.mimeType]);
    if (document.language) fields.push([label("language"), document.language]);
    if (document.pageCount !== undefined)
      fields.push([label("volume"), t("rework.chatTrace.documentTree.pages", { count: document.pageCount })]);
    if (document.rowCount !== undefined)
      fields.push([label("rowsLabel"), t("rework.chatTrace.documentTree.rows", { count: document.rowCount })]);
    if (document.source) fields.push([label("source"), document.source]);
    return fields;
  }

  return (
    <div className={styles.detail}>
      <p className={styles.count}>{t("rework.chatTrace.documentTree.displayed", { count: data.documentCount })}</p>
      {data.truncated && <p className={styles.warning}>{label("incomplete")}</p>}
      {data.documentCount === 0 && data.folders.length === 0 && <p className={styles.empty}>{label("empty")}</p>}
      {data.folders.map((folder, folderIndex) => (
        <details className={styles.folder} key={folder.path} open>
          <summary className={styles.folderSummary}>
            <span className={styles.folderChevron}>
              <MaterialIcon type="chevron_right" />
            </span>
            <MaterialIcon type="folder" />
            <span>{folder.path || label("root")}</span>
          </summary>
          <div className={styles.documents}>
            {folder.documents.map((document, documentIndex) => {
              const key = `${folderIndex}-${documentIndex}`;
              const panelId = `${id}-${key}`;
              const isExpanded = expanded === key;
              const arrival = document.addedToKb ? dateFormat.format(new Date(document.addedToKb)) : unknown;
              return (
                <details className={styles.document} key={document.uid} open={isExpanded}>
                  <summary
                    className={styles.documentSummary}
                    aria-expanded={isExpanded}
                    aria-controls={panelId}
                    onClick={(event) => {
                      event.preventDefault();
                      setExpanded((current) => (current === key ? null : key));
                    }}
                  >
                    <span className={styles.chevron}>
                      <MaterialIcon type={isExpanded ? "expand_more" : "chevron_right"} />
                    </span>
                    <span className={styles.documentHeader}>
                      <span className={styles.nameRow}>
                        <span className={styles.name}>{document.name}</span>
                        {document.format && <span className={styles.format}>{document.format.toUpperCase()}</span>}
                        {document.uid === data.latestUid && (
                          <span className={styles.latest}>{label("latestDisplayed")}</span>
                        )}
                      </span>
                      <span className={styles.date}>
                        {document.legacyUploaded
                          ? t("rework.chatTrace.documentTree.legacyDate", {
                              date: document.legacyUploaded === "unknown date" ? unknown : document.legacyUploaded,
                            })
                          : t("rework.chatTrace.documentTree.arrival", { date: arrival })}
                      </span>
                    </span>
                  </summary>
                  {isExpanded && (
                    <dl className={styles.metadata} id={panelId}>
                      {metadata(document).map(([name, value]) => (
                        <div className={styles.field} key={name}>
                          <dt>{name}</dt>
                          <dd>{value}</dd>
                        </div>
                      ))}
                      {document.labels.length > 0 && (
                        <div className={styles.field}>
                          <dt>{label("labels")}</dt>
                          <dd className={styles.labels}>
                            {document.labels.map((value, index) => (
                              <span className={styles.label} key={index}>
                                {value}
                              </span>
                            ))}
                          </dd>
                        </div>
                      )}
                    </dl>
                  )}
                </details>
              );
            })}
          </div>
        </details>
      ))}
    </div>
  );
}
