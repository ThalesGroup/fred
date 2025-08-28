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
import { Box, Paper, Typography, IconButton, Stack, Chip, useTheme } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { useTranslation } from "react-i18next";

type LabelMap = Record<string, string>;

export interface ChatKnowledgeProps {
  open: boolean;
  hasContext: boolean;
  userInputContext: any;
  onClose: () => void;
  libraryNameMap: LabelMap;
  promptNameMap: LabelMap;
  templateNameMap: LabelMap;
}

const ChatKnowledge: React.FC<ChatKnowledgeProps> = ({
  open,
  hasContext,
  userInputContext,
  onClose,
  libraryNameMap,
  promptNameMap,
  templateNameMap,
}) => {
  const theme = useTheme();
  const { t } = useTranslation();

  if (!open || !hasContext) return null;

  const renderChips = (
    ids: string[] = [],
    onDelete?: (id: string) => void,
    labelMap?: Record<string, string>
  ) => (
    <Stack direction="row" flexWrap="wrap" gap={0.5}>
      {ids.map((id) => (
        <Chip
          key={id}
          label={labelMap?.[id] ?? id}
          size="small"
          onDelete={onDelete ? () => onDelete(id) : undefined}
        />
      ))}
    </Stack>
  );

  return (
    <Paper
      elevation={8}
      sx={{
        position: "fixed",
        right: 24,
        bottom: 24,
        width: 320,
        maxHeight: "60vh",
        overflow: "auto",
        borderRadius: 3,
        p: 1.5,
        border: `1px solid ${theme.palette.divider}`,
        bgcolor: theme.palette.background.paper,
        zIndex: 1300,
      }}
    >
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
        <Typography variant="subtitle1" fontWeight={600}>
          {t("chatbot.knowledgePanel.title")}
        </Typography>
        <IconButton size="small" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      <Stack spacing={1.25}>
        {userInputContext?.files?.length ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t("chatbot.knowledgePanel.files", { count: userInputContext.files.length })}
            </Typography>
            <Stack spacing={0.5}>
              {userInputContext.files.map((f: File, idx: number) => (
                <Box
                  key={`${f.name}-${idx}`}
                  display="flex"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{ border: 1, borderColor: "divider", borderRadius: 2, px: 1, py: 0.5 }}
                >
                  <Typography variant="body2" noWrap title={f.name} sx={{ maxWidth: 200 }}>
                    {f.name}
                  </Typography>
                  <IconButton size="small" onClick={() => userInputContext.actions?.removeFile(idx)}>
                    <CloseIcon fontSize="inherit" />
                  </IconButton>
                </Box>
              ))}
            </Stack>
          </Box>
        ) : null}

        {userInputContext?.audioBlob ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t("chatbot.knowledgePanel.audio")}
            </Typography>
            <Box
              display="flex"
              alignItems="center"
              justifyContent="space-between"
              sx={{ border: 1, borderColor: "divider", borderRadius: 2, px: 1, py: 0.5 }}
            >
              <Typography variant="body2">
                {t("chatbot.knowledgePanel.audioCount", { count: 1 })}
              </Typography>
              <IconButton size="small" onClick={() => userInputContext.actions?.removeAudio()}>
                <CloseIcon fontSize="inherit" />
              </IconButton>
            </Box>
          </Box>
        ) : null}

        {(userInputContext?.documentLibraryIds?.length ?? 0) > 0 ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t("chatbot.knowledgePanel.libraries", {
                count: userInputContext.documentLibraryIds.length,
              })}
            </Typography>
            {renderChips(
              userInputContext.documentLibraryIds,
              userInputContext.actions?.removeDocLib,
              libraryNameMap
            )}
          </Box>
        ) : null}

        {(userInputContext?.promptResourceIds?.length ?? 0) > 0 ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t("chatbot.knowledgePanel.prompts", {
                count: userInputContext.promptResourceIds.length,
              })}
            </Typography>
            {renderChips(
              userInputContext.promptResourceIds,
              userInputContext.actions?.removePrompt,
              promptNameMap
            )}
          </Box>
        ) : null}

        {(userInputContext?.templateResourceIds?.length ?? 0) > 0 ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t("chatbot.knowledgePanel.templates", {
                count: userInputContext.templateResourceIds.length,
              })}
            </Typography>
            {renderChips(
              userInputContext.templateResourceIds,
              userInputContext.actions?.removeTemplate,
              templateNameMap
            )}
          </Box>
        ) : null}
      </Stack>
    </Paper>
  );
};

export default ChatKnowledge;
