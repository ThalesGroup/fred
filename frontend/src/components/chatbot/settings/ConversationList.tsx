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
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  Box,
  Button,
  ClickAwayListener,
  Fade,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  SxProps,
  TextField,
  Theme,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { SessionSchema } from "../../../slices/agentic/agenticOpenApi";
import { useConfirmationDialog } from "../../ConfirmationDialogProvider";

/**
 * Fred UI rationale:
 * - Encapsulate conversation list UX (header + draft row + sessions + actions).
 * - Keep state local (menu anchor, inline edit, fade-in) to avoid bloating Settings.tsx.
 * - Props-only contract so parent decides navigation, creation, and deletion.
 */
export type ConversationListProps = {
  sessions: SessionSchema[];
  currentSession: SessionSchema | null;
  onSelectSession: (session: SessionSchema) => void;
  onCreateNewConversation: () => void;
  onDeleteAllSessions: () => void;
  onDeleteSession: (session: SessionSchema) => void;
  isCreatingNewConversation: boolean;
  sx?: SxProps<Theme>;
};

export const ConversationList: React.FC<ConversationListProps> = (props) => {
  const {
    sessions,
    currentSession,
    onSelectSession,
    onCreateNewConversation,
    onDeleteAllSessions,
    onDeleteSession,
    isCreatingNewConversation,
    sx = [],
  } = props;

  const theme = useTheme<Theme>();
  const isDarkTheme = theme.palette.mode === "dark";
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();

  // Palette hooks (kept aligned with sidebar)
  const activeItemBgColor = theme.palette.sidebar.activeItem;
  const activeItemTextColor = theme.palette.primary.main;
  const hoverColor = theme.palette.sidebar.hoverColor;

  // Local UI state (inline edit + initial fade)
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [showElements, setShowElements] = useState(false);

  const hasSessions = sessions.length > 0;

  useEffect(() => setShowElements(true), []);

  // (Reserved for future rename UX — kept for parity with previous code)
  const saveEditing = () => {
    if (!isEditing) return;
    setEditingSessionId(null);
    setEditText("");
    setIsEditing(false);
  };
  const cancelEditing = () => {
    setEditingSessionId(null);
    setEditText("");
    setIsEditing(false);
  };
  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    e.stopPropagation();
    if (e.key === "Enter") {
      e.preventDefault();
      saveEditing();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancelEditing();
    }
  };
  const handleSaveButtonClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    saveEditing();
  };
  const handleClickAway = () => {
    if (isEditing) saveEditing();
  };

  const handleConfirmDeleteAll = () => {
    showConfirmationDialog({
      title: t("settings.confirmDeleteAllTitle", "Delete all conversations?"),
      message: t(
        "settings.confirmDeleteAllMessage",
        "This action will permanently delete all conversations. Do you want to continue?"
      ),
      onConfirm: onDeleteAllSessions,
    });
  };

  return (
    <Box
      sx={[
        {
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {/* Header + "New conversation" */}
      <Fade in={showElements} timeout={900}>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            px: 2,
            py: 1.5,
            mt: 1,
          }}
        >
          <Typography variant="subtitle1">{t("settings.conversations")}</Typography>
          <Box sx={{ display: "flex", alignItems: "center" }}>
            <Tooltip title={t("settings.newConversation")}>
              <IconButton
                onClick={onCreateNewConversation}
                size="small"
                sx={{
                  borderRadius: "8px",
                  p: 0.5,
                  "&:hover": { backgroundColor: hoverColor },
                }}
              >
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title={t("settings.deleteAll")}>
              <span>
                <IconButton
                  onClick={handleConfirmDeleteAll}
                  size="small"
                  disabled={!hasSessions}
                  sx={{
                    borderRadius: "8px",
                    p: 0.5,
                    "&:hover": { backgroundColor: hoverColor },
                  }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
        </Box>
      </Fade>

      {/* List */}
      <Fade in={showElements} timeout={1100}>
        <List
          sx={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            px: 1.5,
            py: 1,
            "&::-webkit-scrollbar": { width: "5px" },
            "&::-webkit-scrollbar-thumb": {
              backgroundColor: isDarkTheme ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)",
              borderRadius: "3px",
            },
          }}
        >
          {/* Draft row: behaves like a selectable item */}
          <ListItem
            key="__draft__"
            disablePadding
            sx={{
              mb: 0.8,
              borderRadius: "8px",
              backgroundColor: isCreatingNewConversation || !currentSession ? activeItemBgColor : "transparent",
              transition: "all 0.2s",
              position: "relative",
              height: 44,
              "&:hover": {
                backgroundColor: isCreatingNewConversation || !currentSession ? activeItemBgColor : hoverColor,
              },
            }}
          >
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                width: "100%",
                justifyContent: "space-between",
                padding: "0 12px",
                borderRadius: "8px",
                height: "100%",
                cursor: "pointer",
                color: isCreatingNewConversation || !currentSession ? activeItemTextColor : "text.secondary",
                "&:hover": { backgroundColor: hoverColor },
              }}
              onClick={onCreateNewConversation}
            >
              <Box
                sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", textAlign: "left" }}
              >
                <Typography variant="body2" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t("settings.newConversation")}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.disabled" }}>
                  {t("settings.draftNotSaved")}
                </Typography>
              </Box>
            </Box>
          </ListItem>

          {/* Sessions */}
          {[...sessions]
            .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
            .map((session) => {
              const isSelected = session.id === currentSession?.id;
              const isSessionEditing = session.id === editingSessionId;

              return (
                <ListItem
                  key={session.id}
                  disablePadding
                  sx={{
                    mb: 0.8,
                    borderRadius: "8px",
                    backgroundColor: isSelected ? activeItemBgColor : "transparent",
                    transition: "all 0.2s",
                    position: "relative",
                    height: 44,
                    "&:hover": { backgroundColor: isSelected ? activeItemBgColor : hoverColor },
                  }}
                >
                  {isSessionEditing ? (
                    <ClickAwayListener onClickAway={handleClickAway}>
                      <Box
                        sx={{ display: "flex", width: "100%", alignItems: "center", px: 1 }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <TextField
                          autoFocus
                          value={editText}
                          onChange={(e) => setEditText(e.target.value)}
                          onKeyDown={handleEditKeyDown}
                          size="small"
                          fullWidth
                          variant="outlined"
                          sx={{ "& .MuiOutlinedInput-root": { borderRadius: "6px", fontSize: "0.9rem" } }}
                          slotProps={{
                            input: {
                              endAdornment: (
                                <InputAdornment position="end">
                                  <Button size="small" onClick={handleSaveButtonClick}>
                                    OK
                                  </Button>
                                </InputAdornment>
                              ),
                            },
                          }}
                        />
                      </Box>
                    </ClickAwayListener>
                  ) : (
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        width: "100%",
                        justifyContent: "space-between",
                        padding: "0 12px",
                        borderRadius: "8px",
                        height: "100%",
                        cursor: "pointer",
                        color: isSelected ? activeItemTextColor : "text.secondary",
                        "&:hover": { backgroundColor: hoverColor },
                      }}
                      onClick={() => onSelectSession(session)}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          flexDirection: "column",
                          flexGrow: 1,
                          overflow: "hidden",
                          textAlign: "left",
                        }}
                      >
                        <Typography
                          variant="body2"
                          sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "85%" }}
                        >
                          {session.title}
                        </Typography>
                        <Typography variant="caption" sx={{ color: "text.disabled" }}>
                          {new Date(session.updated_at).toLocaleDateString()}
                        </Typography>
                      </Box>
                      <Tooltip title={t("settings.delete")}>
                        <IconButton
                          size="small"
                          sx={{
                            p: 0,
                            color: "inherit",
                            opacity: 0.7,
                            "&:hover": { opacity: 1, backgroundColor: "transparent" },
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteSession(session);
                          }}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  )}
                </ListItem>
              );
            })}

          {sessions.length === 0 && (
            <Box sx={{ p: 2, textAlign: "center", color: "text.disabled" }}>
              <Typography variant="body2">{t("settings.noConversation")}</Typography>
            </Box>
          )}
        </List>
      </Fade>
    </Box>
  );
};
