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

import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import {
  Avatar,
  Box,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { useLocation, useNavigate } from "react-router-dom";

import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import ChatIcon from "@mui/icons-material/Chat";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import GroupIcon from "@mui/icons-material/Group";
import LightModeIcon from "@mui/icons-material/LightMode";
import MenuIcon from "@mui/icons-material/Menu";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { getProperty } from "../common/config.tsx";
import { ImageComponent } from "../utils/image.tsx";
import { ApplicationContext } from "./ApplicationContextProvider.tsx";

export default function SideBar({ darkMode, onThemeChange }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const applicationContext = useContext(ApplicationContext);
  const smallScreen = useMediaQuery(theme.breakpoints.down("md"));

  // Couleurs sobres à la manière du second fichier
  const sideBarBgColor = theme.palette.sidebar.background;

  const activeItemBgColor = theme.palette.sidebar.activeItem;

  const activeItemTextColor = theme.palette.primary.main;

  const hoverColor = theme.palette.sidebar.hoverColor;

  const menuItems = [
    {
      key: "chat",
      label: t("sidebar.chat"),
      icon: <ChatIcon />,
      url: `/chat`,
      canBeDisabled: false,
      tooltip: t("sidebar.tooltip.chat"),
    },
    {
      key: "monitoring",
      label: t("sidebar.monitoring"),
      icon: <MonitorHeartIcon />,
      url: `/monitoring`,
      canBeDisabled: false,
      tooltip: t("sidebar.tooltip.monitoring"),
    },
    {
      key: "knowledge",
      label: t("sidebar.knowledge"),
      icon: <MenuBookIcon />,
      url: `/knowledge`,
      canBeDisabled: false,
      tooltip: t("sidebar.tooltip.knowledge"),
    },
    {
      key: "agent",
      label: t("sidebar.agent"),
      icon: <GroupIcon />,
      url: `/agentHub`,
      canBeDisabled: false,
      tooltip: t("sidebar.tooltip.agent"),
    },
    {
      key: "account",
      label: t("sidebar.account"),
      icon: <AccountCircleIcon />,
      url: `/account`,
      canBeDisabled: false,
      tooltip: t("sidebar.tooltip.account"),
    },
  ];

  const { isSidebarCollapsed, toggleSidebar } = applicationContext;
  const isSidebarSmall = smallScreen || isSidebarCollapsed;
  const sidebarWidth = isSidebarCollapsed ? theme.layout.sidebarCollapsedWidth : theme.layout.sidebarWidth;

  // Helper function to check if the current path matches the menu item path
  const isActive = (path: string) => {
    const menuPathBase = path.split("?")[0];
    const currentPathBase = location.pathname;

    return currentPathBase === menuPathBase || currentPathBase.startsWith(menuPathBase + "/");
  };

  const logoName = getProperty("logoName") || "fred";

  return (
    <Box
      height="100vh"
      width={sidebarWidth}
      sx={{
        bgcolor: sideBarBgColor,
        color: "text.primary",
        borderRight: `1px solid ${theme.palette.divider}`,
        transition: theme.transitions.create(["width", "margin"], {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.standard,
        }),
        boxShadow: "none",
        display: "flex",
        flexDirection: "column",
        zIndex: theme.zIndex.drawer,
        "& > *": { backgroundColor: sideBarBgColor },
        "& > * > *": { backgroundColor: sideBarBgColor },
      }}
    >
      {/* Section du logo */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: isSidebarSmall ? "center" : "space-between",
          py: 2.5,
          px: isSidebarSmall ? 1 : 2,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            cursor: "pointer",
          }}
          onClick={() => navigate("/")}
        >
          <Avatar
            sx={{
              width: 42,
              height: 42,
              backgroundColor: "transparent",
            }}
          >
            <ImageComponent name={logoName} width="36px" height="36px" />
          </Avatar>
          {!isSidebarSmall && (
            <Typography
              variant="subtitle1"
              sx={{
                ml: 1.5,
                fontWeight: 500,
                color: theme.palette.text.primary,
              }}
            >
              {logoName}
            </Typography>
          )}
        </Box>
        {!isSidebarSmall && (
          <IconButton
            onClick={toggleSidebar}
            size="small"
            sx={{
              borderRadius: "8px",
              "&:hover": {
                backgroundColor: hoverColor,
              },
            }}
          >
            {theme.direction === "ltr" ? <ChevronLeftIcon /> : <ChevronRightIcon />}
          </IconButton>
        )}
      </Box>

      {isSidebarSmall && (
        <Box sx={{ display: "flex", justifyContent: "center", pt: 2 }}>
          <IconButton
            size="small"
            onClick={toggleSidebar}
            sx={{
              borderRadius: "8px",
              border: `1px solid ${theme.palette.divider}`,
              width: 28,
              height: 28,
              "&:hover": {
                backgroundColor: hoverColor,
              },
            }}
          >
            <MenuIcon fontSize="small" />
          </IconButton>
        </Box>
      )}

      <List
        sx={{
          pt: 3,
          px: isSidebarSmall ? 1 : 2,
          flexGrow: 1,
          overflowX: "hidden",
          overflowY: "auto",
        }}
      >
        {menuItems.map((item) => {
          const active = isActive(item.url);
          return (
            <Tooltip
              key={item.key}
              title={
               item.tooltip
              }
              placement="right"
              arrow
            >
              <ListItem
                component="div"
                sx={{
                  borderRadius: "8px",
                  mb: 0.8,
                  height: 44,
                  justifyContent: isSidebarSmall ? "center" : "flex-start",
                  backgroundColor: active ? activeItemBgColor : "transparent",
                  color: active ? activeItemTextColor : "text.secondary",
                  "&:hover": {
                    backgroundColor:
                      active
                          ? activeItemBgColor
                          : hoverColor,
                    color: active ? activeItemTextColor : "text.primary",
                  },
                  transition: "all 0.2s",
                  px: isSidebarSmall ? 1 : 2,
                  position: "relative",
                  cursor: "pointer",
                  opacity:  1,
                  pointerEvents: "auto",
                }}
                onClick={ () => navigate(item.url)}
              >
                <ListItemIcon
                  sx={{
                    color: "inherit",
                    minWidth: isSidebarSmall ? "auto" : 40,
                    fontSize: "1.2rem",
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                {!isSidebarSmall && (
                  <ListItemText
                    primary={
                      <Typography variant="sidebar" fontWeight={active ? 500 : 300}>
                        {item.label}
                      </Typography>
                    }
                  />
                )}
                {active && !isSidebarSmall && (
                  <Box
                    sx={{
                      width: 3,
                      height: 16,
                      bgcolor: theme.palette.primary.main,
                      borderRadius: 4,
                      position: "absolute",
                      right: 12,
                      top: "50%",
                      transform: "translateY(-50%)",
                    }}
                  />
                )}
              </ListItem>
            </Tooltip>
          );
        })}
      </List>

      {/* Pied de page */}
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          py: 2,
          mt: "auto",
          borderTop: `1px solid ${theme.palette.divider}`,
        }}
      >
        {/* Commutateur de thème */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            mb: isSidebarSmall ? 0 : 1,
          }}
        >
          {!isSidebarSmall && (
            <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
              {darkMode ? t("sidebar.theme.dark") : t("sidebar.theme.light")}
            </Typography>
          )}
          <IconButton
            size="small"
            onClick={onThemeChange}
            sx={{
              p: 1,
              "&:hover": {
                backgroundColor: hoverColor,
              },
            }}
          >
            {darkMode ? (
              <LightModeIcon sx={{ fontSize: "1rem", color: "text.secondary" }} />
            ) : (
              <DarkModeIcon sx={{ fontSize: "1rem", color: "text.secondary" }} />
            )}
          </IconButton>
        </Box>

        {/* Liens externes */}
        {!isSidebarSmall && (
          <>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                py: 1,
                px: 2,
                mt: 1,
                width: "90%",
                borderRadius: 1,
              }}
            >
              <Typography variant="caption" color="text.secondary">
                Innovation hub
              </Typography>
              <IconButton
                color="inherit"
                size="small"
                onClick={() => window.open("https://paradox-innovation.dev", "_blank", "noopener,noreferrer")}
                sx={{ p: 0.3 }}
              >
                <OpenInNewIcon sx={{ fontSize: "0.8rem", color: "text.secondary" }} />
              </IconButton>
            </Box>

            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                py: 1,
                px: 2,
                mt: 1,
                width: "90%",
                borderRadius: 1,
              }}
            >
              <Typography variant="caption" color="text.secondary">
                Website
              </Typography>
              <IconButton
                color="inherit"
                size="small"
                onClick={() => window.open("https://fredk8.dev", "_blank", "noopener,noreferrer")}
                sx={{ p: 0.3 }}
              >
                <OpenInNewIcon sx={{ fontSize: "0.8rem", color: "text.secondary" }} />
              </IconButton>
            </Box>
          </>
        )}
      </Box>
    </Box>
  );
}
