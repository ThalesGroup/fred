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

import AddIcon from "@mui/icons-material/Add";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import MicIcon from "@mui/icons-material/Mic";
import StopIcon from "@mui/icons-material/Stop";
import {
  Box,
  Chip,
  Divider,
  IconButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  MenuList,
  Popover,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import React, { SetStateAction } from "react";
// import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
// import DescriptionIcon from "@mui/icons-material/Description";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";

import { useTranslation } from "react-i18next";
import { AgentChatOptions } from "../../../slices/agentic/agenticOpenApi.ts";
import { SearchPolicyName } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { ChatDocumentLibrariesSelectionCard } from "../ChatDocumentLibrariesSelectionCard.tsx";
import { ChatResourcesSelectionCard } from "../ChatResourcesSelectionCard.tsx";

type PickerView = null | "libraries" | "prompts" | "templates" | "search_policy";

interface UserInputPopoverProps {
  plusAnchor: HTMLElement | null;
  pickerView: PickerView;
  isRecording: boolean;
  selectedDocumentLibrariesIds: string[];
  selectedPromptResourceIds: string[];
  selectedTemplateResourceIds: string[];
  selectedSearchPolicyName: SearchPolicyName;
  libNameById: Record<string, string>;
  promptNameById: Record<string, string>;
  templateNameById: Record<string, string>;
  searchPolicyLabels: Record<SearchPolicyName, string>;
  setPickerView: React.Dispatch<SetStateAction<PickerView>>;
  setPlusAnchor: React.Dispatch<SetStateAction<HTMLElement | null>>;
  setLibs: (next: React.SetStateAction<string[]>) => void;
  setPrompts: (next: React.SetStateAction<string[]>) => void;
  setTemplates: (next: React.SetStateAction<string[]>) => void;
  setSearchPolicy: (next: React.SetStateAction<SearchPolicyName>) => void;
  onRemoveLib: (id: string) => void;
  onRemovePrompt: (id: string) => void;
  onRemoveTemplate: (id: string) => void;
  onAttachFileClick: () => void;
  onRecordAudioClick: () => void;
  agentChatOptions?: AgentChatOptions;
  filesBlob: File[] | null;
}

const countChip = (n: number) =>
  n > 0 ? <Chip size="small" label={n} sx={{ height: 20, borderRadius: "999px", fontSize: "0.7rem" }} /> : null;

export const UserInputPopover: React.FC<UserInputPopoverProps> = ({
  plusAnchor,
  pickerView,
  isRecording,
  selectedDocumentLibrariesIds,
  selectedPromptResourceIds,
  selectedTemplateResourceIds,
  selectedSearchPolicyName,
  libNameById,
  // promptNameById,
  // templateNameById,
  searchPolicyLabels,
  setPickerView,
  setPlusAnchor,
  setLibs,
  setPrompts,
  setTemplates,
  setSearchPolicy,
  onRemoveLib,
  // onRemovePrompt,
  // onRemoveTemplate,
  onAttachFileClick,
  onRecordAudioClick,
  agentChatOptions,
  filesBlob,
}) => {
  const { t } = useTranslation();

  const handleClose = () => {
    setPickerView(null);
    setPlusAnchor(null);
  };

  const sectionHeader = (
    icon: React.ReactNode,
    label: string,
    count: number,
    onAdd: () => void,
    onClear?: () => void,
  ) => (
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.75 }}>
      <Stack direction="row" alignItems="center" spacing={1}>
        {icon}
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
        {countChip(count)}
      </Stack>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        {onClear && count > 0 && (
          <Tooltip title={t("documentLibrary.clearSelection")}>
            <IconButton size="small" onClick={() => onClear()}>
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title={t("common.add")}>
          <IconButton size="small" onClick={onAdd}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Stack>
  );

  return (
    <Popover
      open={Boolean(plusAnchor)}
      anchorEl={plusAnchor}
      onClose={handleClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      transformOrigin={{ vertical: "top", horizontal: "right" }}
      slotProps={{
        paper: {
          sx: {
            width: pickerView ? 520 : 420,
            maxHeight: "70vh",
            p: 1.25,
            overflow: "hidden",
          },
        },
      }}
    >
      {!pickerView && (
        <Box sx={{ display: "flex", flexDirection: "column" }}>
          {agentChatOptions?.libraries_selection && (
            <>
              {sectionHeader(
                <LibraryBooksIcon fontSize="small" />,
                t("knowledge.viewSelector.libraries"),
                selectedDocumentLibrariesIds.length,
                () => setPickerView("libraries"),
                () => setLibs([]),
              )}
              <Box sx={{ mb: 1 }}>
                {selectedDocumentLibrariesIds.length ? (
                  <Stack direction="row" flexWrap="wrap" gap={0.75}>
                    {selectedDocumentLibrariesIds.map((id) => (
                      <Chip key={id} size="small" label={libNameById[id] ?? id} onDelete={() => onRemoveLib(id)} />
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    {t("common.noneSelected")}
                  </Typography>
                )}
              </Box>
              <Divider sx={{ my: 1 }} />
            </>
          )}

          {/* {sectionHeader(
            <AutoFixHighIcon fontSize="small" />,
            t("knowledge.viewSelector.prompts"),
            selectedPromptResourceIds.length,
            () => setPickerView("prompts"),
            () => setPrompts([]),
          )}
          <Box sx={{ mb: 1 }}>
            {selectedPromptResourceIds.length ? (
              <Stack direction="row" flexWrap="wrap" gap={0.75}>
                {selectedPromptResourceIds.map((id) => (
                  <Chip key={id} size="small" label={promptNameById[id] ?? id} onDelete={() => onRemovePrompt(id)} />
                ))}
              </Stack>
            ) : (
              <Typography variant="caption" color="text.secondary">
                {t("common.noneSelected")}
              </Typography>
            )}
          </Box> */}
          {/* <Divider sx={{ my: 1 }} /> */}

          {/* {sectionHeader(
            <DescriptionIcon fontSize="small" />,
            t("knowledge.viewSelector.templates"),
            selectedTemplateResourceIds.length,
            () => setPickerView("templates"),
            () => setTemplates([]),
          )}
          <Box sx={{ mb: 1 }}>
            {selectedTemplateResourceIds.length ? (
              <Stack direction="row" flexWrap="wrap" gap={0.75}>
                {selectedTemplateResourceIds.map((id) => (
                  <Chip
                    key={id}
                    size="small"
                    label={templateNameById[id] ?? id}
                    onDelete={() => onRemoveTemplate(id)}
                  />
                ))}
              </Stack>
            ) : (
              <Typography variant="caption" color="text.secondary">
                {t("common.noneSelected")}
              </Typography>
            )}
          </Box>
          <Divider sx={{ my: 1 }} /> */}

          {agentChatOptions?.search_policy_selection && (
            <>
              {sectionHeader(<TravelExploreIcon fontSize="small" />, t("search.policy", "Search policy"), 1, () =>
                setPickerView("search_policy"),
              )}
              <Box sx={{ mb: 1 }}>
                <Stack direction="row" flexWrap="wrap" gap={0.75}>
                  <Chip size="small" label={searchPolicyLabels[selectedSearchPolicyName]} />
                </Stack>
              </Box>
              <Divider sx={{ my: 1 }} />
            </>
          )}

          <MenuList dense sx={{ py: 0.25 }}>
            {agentChatOptions?.attach_files && (
              <MenuItem onClick={onAttachFileClick}>
                <ListItemIcon>
                  <AttachFileIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary={t("chatbot.attachFiles")}
                  secondary={
                    filesBlob?.length
                      ? t("chatbot.attachments.count", {
                          count: filesBlob.length,
                        })
                      : undefined
                  }
                />
              </MenuItem>
            )}
            {agentChatOptions?.record_audio_files && (
              <MenuItem onClick={onRecordAudioClick}>
                <ListItemIcon>
                  {isRecording ? <StopIcon fontSize="small" /> : <MicIcon fontSize="small" />}
                </ListItemIcon>
                <ListItemText primary={isRecording ? t("chatbot.stopRecording") : t("chatbot.recordAudio")} />
              </MenuItem>
            )}
          </MenuList>
        </Box>
      )}

      {pickerView && (
        <Box sx={{ height: "60vh", overflow: "auto", pr: 0.5 }}>
          {pickerView === "libraries" && (
            <ChatDocumentLibrariesSelectionCard
              selectedLibrariesIds={selectedDocumentLibrariesIds}
              setSelectedLibrariesIds={setLibs}
              libraryType="document"
            />
          )}
          {pickerView === "prompts" && (
            <ChatResourcesSelectionCard
              libraryType="prompt"
              selectedResourceIds={selectedPromptResourceIds}
              setSelectedResourceIds={setPrompts}
            />
          )}
          {pickerView === "templates" && (
            <ChatResourcesSelectionCard
              libraryType="template"
              selectedResourceIds={selectedTemplateResourceIds}
              setSelectedResourceIds={setTemplates}
            />
          )}
          {pickerView === "search_policy" && (
            <MenuList sx={{ width: "100%" }}>
              <MenuItem
                onClick={() => {
                  setSearchPolicy("hybrid");
                  setPickerView(null);
                }}
                selected={selectedSearchPolicyName === "hybrid"}
              >
                <ListItemText primary={t("search.hybrid")} secondary={t("search.hybridDescription")} />
              </MenuItem>
              <MenuItem
                onClick={() => {
                  setSearchPolicy("semantic");
                  setPickerView(null);
                }}
                selected={selectedSearchPolicyName === "semantic"}
              >
                <ListItemText primary={t("search.semantic")} secondary={t("search.semanticDescription")} />
              </MenuItem>
              <MenuItem
                onClick={() => {
                  setSearchPolicy("strict");
                  setPickerView(null);
                }}
                selected={selectedSearchPolicyName === "strict"}
              >
                <ListItemText primary={t("search.strict")} secondary={t("search.strictDescription")} />
              </MenuItem>
            </MenuList>
          )}
        </Box>
      )}
    </Popover>
  );
};
