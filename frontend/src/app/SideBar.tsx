import AppsIcon from "@mui/icons-material/Apps";
import ConstructionIcon from "@mui/icons-material/Construction";
import GroupIcon from "@mui/icons-material/Group";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import ScheduleIcon from "@mui/icons-material/Schedule";
import ScienceIcon from "@mui/icons-material/Science";
import ShieldIcon from "@mui/icons-material/Shield";
import { Box, CSSObject, Divider, Paper, styled, Theme } from "@mui/material";
import MuiDrawer from "@mui/material/Drawer";
import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { getProperty } from "../common/config";
import InvisibleLink from "../components/InvisibleLink";
import {
  SideBarConversationsSection,
  SideBarNavigationElement,
  SideBarNavigationList,
  SidebarProfileSection,
} from "../components/sideBar";
import { SideBarNewConversationButton } from "../components/sideBar/SideBarNewConversationButton";
import { KeyCloakService } from "../security/KeycloakService";
import { usePermissions } from "../security/usePermissions";
import { useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery } from "../slices/agentic/agenticOpenApi";
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
  const { data: frontendConfig } = useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery();

  // const [open, setOpen] = useLocalStorageState("SideBar.open", true);
  // Remove collapsing for now
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

  const menuItems: SideBarNavigationElement[] = [
    {
      key: "agent",
      label: t("sidebar.agent", {
        agentsNickname: frontendConfig.frontend_settings.properties.agentsNicknamePlural,
      }),
      icon: <GroupIcon />,
      url: `/agents`,
      tooltip: t("sidebar.tooltip.agent"),
    },
    {
      key: "knowledge",
      label: t("sidebar.knowledge"),
      icon: <MenuBookIcon />,
      url: `/knowledge`,
      tooltip: t("sidebar.tooltip.knowledge"),
    },
  ];
  const appsMenuItems: SideBarNavigationElement[] = [
    {
      key: "apps",
      label: t("sidebar.apps", "Apps"),
      icon: <AppsIcon />,
      tooltip: t("sidebar.tooltip.apps", "Run and test app workflows"),
      children: [
        {
          key: "apps-scheduler",
          label: t("sidebar.apps_scheduler", "Scheduler"),
          icon: <ScheduleIcon />,
          url: `/apps/scheduler`,
          tooltip: t("sidebar.tooltip.apps_scheduler", "Submit and track scheduled tasks"),
        },
      ],
    },
  ];
  const adminMenuItems: SideBarNavigationElement[] = [
    {
      key: "mcp",
      label: t("sidebar.mcp"),
      icon: <ConstructionIcon />,
      url: `/tools`,
      tooltip: t("sidebar.tooltip.mcp"),
    },
    ...(canReadKpis || canReadOpenSearch || canReadLogs || canReadRuntime || canUpdateTag
      ? [
          {
            key: "laboratory",
            label: t("sidebar.laboratory"),
            icon: <ScienceIcon />,
            tooltip: t("sidebar.tooltip.laboratory"),
            children: [
              ...(canReadRuntime
                ? [
                    {
                      key: "monitoring-graph",
                      label: t("sidebar.monitoring_graph", "Graph Hub"),
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/graph`,
                      tooltip: t("sidebar.tooltip.monitoring_graph", "Knowledge graph view"),
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
                      tooltip: t("sidebar.tooltip.monitoring_processors"),
                    },
                  ]
                : []),
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
            tooltip: t("sidebar.tooltip.monitoring"),
            children: [
              ...(canReadKpis
                ? [
                    {
                      key: "monitoring-kpi",
                      label: t("sidebar.monitoring_kpi") || "KPI",
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/kpis`,
                      tooltip: t("sidebar.tooltip.monitoring_kpi") || "KPI Overview",
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
                      tooltip: t("sidebar.tooltip.monitoring_runtime", "Runtime summary"),
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
                      tooltip: t("sidebar.tooltip.monitoring_data", "Data lineage view"),
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
                      tooltip: t("sidebar.tooltip.monitoring_logs"),
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
                      tooltip: t("sidebar.tooltip.migration", "Rebuild ReBAC relations"),
                    },
                  ]
                : []),
            ],
          },
        ]
      : []),
  ];

  const { darkMode } = useContext(ApplicationContext);
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

          <Box sx={{ widht: "100%", px: 2, mb: 1 }}>
            <SideBarNewConversationButton />
          </Box>

          {/* Nav */}
          <Box>
            <SideBarNavigationList menuItems={menuItems} isSidebarOpen={open} />
          </Box>

          <SideBarDivider />

          {/* Apps Nav */}
          <Box>
            <SideBarNavigationList menuItems={appsMenuItems} isSidebarOpen={open} />
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
