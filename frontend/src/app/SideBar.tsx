import ChatIcon from "@mui/icons-material/Chat";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ConstructionIcon from "@mui/icons-material/Construction";
import ExpandLess from "@mui/icons-material/ExpandLess";
import ExpandMore from "@mui/icons-material/ExpandMore";
import GroupIcon from "@mui/icons-material/Group";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import SettingsIcon from "@mui/icons-material/Settings";
import {
  Box,
  Collapse,
  CSSObject,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  styled,
  Theme,
} from "@mui/material";
import MuiDrawer from "@mui/material/Drawer";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { UserAvatar } from "../components/profile/UserAvatar";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { KeyCloakService } from "../security/KeycloakService";
import { usePermissions } from "../security/usePermissions";

const drawerWidth = 240;

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

type MenuItemCfg = {
  key: string;
  label: string;
  icon: React.ReactNode;
  url?: string;
  tooltip: string;
  children?: MenuItemCfg[];
};

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

  const menuItems: MenuItemCfg[] = [
    {
      key: "chat",
      label: t("sidebar.chat"),
      icon: <ChatIcon />,
      url: `/chat`,
      tooltip: t("sidebar.tooltip.chat"),
    },
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
    ...(canReadKpis || canReadOpenSearch || canReadLogs || canReadRuntime
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
                      key: "monitoring-processors",
                      label: t("sidebar.monitoring_processors", "Processors"),
                      icon: <MonitorHeartIcon />,
                      url: `/monitoring/processors`,
                      tooltip: t("sidebar.tooltip.monitoring_processors", "Processor bench"),
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
                      tooltip: t("sidebar.tooltip.monitoring_logs") || "Log Console",
                    },
                  ]
                : []),
            ],
          },
        ]
      : []),
  ];

  return (
    <Drawer variant="permanent" open={open}>
      {/* Header (icon + open/close button*/}
      <DrawerHeader>
        <IconButton onClick={() => setOpen((open) => !open)} sx={{ mr: open ? 0 : 1 }}>
          {open ? <ChevronLeftIcon /> : <ChevronRightIcon />}
        </IconButton>
      </DrawerHeader>

      {/* Nav */}
      <Paper elevation={0}>
        <SideBarMenuList menuItems={menuItems} isSidebarOpen={open} />
      </Paper>

      {/* Conversations */}
      <Box>
        {/* Conversation header */}
        <Paper elevation={1}></Paper>
        {/* Conversation list */}
        <Paper elevation={0}></Paper>
      </Box>

      {/* Profile */}
      <Paper elevation={1}>
        <SidebarProfileItem isSidebarOpen={open} />
      </Paper>
    </Drawer>
  );
}

interface SidebarProfileItemProps {
  isSidebarOpen: boolean;
}

function SidebarProfileItem({ isSidebarOpen }: SidebarProfileItemProps) {
  const roles = KeyCloakService.GetUserRoles();

  return (
    <ListItem
      dense
      sx={{ py: 1 }}
      secondaryAction={
        <IconButton component={Link} to="/settings">
          <SettingsIcon />
        </IconButton>
      }
    >
      <ListItemIcon>{isSidebarOpen && <UserAvatar />}</ListItemIcon>
      <ListItemText primary={KeyCloakService.GetUserFullName()} secondary={roles.length > 0 ? roles[0] : undefined} />
    </ListItem>
  );
}

interface SideBarMenuListProps {
  menuItems: MenuItemCfg[];
  isSidebarOpen: boolean;
  indentation?: number;
}

function SideBarMenuList({ menuItems, isSidebarOpen, indentation = 0 }: SideBarMenuListProps) {
  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>({});

  return (
    <List>
      {menuItems.map((item) => {
        const hasChildren = !!(item.children && item.children.length > 0);
        const hasLink = !!item.url;
        const isOpen = openKeys[item.key] || false;

        return (
          <>
            <ListItemButton
              dense={indentation > 0}
              key={item.key}
              component={hasLink ? Link : "div"}
              {...(hasLink ? { to: item.url } : {})}
              onClick={
                hasChildren ? () => setOpenKeys((prev) => ({ ...prev, [item.key]: !prev[item.key] })) : undefined
              }
              sx={{ pl: 2 + indentation * 2 }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
              {hasChildren && (isOpen ? <ExpandLess /> : <ExpandMore />)}
            </ListItemButton>
            {true && <div></div>}
            {item.children && item.children.length > 0 && (
              <Collapse in={isSidebarOpen && isOpen} timeout="auto" unmountOnExit>
                <SideBarMenuList
                  menuItems={item.children}
                  isSidebarOpen={isSidebarOpen}
                  indentation={indentation + 1}
                />
              </Collapse>
            )}
          </>
        );
      })}
    </List>
  );
}
