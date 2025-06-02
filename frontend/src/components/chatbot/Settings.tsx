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
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import { AgenticFlow } from "../../pages/Chat.tsx";
import { useEffect, useState } from "react";
import { getAgentBadge } from "../../utils/avatar.tsx";
import React from "react";
import { StyledMenu } from "../../utils/styledMenu.tsx";
import { SessionSchema } from "../../slices/chatApiStructures.ts";

export const Settings = ({
  sessions,
  currentSession,
  onSelectSession,
  onCreateNewConversation,
  agenticFlows,
  currentAgenticFlow,
  onSelectAgenticFlow,
  onDeleteSession,
}: {
  sessions: SessionSchema[];
  currentSession: SessionSchema | null;
  onSelectSession: (session: SessionSchema) => void;
  onCreateNewConversation: () => void;
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
  onSelectAgenticFlow: (flow: AgenticFlow) => void;
  onDeleteSession: (session: SessionSchema) => void;
}) => {
  // Récupération du thème pour l'adaptation des couleurs
  const theme = useTheme<Theme>();
  const isDarkTheme = theme.palette.mode === "dark";

  // Couleurs harmonisées avec le SideBar
  const bgColor = theme.palette.sidebar.background;

  const activeItemBgColor = theme.palette.sidebar.activeItem;

  const activeItemTextColor = theme.palette.primary.main;

  const hoverColor = theme.palette.sidebar.hoverColor;

  // États du composant
  const [menuAnchorEl, setMenuAnchorEl] = useState<HTMLElement | null>(null);
  const [contextSession, setContextSession] = useState<SessionSchema | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [showElements, setShowElements] = useState(false);

  // Gestion du menu contextuel
  const openMenu = (event: React.MouseEvent<HTMLElement>, session: SessionSchema) => {
    event.stopPropagation();
    setMenuAnchorEl(event.currentTarget);
    setContextSession(session);
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

  // Animation au chargement
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
      {/* En-tête: titre et sélecteur d'agent */}
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
            Assistants
          </Typography>

          {currentAgenticFlow && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              {agenticFlows.map((flow) => {
                const isSelected = flow.name === currentAgenticFlow.name;
                return (
                  <Box
                    key={flow.name}
                    onClick={() => onSelectAgenticFlow(flow)}
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      padding: "8px 12px",
                      borderRadius: "10px",
                      cursor: "pointer",
                      border: isSelected
                        ? `2px solid ${theme.palette.primary.main}`
                        : `1px solid ${theme.palette.divider}`,
                      backgroundColor: isSelected
                        ? isDarkTheme
                          ? "rgba(25, 118, 210, 0.12)"
                          : "rgba(25, 118, 210, 0.05)"
                        : isDarkTheme
                          ? "rgba(255,255,255,0.03)"
                          : "rgba(0,0,0,0.02)",
                      transition: "all 0.2s",
                      "&:hover": {
                        backgroundColor: isSelected
                          ? isDarkTheme
                            ? "rgba(25, 118, 210, 0.15)"
                            : "rgba(25, 118, 210, 0.08)"
                          : isDarkTheme
                            ? "rgba(255,255,255,0.05)"
                            : "rgba(0,0,0,0.04)",
                      },
                    }}
                  >
                    <Box sx={{ mr: 2 }}>{getAgentBadge(flow.nickname)}</Box>
                    <Box
                      sx={{
                        display: "flex",
                        flexDirection: "column",
                        flexGrow: 1,
                      }}
                    >
                      <Typography
                        variant="body1"
                        sx={{
                          fontWeight: isSelected ? 500 : 400,
                          color: isSelected ? theme.palette.primary.main : "text.primary",
                        }}
                      >
                        {flow.nickname}
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{
                          color: "text.secondary",
                          lineHeight: 1.2,
                        }}
                      >
                        {flow.role}
                      </Typography>
                    </Box>
                    {isSelected && (
                      <Box
                        sx={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          backgroundColor: theme.palette.primary.main,
                          ml: 1,
                        }}
                      />
                    )}
                  </Box>
                );
              })}
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
            Conversations
          </Typography>
          <Tooltip title="New conversation">
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
              <Typography variant="body2">Aucune conversation</Typography>
            </Box>
          )}
        </List>
      </Fade>

      {/* Menu contextuel */}
      <StyledMenu id="session-context-menu" anchorEl={menuAnchorEl} open={Boolean(menuAnchorEl)} onClose={closeMenu}>
        <MenuItem
          onClick={() => {
            if (contextSession) {
              onDeleteSession(contextSession);
              closeMenu();
            }
          }}
          disableRipple
        >
          <DeleteOutlineIcon fontSize="small" sx={{ mr: 2, fontSize: "1rem" }} />
          <Typography variant="body2">Supprimer</Typography>
        </MenuItem>
      </StyledMenu>
    </Box>
  );
};
