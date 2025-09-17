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
import { useEffect, useState, useMemo } from "react";
import { getAgentBadge } from "../../utils/avatar.tsx";
import React from "react";
import { StyledMenu } from "../../utils/styledMenu.tsx";
import { useTranslation } from "react-i18next";
import { AgenticFlow, SessionSchema } from "../../slices/agentic/agenticOpenApi.ts";
import Popover from "@mui/material/Popover";
import { useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { ChatResourcesSelectionCard } from "./ChatResourcesSelectionCard.tsx";
import { PluginSelector, PluginItem } from "./PluginSelector.tsx";

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
  onChangeSelectedProfileIds,
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
  onChangeSelectedProfileIds?: (ids: string[]) => void;
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

  // === Profile selection via card (no dropdown) ===
  const [selectedProfileIds, setSelectedProfileIds] = useState<string[]>([]);
  const [profilePickerAnchor, setProfilePickerAnchor] = useState<HTMLElement | null>(null);
  const selectedProfileId = selectedProfileIds[0] ?? null;
  const { data: selectedProfileResource } =
    useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery(
      { resourceId: selectedProfileId as string },
      { skip: !selectedProfileId }
    );
  const hasSelectedProfile = !!selectedProfileId; // ← clé pour éviter l'effet de cache RTK

  const profileBodyPreview = useMemo(() => {
    const c = selectedProfileResource?.content ?? "";
    const sep = "\n---\n";
    const i = c.indexOf(sep);
    const body = (i !== -1 ? c.slice(i + sep.length) : c).replace(/\r\n/g, "\n").trim();
    if (!body) return null;
    const oneline = body.split("\n").filter(Boolean).slice(0, 2).join(" ");
    return oneline.length > 180 ? oneline.slice(0, 180) + "…" : oneline;
  }, [selectedProfileResource]);

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

  useEffect(() => {
    if (!selectedProfileId) {
      setProfilePickerAnchor(null);
    }
  }, [selectedProfileId]);

  const applyProfileSelection = (ids: string[]) => {
    setSelectedProfileIds(ids);
    onChangeSelectedProfileIds?.(ids);
    setProfilePickerAnchor(null);
  };

  const [pluginAnchorEl, setPluginAnchorEl] = useState<HTMLElement | null>(null);
  const [pluginAgent] = useState<string | null>(null);
  const [selectedPluginIdsByAgent, setSelectedPluginIdsByAgent] = useState<Record<string, string[]>>({});

  const pluginItems: PluginItem[] = useMemo(
    () => [
      { id: "web_search", name: "Web Search", group: "Core", description: "Search the web during answers" },
      { id: "sql_runner", name: "SQL Runner", group: "Data", description: "Run read-only SQL queries" },
      { id: "viz", name: "Visualization", group: "Core", description: "Render charts and diagrams" },
      { id: "github", name: "GitHub", group: "Integrations", description: "Read issues and PRs" },
    ],
    []
  );

  // const openPluginPicker = (e: React.MouseEvent, flowName: string) => {
  //   e.stopPropagation();
  //   e.preventDefault();
  //   setPluginAgent(flowName);
  //   setPluginAnchorEl(e.currentTarget as HTMLElement);
  // };

  const closePluginPicker = () => {
    setPluginAnchorEl(null);
  };

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
          {/* Titre + action à droite */}
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <Typography
              variant="subtitle1"
              sx={{
                fontWeight: 500,
              }}
            >
              {t("settings.profile")}
            </Typography>

            {/* À droite : '+' si aucun profil */}
            {!hasSelectedProfile && (
              <Tooltip title={t("settings.selectProfile", "Select a profile")}>
                <IconButton
                  size="small"
                  onClick={(e) => setProfilePickerAnchor(e.currentTarget)}
                  sx={{ borderRadius: 1.5 }}
                >
                  <AddIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
          </Box>

          {/* Popover de sélection/modification */}
          <Popover
            open={Boolean(profilePickerAnchor)}
            anchorEl={profilePickerAnchor}
            onClose={() => setProfilePickerAnchor(null)}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
            PaperProps={{ sx: { p: 1 } }}
          >
            <ChatResourcesSelectionCard
              libraryType={"profile"}
              selectedResourceIds={selectedProfileIds}
              setSelectedResourceIds={(ids) => {
                const next = ids.length > 0 ? [ids[ids.length - 1]] : [];
                applyProfileSelection(next);
              }}
            />
          </Popover>

          {hasSelectedProfile && (
            <List dense disablePadding sx={{ mt: 1 }}>
              <ListItem disableGutters sx={{ mb: 0 }}>
                <ListItemButton
                  dense
                  selected
                  onClick={(e) => setProfilePickerAnchor(e.currentTarget)}
                  sx={{
                    borderRadius: 1,
                    px: 1,
                    py: 0.75,
                    alignItems: "flex-start",
                    border: `1px solid ${theme.palette.primary.main}`,
                    backgroundColor:
                      theme.palette.mode === "dark"
                        ? "rgba(25,118,210,0.06)"
                        : "rgba(25,118,210,0.04)",
                    "&:hover": {
                      backgroundColor:
                        theme.palette.mode === "dark"
                          ? "rgba(25,118,210,0.1)"
                          : "rgba(25,118,210,0.08)",
                    },
                  }}
                >
                  <Box sx={{ width: "100%", minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                      {selectedProfileResource?.name}
                    </Typography>

                    {Array.isArray(selectedProfileResource?.labels) &&
                      selectedProfileResource!.labels.length > 0 && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }} noWrap>
                          {selectedProfileResource!.labels.join(" · ")}
                        </Typography>
                      )}

                    {profileBodyPreview && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                          mt: 0.5,
                          display: "-webkit-box",
                          WebkitLineClamp: "2",
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "normal",
                        } as any}
                      >
                        {profileBodyPreview}
                      </Typography>
                    )}
                  </Box>
                </ListItemButton>
              </ListItem>
            </List>
          )}
        </Box>
      </Fade>

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

          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            {/* Fred rationale:
     - Always render the list so users can pick an assistant even with no session.
     - Selection is computed safely with optional chaining. */}
            <List dense disablePadding>
              {agenticFlows.map((flow) => {
                const isSelected = currentAgenticFlow?.name === flow.name;

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
                    <Tooltip
                      title={tooltipContent}
                      placement="right"
                      arrow
                      slotProps={{ tooltip: { sx: { maxWidth: 460 } } }}
                    >
                      <ListItemButton
                        dense
                        onClick={() => onSelectAgenticFlow(flow)}
                        selected={isSelected}
                        sx={{
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
                        {/* Badge */}
                        <Box sx={{ mr: 1, transform: "scale(0.8)", transformOrigin: "center", lineHeight: 0 }}>
                          {getAgentBadge(flow.nickname)}
                        </Box>

                        {/* Texts */}
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

                          <Box sx={{ ml: "auto", opacity:0 }}>
                            <Tooltip disableHoverListener title={t("settings.add", "Add")}>
                              <IconButton
                                size="small"
                                edge="end"
                                disableRipple
                                tabIndex={-1}
                                //onMouseDown={(e) => e.stopPropagation()}
                                //onClick={(e) => openPluginPicker(e, flow.name)}
                                sx={{ borderRadius: 1.5 }}
                              >
                                <AddIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </Box>
                      </ListItemButton>
                    </Tooltip>
                  </ListItem>
                );
              })}
            </List>

            {/* Optional hint when nothing is selected */}
            {!currentAgenticFlow && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, px: 1 }}>
                {t("settings.pickAssistantToStart")}
              </Typography>
            )}

              <Popover
                open={Boolean(pluginAnchorEl)}
                anchorEl={pluginAnchorEl}
                onClose={closePluginPicker}
                anchorOrigin={{ vertical: "center", horizontal: "right" }}
                transformOrigin={{ vertical: "center", horizontal: "left" }}
                PaperProps={{ sx: { p: 1 } }}
              >
                <PluginSelector
                  items={pluginItems}
                  selectedIds={selectedPluginIdsByAgent[pluginAgent ?? ""] ?? []}
                  onChange={(ids) =>
                    setSelectedPluginIdsByAgent((prev) => ({
                      ...prev,
                      [(pluginAgent ?? "")]: ids,
                    }))
                  }
                />
              </Popover>
          </Box>
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
