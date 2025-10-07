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

import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import ChatIcon from "@mui/icons-material/Chat";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import GroupIcon from "@mui/icons-material/Group";
import LightModeIcon from "@mui/icons-material/LightMode";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  Avatar,
  Box,
  Collapse,
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
import { useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { getProperty } from "../common/config.tsx";
import { usePermissions } from "../security/usePermissions";
import { ImageComponent } from "../utils/image.tsx";
import { ApplicationContext } from "./ApplicationContextProvider.tsx";

type MenuItemCfg = {
  key: string;
  label: string;
  icon: React.ReactNode;
  url?: string;
  canBeDisabled: boolean;
  tooltip: string;
  children?: MenuItemCfg[];
};

export default function SideBar({ darkMode, onThemeChange }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const applicationContext = useContext(ApplicationContext);
  const smallScreen = useMediaQuery(theme.breakpoints.down("md"));

  const { can } = usePermissions();

  const sideBarBgColor = theme.palette.sidebar.background;
  const activeItemBgColor = theme.palette.sidebar.activeItem;
  const activeItemTextColor = theme.palette.primary.main;
  const hoverColor = theme.palette.sidebar.hoverColor;

  // Here we set the "can" action to "create" since we want the viewer role not to see kpis and logs.
  // We also can remove the read_only allowed action to the viewer; to: kpi, opensearch & logs in rbac.py in fred_core/security
  // but for now we can leave it like that. 
  const canReadKpis = can("kpi", "create");
  const canReadOpenSearch = can("opensearch", "create");
  const canReadLogs = can("logs", "create");

  const menuItems: MenuItemCfg[] = [
    {
      key: "chat",
      label: t("sidebar.chat"),
      icon: <ChatIcon />,
      url: `/chat`,
      canBeDisabled: false,
      tooltip: t("sidebar.tooltip.chat"),
    },

    // Only show monitoring if user has permission
    ...(canReadKpis || canReadOpenSearch || canReadLogs
      ? [
          {
            key: "monitoring",
            label: t("sidebar.monitoring"),
            icon: <MonitorHeartIcon />,
            canBeDisabled: false,
            tooltip: t("sidebar.tooltip.monitoring"),
            children: [
              ...(canReadKpis
                ? [
                    {
                      key: "monitoring-kpi",
                      label: t("sidebar.monitoring_kpi") || "KPI",
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/kpis`,
                      canBeDisabled: false,
                      tooltip: t("sidebar.tooltip.monitoring_kpi") || "KPI Overview",
                    },
                  ]
                : []),
              ...(canReadOpenSearch || canReadLogs
                ? [
                    {
                      key: "monitoring-logs",
                      label: t("sidebar.monitoring_logs") || "Logs",
                      icon: <MenuBookIcon />,
                      url: `/monitoring/logs`,
                      canBeDisabled: false,
                      tooltip: t("sidebar.tooltip.monitoring_logs") || "Log Console",
                    },
                  ]
                : []),
            ],
          },
        ]
      : []),    {
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

  const isActive = (path: string) => {
    const menuPathBase = path.split("?")[0];
    const currentPathBase = location.pathname;
    return currentPathBase === menuPathBase || currentPathBase.startsWith(menuPathBase + "/");
  };
  const isAnyChildActive = (children?: MenuItemCfg[]) => !!children?.some((c) => c.url && isActive(c.url));

  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setOpenKeys((prev) => {
      const next = { ...prev };
      for (const it of menuItems) {
        if (it.children && isAnyChildActive(it.children)) {
          next[it.key] = true;
        }
      }
      return next;
    });
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const logoName = getProperty("logoName") || "fred";

  return (
    <Box
      height="100vh"
      width={sidebarWidth}
      sx={{
        flex: `0 0 ${sidebarWidth}px`,
        minWidth: sidebarWidth,
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
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: 62,
          py: 0.0,
          px: isSidebarSmall ? 1 : 2,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            cursor: "pointer",
            justifyContent: "center",
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
        </Box>
      </Box>

      <Box sx={{ display: "flex", justifyContent: "center", pt: 2 }}>
        <IconButton
          size="small"
          onClick={toggleSidebar}
          sx={{
            borderRadius: "8px",
            border: `1px solid ${theme.palette.divider}`,
            width: 28,
            height: 28,
            "&:hover": { backgroundColor: hoverColor },
          }}
        >
          {isSidebarCollapsed ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
        </IconButton>
      </Box>

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
          const hasChildren = !!item.children?.length;
          const active = item.url ? isActive(item.url) : isAnyChildActive(item.children);
          const opened = !!openKeys[item.key];

          if (isSidebarSmall) {
            return (
              <Tooltip key={item.key} title={item.tooltip} placement="right" arrow>
                <ListItem
                  component="div"
                  onClick={() =>
                    item.url ? navigate(item.url) : setOpenKeys((s) => ({ ...s, [item.key]: !opened }))
                  }
                  sx={{
                    borderRadius: "8px",
                    mb: 0.8,
                    height: 44,
                    justifyContent: "center",
                    backgroundColor: active ? activeItemBgColor : "transparent",
                    color: active ? activeItemTextColor : "text.secondary",
                    "&:hover": {
                      backgroundColor: active ? activeItemBgColor : hoverColor,
                      color: active ? activeItemTextColor : "text.primary",
                    },
                    transition: "all 0.2s",
                    px: 1,
                    cursor: "pointer",
                  }}
                >
                  <ListItemIcon sx={{ color: "inherit", minWidth: "auto", fontSize: "1.2rem" }}>
                    {item.icon}
                  </ListItemIcon>
                </ListItem>
              </Tooltip>
            );
          }

          return (
            <Box key={item.key}>
              <Tooltip title={item.tooltip} placement="right" arrow>
                <ListItem
                  component="div"
                  onClick={() => {
                    if (hasChildren) {
                      setOpenKeys((s) => ({ ...s, [item.key]: !opened }));
                    } else if (item.url) {
                      navigate(item.url);
                    }
                  }}
                  sx={{
                    borderRadius: "8px",
                    mb: 0.8,
                    height: 44,
                    justifyContent: "flex-start",
                    backgroundColor: active ? activeItemBgColor : "transparent",
                    color: active ? activeItemTextColor : "text.secondary",
                    "&:hover": {
                      backgroundColor: active ? activeItemBgColor : hoverColor,
                      color: active ? activeItemTextColor : "text.primary",
                    },
                    transition: "all 0.2s",
                    px: 2,
                    position: "relative",
                    cursor: "pointer",
                  }}
                >
                  <ListItemIcon sx={{ color: "inherit", minWidth: 40, fontSize: "1.2rem" }}>
                    {item.icon}
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="sidebar" fontWeight={active ? 500 : 300}>
                        {item.label}
                      </Typography>
                    }
                  />
                  {active && (
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

              {hasChildren && (
                <Collapse in={opened} timeout="auto" unmountOnExit>
                  <List component="div" disablePadding sx={{ pl: 5, pr: 1 }}>
                    {item.children!.map((child) => {
                      const childActive = !!child.url && isActive(child.url);
                      return (
                        <Tooltip key={child.key} title={child.tooltip} placement="right" arrow>
                          <ListItem
                            component="div"
                            onClick={() => child.url && navigate(child.url)}
                            sx={{
                              borderRadius: "8px",
                              mb: 0.0,
                              height: 32,
                              backgroundColor: childActive ? activeItemBgColor : "transparent",
                              color: childActive ? activeItemTextColor : "text.secondary",
                              "&:hover": {
                                backgroundColor: childActive ? activeItemBgColor : hoverColor,
                                color: childActive ? activeItemTextColor : "text.primary",
                              },
                              transition: "all 0.2s",
                              px: 1,
                              cursor: "pointer",
                            }}
                          >
                            <ListItemText
                              primary={
                                <Typography variant="sidebar" fontWeight={childActive ? 600 : 400}>
                                  {child.label}
                                </Typography>
                              }
                            />
                          </ListItem>
                        </Tooltip>
                      );
                    })}
                  </List>
                </Collapse>
              )}
            </Box>
          );
        })}
      </List>

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
            sx={{ p: 1, "&:hover": { backgroundColor: hoverColor } }}
          >
            {darkMode ? (
              <LightModeIcon sx={{ fontSize: "1rem", color: "text.secondary" }} />
            ) : (
              <DarkModeIcon sx={{ fontSize: "1rem", color: "text.secondary" }} />
            )}
          </IconButton>
        </Box>

        {!isSidebarSmall && (
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
        )}
      </Box>
    </Box>
  );
}
