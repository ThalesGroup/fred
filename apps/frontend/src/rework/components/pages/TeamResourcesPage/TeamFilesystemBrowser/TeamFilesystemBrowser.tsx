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

import { Fragment, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton.tsx";
import { useDeleteFileMutation, useLsQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./TeamFilesystemBrowser.module.css";

/** One entry returned by the /fs/list endpoint (path is the direct child name). */
interface FsEntry {
  path: string;
  size?: number | null;
  type?: string;
  modified?: string | null;
}

function isDirectory(type: string | undefined): boolean {
  return typeof type === "string" && type.toLowerCase().includes("directory");
}

interface TeamFilesystemBrowserProps {
  /** Team-rooted base path for this area, e.g. `teams/{team}/shared` or `teams/{team}/users/{uid}`. */
  root: string;
}

/**
 * Browse one team-rooted filesystem area (FILES-04): list, navigate sub-folders, delete.
 *
 * Native + design-system only (no MUI), to match the rest of rework. Adding files/folders is
 * the root's "+" control (FsRootAddMenu), so this body has no toolbar and never repeats the
 * root name. An empty area shows nothing.
 */
export default function TeamFilesystemBrowser({ root }: TeamFilesystemBrowserProps) {
  const { t } = useTranslation();
  const [segments, setSegments] = useState<string[]>([]);

  const fullPath = useMemo(() => [root, ...segments].join("/"), [root, segments]);
  const { data, isFetching } = useLsQuery({ path: fullPath });
  const [deleteFile, { isLoading: isDeleting }] = useDeleteFileMutation();

  const entries: FsEntry[] = Array.isArray(data) ? (data as FsEntry[]) : [];
  const sorted = [...entries].sort((a, b) => {
    const dirDelta = Number(isDirectory(b.type)) - Number(isDirectory(a.type));
    return dirDelta !== 0 ? dirDelta : a.path.localeCompare(b.path);
  });

  const handleDelete = async (name: string) => {
    await deleteFile({ path: `${fullPath}/${name}` }).unwrap();
  };

  return (
    <div className={styles.browser}>
      {segments.length > 0 && (
        <nav className={styles.breadcrumb} aria-label="breadcrumb">
          <button
            type="button"
            className={styles.crumb}
            onClick={() => setSegments([])}
            aria-label={t("rework.resources.roots.mine")}
          >
            <Icon category="outlined" type="home" />
          </button>
          {segments.map((segment, index) => (
            <Fragment key={`${segment}-${index}`}>
              <Icon category="outlined" type="chevron_right" />
              <button type="button" className={styles.crumb} onClick={() => setSegments(segments.slice(0, index + 1))}>
                {segment}
              </button>
            </Fragment>
          ))}
        </nav>
      )}

      {isFetching ? (
        <div className={styles.loading}>{t("rework.resources.loading")}</div>
      ) : (
        sorted.map((entry) => {
          const directory = isDirectory(entry.type);
          return (
            <div key={entry.path} className={`${styles.row} ${directory ? styles.folder : styles.file}`}>
              <button
                type="button"
                className={styles.entry}
                disabled={!directory}
                onClick={() => directory && setSegments([...segments, entry.path])}
              >
                <span className={styles.icon}>
                  <Icon category="outlined" type={directory ? "folder" : "description"} />
                </span>
                <span className={styles.name}>{entry.path}</span>
              </button>
              <DeleteIconButton size="small" disabled={isDeleting} onClick={() => void handleDelete(entry.path)} />
            </div>
          );
        })
      )}
    </div>
  );
}
