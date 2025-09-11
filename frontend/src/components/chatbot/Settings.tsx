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

import {
  Box,
  Button,
  IconButton,
  MenuItem,
  TextField,
  Theme,
  Tooltip,
  Typography,
  useTheme,
  List,
  ListItem,
  ClickAwayListener,
  Fade,
  ListItemButton,
  ListItemText,
  Divider,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import { useEffect, useState } from "react";
import { getAgentBadge } from "../../utils/avatar.tsx";
import React from "react";
import { StyledMenu } from "../../utils/styledMenu.tsx";
import { useTranslation } from "react-i18next";
import { AgenticFlow, SessionSchema } from "../../slices/agentic/agenticOpenApi.ts";

export const Settings = ({
  sessions,
  currentSession,
  onSelectSession,
  onCreateNewConversation,
  agenticFlows,
  currentAgenticFlow,
  onSelectAgenticFlow,
  onDeleteSession,
  isCreatingNewConversation,
}: {
  sessions: SessionSchema[];
  currentSession: SessionSchema | null;
  onSelectSession: (session: SessionSchema) => void;
  onCreateNewConversation: () => void;
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
  onSelectAgenticFlow: (flow: AgenticFlow) => void;
  onDeleteSession: (session: SessionSchema) => void;
  isCreatingNewConversation: boolean; // ← new
}) => {
  // Récupération du thème pour l'adaptation des couleurs
  const theme = useTheme<Theme>();
  const isDarkTheme = theme.palette.mode === "dark";
  const { t } = useTranslation();

  // Couleurs harmonisées avec le SideBar
  const bgColor = theme.palette.sidebar.background;

  const activeItemBgColor = theme.palette.sidebar.activeItem;

  const activeItemTextColor = theme.palette.primary.main;

  const hoverColor = theme.palette.sidebar.hoverColor;

  // États du composant
  const [menuAnchorEl, setMenuAnchorEl] = useState<HTMLElement | null>(null);
  const [chatProfileSession, setChatProfileSession] = useState<SessionSchema | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [showElements, setShowElements] = useState(false);

  // Gestion du menu chatProfileuel
  const openMenu = (event: React.MouseEvent<HTMLElement>, session: SessionSchema) => {
    event.stopPropagation();
    setMenuAnchorEl(event.currentTarget);
    setChatProfileSession(session);
  };

  const closeMenu = () => {
    setMenuAnchorEl(null);
  };

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
    if (isEditing) {
      saveEditing();
    }
  };

  useEffect(() => {
    setShowElements(true);
  }, []);

  return (
    <Box
      sx={{
        width: "250px",
        height: "100vh",
        backgroundColor: bgColor,
        color: "text.primary",
        borderRight: `1px solid ${theme.palette.divider}`,
        borderLeft: `1px solid ${theme.palette.divider}`,
        display: "flex",
        flexDirection: "column",
        transition: theme.transitions.create(["width", "background-color"], {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.standard,
        }),
        boxShadow: "None",
      }}
    >
      <Fade in={showElements} timeout={900}>
        <Box
          sx={{
            py: 2.5,
            px: 2,
            borderBottom: `1px solid ${theme.palette.divider}`,
          }}
        >
          <Typography
            variant="subtitle1"
            sx={{
              mb: 2,
              fontWeight: 500,
            }}
          >
            {t("settings.assistants")}
          </Typography>

          {currentAgenticFlow && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              {/* Fred rationale:
       - Uniform, vertical, compact list.
       - Tooltip shows role + description without stealing clicks.
       - Selected line uses a clear border + subtle bg.
    */}
              <List dense disablePadding>
                {agenticFlows.map((flow) => {
                  const isSelected = flow.name === currentAgenticFlow.name;

                  // Tooltip content: nickname (title), then role + description
                  const tooltipContent = (
                    <Box sx={{ maxWidth: 460 }}>
                      {/* Nickname */}
                      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.75 }}>
                        {flow.nickname}
                      </Typography>

                      {/* Subtle separator */}
                      <Divider sx={{ opacity: 0.5, mb: 0.75 }} />

                      {/* Role + description grouped with a thin left accent */}
                      <Box
                        sx={(theme) => ({
                          pl: 1.25,
                          borderLeft: `2px solid ${theme.palette.divider}`,
                        })}
                      >
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{ fontStyle: "italic", mb: flow.description ? 0.25 : 0 }}
                        >
                          {flow.role}
                        </Typography>

                        {flow.description && (
                          <Typography variant="body2" color="text.secondary">
                            {flow.description}
                          </Typography>
                        )}
                      </Box>
                    </Box>
                  );

                  return (
                    <ListItem key={flow.name} disableGutters sx={{ mb: 0 }}>
                      <Tooltip title={tooltipContent} placement="right" arrow
                        slotProps={{ tooltip: { sx: { maxWidth: 460 } } }}
                      >
                        <ListItemButton
                          dense
                          onClick={() => onSelectAgenticFlow(flow)}
                          selected={isSelected}
                          sx={{
                            // Compact, consistent row height
                            //minHeight: 30,
                            borderRadius: 1,
                            px: 1,
                            py: 0,
                            border: `1px solid ${isSelected ? theme.palette.primary.main : theme.palette.divider}`,
                            backgroundColor: isSelected
                              ? theme.palette.mode === "dark"
                                ? "rgba(25,118,210,0.12)"
                                : "rgba(25,118,210,0.06)"
                              : "transparent",
                            "&:hover": {
                              backgroundColor: isSelected
                                ? theme.palette.mode === "dark"
                                  ? "rgba(25,118,210,0.16)"
                                  : "rgba(25,118,210,0.1)"
                                : theme.palette.mode === "dark"
                                  ? "rgba(255,255,255,0.04)"
                                  : "rgba(0,0,0,0.03)",
                            },
                          }}
                        >
                          {/* Keep your badge (with ⭐), scaled down */}
                          <Box sx={{ mr: 1, transform: "scale(0.8)", transformOrigin: "center", lineHeight: 0 }}>
                            {getAgentBadge(flow.nickname)}
                          </Box>

                          <ListItemText
                            primary={flow.nickname}
                            secondary={flow.role}
                            primaryTypographyProps={{
                              variant: "body2",
                              fontWeight: isSelected ? 600 : 500,
                              noWrap: true,
                            }}
                            secondaryTypographyProps={{
                              variant: "caption",
                              color: "text.secondary",
                              noWrap: true,
                            }}
                          />
                        </ListItemButton>
                      </Tooltip>
                    </ListItem>
                  );
                })}
              </List>
            </Box>
          )}
        </Box>
      </Fade>

      {/* En-tête des conversations avec bouton d'ajout */}
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
          <Typography
            variant="body2"
            sx={{
              color: "text.secondary",
              fontWeight: 500,
            }}
          >
            {t("settings.conversations")}
          </Typography>
          <Tooltip title={t("settings.newConversation")}>
            <IconButton
              onClick={() => onCreateNewConversation()}
              size="small"
              sx={{
                borderRadius: "8px",
                p: 0.5,
                "&:hover": {
                  backgroundColor: hoverColor,
                },
              }}
            >
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Fade>

      {/* Liste des sessions de conversation */}
      <Fade in={showElements} timeout={1100}>
        <List
          sx={{
            flexGrow: 1,
            overflowY: "auto",
            px: 1.5,
            py: 1,
            "&::-webkit-scrollbar": {
              width: "3px",
            },
            "&::-webkit-scrollbar-thumb": {
              backgroundColor: isDarkTheme ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)",
              borderRadius: "3px",
            },
          }}
        >
          {/* === Pseudo-item for "New Conversation" === */}
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
              onClick={() => onCreateNewConversation()}
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
                    "&:hover": {
                      backgroundColor: isSelected ? activeItemBgColor : hoverColor,
                    },
                  }}
                >
                  {isSessionEditing ? (
                    // Mode édition
                    <ClickAwayListener onClickAway={handleClickAway}>
                      <Box
                        sx={{
                          display: "flex",
                          width: "100%",
                          alignItems: "center",
                          px: 1,
                        }}
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
                          sx={{
                            "& .MuiOutlinedInput-root": {
                              borderRadius: "6px",
                              fontSize: "0.9rem",
                            },
                          }}
                          InputProps={{
                            endAdornment: (
                              <Button
                                size="small"
                                onClick={handleSaveButtonClick}
                                sx={{
                                  minWidth: "auto",
                                  p: "2px 8px",
                                  fontSize: "0.75rem",
                                  fontWeight: 500,
                                }}
                              >
                                OK
                              </Button>
                            ),
                          }}
                        />
                      </Box>
                    </ClickAwayListener>
                  ) : (
                    // Mode normal
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        width: "100%",
                        justifyContent: "space-between",
                        padding: "0 12px",
                        borderRadius: "8px",
                        height: "100%",
                        backgroundColor: "transparent",
                        cursor: "pointer",
                        color: isSelected ? activeItemTextColor : "text.secondary",
                        "&:hover": {
                          backgroundColor: hoverColor,
                        },
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
                          sx={{
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {session.title}
                        </Typography>
                        <Typography variant="caption" sx={{ color: "text.disabled" }}>
                          {new Date(session.updated_at).toLocaleDateString()}
                        </Typography>
                      </Box>
                      <IconButton
                        size="small"
                        sx={{
                          padding: 0,
                          color: "inherit",
                          opacity: 0.7,
                          "&:hover": {
                            opacity: 1,
                            backgroundColor: "transparent",
                          },
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          openMenu(e, session);
                        }}
                      >
                        <MoreHorizIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  )}
                </ListItem>
              );
            })}

          {/* Message quand aucune session */}
          {sessions.length === 0 && (
            <Box
              sx={{
                p: 2,
                textAlign: "center",
                color: "text.disabled",
              }}
            >
              <Typography variant="body2">{t("settings.noConversation")}</Typography>
            </Box>
          )}
        </List>
      </Fade>

      {/* Menu chatProfileuel */}
      <StyledMenu
        id="session-chatProfile-menu"
        anchorEl={menuAnchorEl}
        open={Boolean(menuAnchorEl)}
        onClose={closeMenu}
      >
        <MenuItem
          onClick={() => {
            if (chatProfileSession) {
              onDeleteSession(chatProfileSession);
              closeMenu();
            }
          }}
          disableRipple
        >
          <DeleteOutlineIcon fontSize="small" sx={{ mr: 2, fontSize: "1rem" }} />
          <Typography variant="body2">{t("settings.delete")}</Typography>
        </MenuItem>
      </StyledMenu>
    </Box>
  );
};
