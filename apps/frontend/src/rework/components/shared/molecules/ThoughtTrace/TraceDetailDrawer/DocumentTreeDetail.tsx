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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties";
import { MaterialIcon } from "../../../atoms/Icon/Icon";
import { Tooltip } from "../../../atoms/Tooltip/Tooltip";
import type { DocumentTreeTrace, TreeDocument, TreeFolder } from "../../../../../utils/documentTreeTrace";
import styles from "./DocumentTreeDetail.module.css";

interface FolderNode {
  name: string;
  path: string;
  children: Map<string, FolderNode>;
  documents: TreeDocument[];
}

function folderTree(folders: TreeFolder[]): FolderNode {
  const root: FolderNode = { name: "", path: "", children: new Map(), documents: [] };
  for (const folder of folders) {
    let node = root;
    for (const name of folder.path.split("/").filter(Boolean)) {
      if (!node.children.has(name))
        node.children.set(name, {
          name,
          path: node.path ? `${node.path}/${name}` : name,
          children: new Map(),
          documents: [],
        });
      node = node.children.get(name)!;
    }
    node.documents.push(...folder.documents);
  }
  return root;
}

export function DocumentTreeDetail({ data }: { data: DocumentTreeTrace }) {
  const { t } = useTranslation();
  const { siteDisplayName } = useFrontendProperties();
  const tree = useMemo(() => folderTree(data.folders), [data.folders]);
  const unknown = t("rework.chatTrace.documentTree.unknown");
  const label = (name: string) => t(`rework.chatTrace.documentTree.${name}`);
  const fullDate = (value: string | null) =>
    value ? value.replace("T", " ").replace(/(?:\+00:00|Z)$/, " UTC") : unknown;

  function metadata(document: TreeDocument) {
    const fields: [string, string][] = [
      [t("rework.chatTrace.documentTree.addedToKb", { siteDisplayName }), fullDate(document.addedToKb)],
    ];
    if (document.title && document.title !== document.name) fields.unshift([label("title"), document.title]);
    if (document.legacyUploaded)
      fields.unshift([
        label("legacyUploaded"),
        document.legacyUploaded === "unknown date" ? unknown : document.legacyUploaded,
      ]);
    if (document.mimeType) fields.push([label("mimeType"), document.mimeType]);
    if (document.language) fields.push([label("language"), document.language]);
    if (document.pageCount !== undefined)
      fields.push([label("volume"), t("rework.chatTrace.documentTree.pages", { count: document.pageCount })]);
    if (document.rowCount !== undefined)
      fields.push([label("rowsLabel"), t("rework.chatTrace.documentTree.rows", { count: document.rowCount })]);
    if (document.source) fields.push([label("source"), document.source]);
    return fields;
  }

  function documents(items: TreeDocument[]) {
    return items.map((document) => (
      <li className={styles.documentRow} key={document.uid}>
        <Tooltip
          interactive
          placement="left"
          content={
            <div className={styles.metadataPanel}>
              <p className={styles.metadataTitle}>{document.name}</p>
              {document.uid === data.latestUid && <p className={styles.latest}>{label("latestDisplayed")}</p>}
              <dl className={styles.metadata}>
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
            </div>
          }
        >
          <button
            type="button"
            className={styles.document}
            aria-label={t("rework.chatTrace.documentTree.metadataFor", { name: document.name })}
          >
            <span className={styles.fileIcon}>
              <MaterialIcon type="draft" />
            </span>
            <span className={styles.name}>{document.name}</span>
          </button>
        </Tooltip>
      </li>
    ));
  }

  function folder(node: FolderNode) {
    return (
      <li className={styles.folder} key={node.path}>
        <details open>
          <summary className={styles.folderSummary}>
            <span className={styles.folderChevron}>
              <MaterialIcon type="chevron_right" />
            </span>
            <MaterialIcon type="folder" />
            <span className={styles.folderName}>{node.name}</span>
          </summary>
          <ul className={styles.branch}>
            {Array.from(node.children.values(), folder)}
            {documents(node.documents)}
          </ul>
        </details>
      </li>
    );
  }

  return (
    <div className={styles.detail}>
      <p className={styles.count}>{t("rework.chatTrace.documentTree.displayed", { count: data.documentCount })}</p>
      {data.documentCount === 0 && data.folders.length === 0 && <p className={styles.empty}>{label("empty")}</p>}
      <ul className={styles.tree}>
        {Array.from(tree.children.values(), folder)}
        {documents(tree.documents)}
      </ul>
      {data.truncated && <p className={styles.truncated}>{label("truncated")}</p>}
    </div>
  );
}
