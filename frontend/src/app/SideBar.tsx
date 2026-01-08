import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ConstructionIcon from "@mui/icons-material/Construction";
import GroupIcon from "@mui/icons-material/Group";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import ShieldIcon from "@mui/icons-material/Shield";
import { Box, CSSObject, IconButton, Paper, styled, Theme } from "@mui/material";
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
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { usePermissions } from "../security/usePermissions";
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

const DrawerHeader = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  padding: theme.spacing(1, 1),
}));

export default function SideBar() {
  const { t } = useTranslation();

  const [open, setOpen] = useLocalStorageState("SideBar.open", true);

  // Here we set the "can" action to "create" since we want the viewer role not to see kpis and logs.
  // We also can remove the read_only allowed action to the viewer; to: kpi, opensearch & logs in rbac.py in fred_core/security
  // but for now we can leave it like that.
  const { can } = usePermissions();
  const canReadKpis = can("kpi", "create");
  const canReadOpenSearch = can("opensearch", "create");
  const canReadLogs = can("logs", "create");
  const canReadRuntime = can("kpi", "create");
  const canUpdateTag = can("tag", "update");

  const menuItems: SideBarNavigationElement[] = [
    {
      key: "agent",
      label: t("sidebar.agent"),
      icon: <GroupIcon />,
      url: `/agents`,
      tooltip: t("sidebar.tooltip.agent"),
    },
    {
      key: "mcp",
      label: t("sidebar.mcp"),
      icon: <ConstructionIcon />,
      url: `/tools`,
      tooltip: t("sidebar.tooltip.mcp"),
    },
    {
      key: "knowledge",
      label: t("sidebar.knowledge"),
      icon: <MenuBookIcon />,
      url: `/knowledge`,
      tooltip: t("sidebar.tooltip.knowledge"),
    },

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
      <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
        {/* Header (icon + open/close button*/}
        <DrawerHeader>
          {open && (
            <Box sx={{ display: "flex", width: "100%", justifyContent: "flex-start", alignItems: "center", pl: 1 }}>
              <InvisibleLink to="/">
                <ImageComponent name={darkMode ? logoNameDark : logoName} width="36px" height="36px" />
              </InvisibleLink>
            </Box>
          )}
          <IconButton onClick={() => setOpen((open) => !open)} sx={{ mr: open ? 0 : 1 }}>
            {open ? <ChevronLeftIcon /> : <ChevronRightIcon />}
          </IconButton>
        </DrawerHeader>

        {/* Nav */}
        <Paper elevation={0}>
          <SideBarNavigationList menuItems={menuItems} isSidebarOpen={open} />
        </Paper>

        {/* Conversations */}
        <SideBarConversationsSection isSidebarOpen={open} />

        {/* Profile */}
        <Paper elevation={1}>
          <SidebarProfileSection isSidebarOpen={open} />
        </Paper>
      </Box>
    </Drawer>
  );
}
