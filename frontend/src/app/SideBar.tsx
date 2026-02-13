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
import AssistantIcon from "@mui/icons-material/Assistant";
import ConstructionIcon from "@mui/icons-material/Construction";
import GroupsIcon from "@mui/icons-material/Groups";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import ScheduleIcon from "@mui/icons-material/Schedule";
import ScienceIcon from "@mui/icons-material/Science";
import ShieldIcon from "@mui/icons-material/Shield";
import { Avatar, Box, CSSObject, Divider, Paper, styled, Theme, Typography } from "@mui/material";
import MuiDrawer from "@mui/material/Drawer";
import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { getProperty } from "../common/config";
import { DynamicSvgIcon } from "../components/DynamicSvgIcon";
import InvisibleLink from "../components/InvisibleLink";
import {
  SideBarConversationsSection,
  SideBarNavigationElement,
  SideBarNavigationList,
  SidebarProfileSection,
} from "../components/sideBar";
import { SideBarNewConversationButton } from "../components/sideBar/SideBarNewConversationButton";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { KeyCloakService } from "../security/KeycloakService";
import { usePermissions } from "../security/usePermissions";
import { useListTeamsKnowledgeFlowV1TeamsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowApiEnhancements";
import { ImageComponent } from "../utils/image";
import { ApplicationContext } from "./ApplicationContextProvider";

const drawerWidth = 280;
const openedMixin = (theme: Theme): CSSObject => ({
  width: drawerWidth,
  transition: theme.transitions.create("width", {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.enteringScreen,
  }),
  overflowX: "hidden",
});

const closedMixin = (theme: Theme): CSSObject => ({
  transition: theme.transitions.create("width", {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  overflowX: "hidden",
  width: `calc(${theme.spacing(7)} + 1px)`,
  [theme.breakpoints.up("sm")]: {
    width: `calc(${theme.spacing(8)} + 1px)`,
  },
});

const Drawer = styled(MuiDrawer, { shouldForwardProp: (prop) => prop !== "open" })(({ theme }) => ({
  width: drawerWidth,
  flexShrink: 0,
  whiteSpace: "nowrap",
  boxSizing: "border-box",
  variants: [
    {
      props: ({ open }) => open,
      style: {
        ...openedMixin(theme),
        "& .MuiDrawer-paper": openedMixin(theme),
      },
    },
    {
      props: ({ open }) => !open,
      style: {
        ...closedMixin(theme),
        "& .MuiDrawer-paper": closedMixin(theme),
      },
    },
  ],
}));
export default function SideBar() {
  const { t } = useTranslation();
  const { agentsNicknamePlural, agentIconName } = useFrontendProperties();

  // Remove collapsing for now
  // const [open, setOpen] = useLocalStorageState("SideBar.open", true);
  const open = true;

  // Here we set the "can" action to "create" since we want the viewer role not to see kpis and logs.
  // We also can remove the read_only allowed action to the viewer; to: kpi, opensearch & logs in rbac.py in fred_core/security
  // but for now we can leave it like that.
  const { can } = usePermissions();
  const canReadKpis = can("kpi", "create");
  const canReadOpenSearch = can("opensearch", "create");
  const canReadLogs = can("logs", "create");
  const canReadRuntime = can("kpi", "create");
  const canUpdateTag = can("tag", "update");

  const userRoles = KeyCloakService.GetUserRoles();
  const isAdmin = userRoles.includes("admin");

  const { darkMode } = useContext(ApplicationContext);
  const menuItems: SideBarNavigationElement[] = [
    {
      key: "agent",
      label: t("sidebar.agent", {
        agentsNickname: agentsNicknamePlural,
      }),
      icon: agentIconName ? (
        <DynamicSvgIcon iconPath={`images/${agentIconName}.svg`} color="action" />
      ) : (
        <AssistantIcon />
      ),
      url: `/agents`,
    },
    {
      key: "knowledge",
      label: t("sidebar.knowledge"),
      icon: <MenuBookIcon />,
      url: `/knowledge`,
    },
    {
      key: "teams",
      label: t("sidebar.teams"),
      icon: <GroupsIcon />,
      url: `/teams`,
    },
  ];
  const adminMenuItems: SideBarNavigationElement[] = [
    {
      key: "mcp",
      label: t("sidebar.mcp"),
      icon: <ConstructionIcon />,
      url: `/tools`,
    },
    ...(canReadKpis || canReadOpenSearch || canReadLogs || canReadRuntime || canUpdateTag
      ? [
          {
            key: "laboratory",
            label: t("sidebar.laboratory"),
            icon: <ScienceIcon />,
            children: [
              ...(canReadRuntime
                ? [
                    {
                      key: "monitoring-graph",
                      label: t("sidebar.monitoring_graph", "Graph Hub"),
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/graph`,
                    },
                  ]
                : []),
              ...(canReadRuntime
                ? [
                    {
                      key: "monitoring-processors",
                      label: t("sidebar.monitoring_processors", "Processors"),
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/processors`,
                    },
                  ]
                : []),
              {
                key: "laboratory-scheduler",
                label: t("sidebar.apps_scheduler", "Scheduler"),
                icon: <ScheduleIcon />,
                url: `/apps/scheduler`,
              },
            ],
          },
        ]
      : []),

    // Only show monitoring if user has permission
    ...(canReadKpis || canReadOpenSearch || canReadLogs || canReadRuntime || canUpdateTag
      ? [
          {
            key: "monitoring",
            label: t("sidebar.monitoring"),
            icon: <MonitorHeartIcon />,
            children: [
              ...(canReadKpis
                ? [
                    {
                      key: "monitoring-kpi",
                      label: t("sidebar.monitoring_kpi") || "KPI",
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/kpis`,
                    },
                  ]
                : []),
              ...(canReadRuntime
                ? [
                    {
                      key: "monitoring-runtime",
                      label: t("sidebar.monitoring_runtime", "Runtime"),
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/runtime`,
                    },
                  ]
                : []),
              ...(canReadRuntime
                ? [
                    {
                      key: "monitoring-data",
                      label: t("sidebar.monitoring_data", "Data Hub"),
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/data`,
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
                    },
                  ]
                : []),
              ...(canUpdateTag
                ? [
                    {
                      key: "monitoring-rebac-backfill",
                      label: t("sidebar.migration"),
                      icon: <ShieldIcon />,
                      url: `/monitoring/rebac-backfill`,
                    },
                  ]
                : []),
            ],
          },
        ]
      : []),
  ];

  // List user teams
  // todo: handle loading
  // todo: handle error
  const { data: teams } = useListTeamsKnowledgeFlowV1TeamsGetQuery();
  const yourTeams = teams && teams.filter((t) => t.is_member);
  const teamsMenuItem: SideBarNavigationElement[] =
    yourTeams?.map((t) => ({
      key: t.id,
      label: t.name,
      url: `team/${t.id}/${agentsNicknamePlural}`,
      icon: <Avatar src={t.banner_image_url || ""} sx={{ height: "24px", width: "24px" }} />,
    })) || [];

  const logoName = getProperty("logoName") || "fred";
  const logoNameDark = getProperty("logoNameDark") || "fred-dark";

  return (
    <Drawer variant="permanent" open={open}>
      <Paper sx={{ borderRadius: 0 }}>
        <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
          {/* Header (icon + open/close button*/}
          {/* <DrawerHeader> */}
          {open && (
            <Box
              sx={{
                display: "flex",
                width: "100%",
                justifyContent: "flex-start",
                alignItems: "center",
                pl: 2,
                py: 1.5,
                minHeight: "56px",
              }}
            >
              <InvisibleLink to="/new-chat">
                <ImageComponent
                  name={darkMode ? logoNameDark : logoName}
                  height={getProperty("logoHeight")}
                  width={getProperty("logoWidth")}
                />
              </InvisibleLink>
            </Box>
          )}

          {/* Remove collapsing for now */}
          {/* <IconButton onClick={() => setOpen((open) => !open)} sx={{ mr: open ? 0 : 1 }}>
            {open ? <ChevronLeftIcon /> : <ChevronRightIcon />}
          </IconButton> */}
          {/* </DrawerHeader> */}

          {/* New chat button */}
          <Box sx={{ widht: "100%", px: 2, mb: 1 }}>
            <SideBarNewConversationButton />
          </Box>

          {/* Nav */}
          <Box>
            <SideBarNavigationList menuItems={menuItems} isSidebarOpen={open} />
          </Box>

          <SideBarDivider />

          {/* Admin Nav */}
          {isAdmin && (
            <>
              <Box>
                <SideBarNavigationList menuItems={adminMenuItems} isSidebarOpen={open} />
              </Box>
              <SideBarDivider />
            </>
          )}

          {/* Teams */}
          <Box sx={{ display: "flex", alignItems: "center", px: 2, pt: 1 }}>
            <Typography variant="caption" color="textSecondary">
              {t("sidebar.yourTeamsSectionTitle")}
            </Typography>
          </Box>
          <Box
            sx={{
              overflowY: "auto",
              overflowX: "hidden",
              scrollbarWidth: "none",
              maxHeight: "calc(36px * 5.8)",
            }}
          >
            <SideBarNavigationList menuItems={teamsMenuItem} isSidebarOpen={open} />
          </Box>
          <SideBarDivider />

          {/* Conversations */}
          <SideBarConversationsSection isSidebarOpen={open} />

          {/* Profile */}
          <Box sx={{ px: 1, pb: 1 }}>
            <Paper elevation={4} sx={{ borderRadius: 2 }}>
              <SidebarProfileSection isSidebarOpen={open} />
            </Paper>
          </Box>
        </Box>
      </Paper>
    </Drawer>
  );
}

function SideBarDivider() {
  return (
    <Box sx={{ px: 2 }}>
      <Divider />
    </Box>
  );
}
