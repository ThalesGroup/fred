// Copyright Thales 2025
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

import React from "react";
import { Chip, CircularProgress, Grid2 } from "@mui/material";
import { useTranslation } from "react-i18next";

interface UserInputAttachmentsProps {
  files: File[] | null;
  uploadingFileNames?: string[];
  audio: Blob | null;
  onRemoveFile: (index: number) => void;
  onShowAudioController: () => void;
  onRemoveAudio: () => void;
}

export const UserInputAttachments: React.FC<UserInputAttachmentsProps> = ({
  files,
  uploadingFileNames,
  audio,
  onRemoveFile,
  onShowAudioController,
  onRemoveAudio,
}) => {
  const { t } = useTranslation();

  const hasAttachments = (uploadingFileNames && uploadingFileNames.length > 0) || (files && files.length > 0) || audio;

  if (!hasAttachments) return null;

  return (
    <Grid2
      container
      size={12}
      height="40px"
      overflow="auto"
      paddingBottom={1}
      display="flex"
      justifyContent="center"
      gap={1}
    >
      {uploadingFileNames &&
        uploadingFileNames.map((name, i) => (
          <Grid2 size="auto" key={`${name}-${i}-uploading`}>
            <Chip
              icon={<CircularProgress size={14} />}
              label={t("chatbot.uploadingFile", { defaultValue: "Uploading {{name}}...", name })}
              color="warning"
              variant="outlined"
              sx={{ height: 32, fontSize: "1.0rem" }}
            />
          </Grid2>
        ))}
      {files &&
        files.map((f, i) => (
          <Grid2 size="auto" key={`${f.name}-${i}`}>
            <Chip
              label={f.name.replace(/\.[^/.]+$/, "")}
              color="primary"
              variant="outlined"
              sx={{ height: 32, fontSize: "1.0rem" }}
              onDelete={() => onRemoveFile(i)}
            />
          </Grid2>
        ))}
      {audio && (
        <Chip
          label={t("chatbot.audioChip", "Audio recording")}
          color="error"
          variant="outlined"
          sx={{ height: 32, fontSize: "1.0rem" }}
          onClick={onShowAudioController}
          onDelete={onRemoveAudio}
        />
      )}
    </Grid2>
  );
};
