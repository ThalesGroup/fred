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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Box,
  Breadcrumbs,
  CircularProgress,
  IconButton,
  Link,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useDeleteFileMutation, useLsQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

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
 * Adding files/folders is the root's "+" control (FsRootAddMenu), so this body has no
 * toolbar and never repeats the root name. An empty area shows nothing.
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
    <Box sx={{ display: "flex", flexDirection: "column" }}>
      {segments.length > 0 && (
        <Breadcrumbs aria-label="breadcrumb" sx={{ fontSize: "11px", pb: 0.5 }}>
          <Link component="button" type="button" underline="hover" color="inherit" onClick={() => setSegments([])}>
            <Icon category="outlined" type="home" />
          </Link>
          {segments.map((segment, index) => (
            <Link
              key={`${segment}-${index}`}
              component="button"
              type="button"
              underline="hover"
              color={index === segments.length - 1 ? "text.primary" : "inherit"}
              onClick={() => setSegments(segments.slice(0, index + 1))}
            >
              {segment}
            </Link>
          ))}
        </Breadcrumbs>
      )}

      {isFetching ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 1 }}>
          <CircularProgress size={18} />
        </Box>
      ) : (
        <List dense disablePadding>
          {sorted.map((entry) => {
            const directory = isDirectory(entry.type);
            return (
              <ListItem
                key={entry.path}
                disablePadding
                secondaryAction={
                  <IconButton
                    edge="end"
                    size="small"
                    disabled={isDeleting}
                    aria-label={t("rework.resources.action.delete")}
                    onClick={() => void handleDelete(entry.path)}
                  >
                    <Icon category="outlined" type="delete" />
                  </IconButton>
                }
              >
                <ListItemButton
                  disabled={!directory}
                  onClick={() => directory && setSegments([...segments, entry.path])}
                >
                  <ListItemIcon sx={{ minWidth: 32 }}>
                    <Icon category="outlined" type={directory ? "folder" : "description"} />
                  </ListItemIcon>
                  <ListItemText primary={entry.path} />
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      )}
    </Box>
  );
}
