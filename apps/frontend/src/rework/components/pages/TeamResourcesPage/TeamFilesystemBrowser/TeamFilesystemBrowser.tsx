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

import { useMemo, useRef, useState } from "react";
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
  Typography,
} from "@mui/material";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import {
  useDeleteFileMutation,
  useLsQuery,
  useUploadFileMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

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
  /** Human label for the area root shown as the first breadcrumb. */
  rootLabel: string;
}

/**
 * Browse and upload files in one team-rooted filesystem area (FILES-04).
 *
 * Drives the unified `/fs` endpoints: list a folder, upload files, delete entries, and
 * navigate sub-folders. The team and user are part of the `root` path, so this component
 * never builds identity itself.
 */
export default function TeamFilesystemBrowser({ root, rootLabel }: TeamFilesystemBrowserProps) {
  const { t } = useTranslation();
  const [segments, setSegments] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fullPath = useMemo(() => [root, ...segments].join("/"), [root, segments]);
  const { data, isFetching, refetch } = useLsQuery({ path: fullPath });
  const [uploadFile, { isLoading: isUploading }] = useUploadFileMutation();
  const [deleteFile] = useDeleteFileMutation();

  const entries: FsEntry[] = Array.isArray(data) ? (data as FsEntry[]) : [];
  const sorted = [...entries].sort((a, b) => {
    const dirDelta = Number(isDirectory(b.type)) - Number(isDirectory(a.type));
    return dirDelta !== 0 ? dirDelta : a.path.localeCompare(b.path);
  });

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);
      await uploadFile({ path: `${fullPath}/${file.name}`, bodyUploadFile: formData as never }).unwrap();
    }
    refetch();
  };

  const handleDelete = async (name: string) => {
    await deleteFile({ path: `${fullPath}/${name}` }).unwrap();
    refetch();
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}>
        <Breadcrumbs aria-label="breadcrumb">
          <Link component="button" type="button" underline="hover" color="inherit" onClick={() => setSegments([])}>
            {rootLabel}
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

        <Button
          color="primary"
          variant="filled"
          size="small"
          icon={{ category: "outlined", type: "attach_file" }}
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {t("rework.resources.action.addFile")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(event) => {
            void handleUpload(event.target.files);
            event.target.value = "";
          }}
        />
      </Box>

      {isFetching ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <CircularProgress size={24} />
        </Box>
      ) : sorted.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
          {t("rework.resources.empty.folder")}
        </Typography>
      ) : (
        <List dense>
          {sorted.map((entry) => {
            const directory = isDirectory(entry.type);
            return (
              <ListItem
                key={entry.path}
                disablePadding
                secondaryAction={
                  <IconButton
                    edge="end"
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
                  <ListItemIcon sx={{ minWidth: 36 }}>
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
