import AddIcon from "@mui/icons-material/Add";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ConstructionIcon from "@mui/icons-material/Construction";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandLess from "@mui/icons-material/ExpandLess";
import ExpandMore from "@mui/icons-material/ExpandMore";
import GroupIcon from "@mui/icons-material/Group";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import PersonIcon from "@mui/icons-material/Person";
import SettingsIcon from "@mui/icons-material/Settings";
import {
  Box,
  Button,
  Collapse,
  CSSObject,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Paper,
  styled,
  Theme,
  Typography,
  useTheme,
} from "@mui/material";
import MuiDrawer from "@mui/material/Drawer";
import Select, { SelectChangeEvent } from "@mui/material/Select";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { UserAvatar } from "../components/profile/UserAvatar";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { KeyCloakService } from "../security/KeycloakService";
import { usePermissions } from "../security/usePermissions";
import {
  SessionWithFiles,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
} from "../slices/agentic/agenticOpenApi";

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
      <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
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
        <ConversationsSection isSidebarOpen={open} />

        {/* Profile */}
        <Paper elevation={1}>
          <SidebarProfileItem isSidebarOpen={open} />
        </Paper>
      </Box>
    </Drawer>
  );
}
interface ConversationsSectionProps {
  isSidebarOpen: boolean;
}

function ConversationsSection({ isSidebarOpen }: ConversationsSectionProps) {
  const { t } = useTranslation();
  const theme = useTheme();

  const {
    data: agentsFromServer = [],
    isLoading: flowsLoading,
    isError: flowsError,
    error: flowsErrObj,
  } = useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();

  const {
    data: sessionsFromServer,
    isLoading: sessionsLoading,
    isError: sessionsError,
    error: sessionsErrObj,
    refetch: refetchSessions,
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
    refetchOnReconnect: true,
  });

  const allAgentOptionValue = "all-agents";
  const [selectedAgent, setSelectedAgent] = useLocalStorageState<string>(
    "ConversationsSection.selectedAgent",
    allAgentOptionValue,
  );

  const enabledAgents = (agentsFromServer ?? []).filter((a) => a.enabled === true);

  return (
    <>
      {/* Conversation header */}
      {isSidebarOpen && (
        <Paper elevation={1}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", px: 2, py: 1 }}>
            <Typography variant="subtitle2" sx={{ color: theme.palette.text.secondary }}>
              {t("sidebar.chat")}
            </Typography>
            <Button component={Link} to="/chat" variant="outlined" size="small" startIcon={<AddIcon />}>
              {t("common.create")}
            </Button>
          </Box>
          <Box sx={{ px: 2, py: 1 }}>
            <Select
              size="small"
              value={selectedAgent}
              onChange={(event: SelectChangeEvent) => setSelectedAgent(event.target.value as string)}
              sx={{ width: "100%" }}
            >
              <MenuItem value={allAgentOptionValue}>{t("sidebar.allAgents")}</MenuItem>
              {enabledAgents.map((agent) => (
                <MenuItem value={agent.name}>{agent.name}</MenuItem>
              ))}
            </Select>
          </Box>
        </Paper>
      )}

      {/* Conversation list */}
      <Paper
        elevation={0}
        sx={{ flexGrow: 1, overflowY: "auto", overflowX: "hidden", scrollbarWidth: "none", py: 1, px: 1 }}
      >
        {isSidebarOpen && sessionsFromServer?.map((session) => <SideBarConversationListElement session={session} />)}
      </Paper>
    </>
  );
}
interface SideBarConversationListElementProps {
  session: SessionWithFiles;
}

function SideBarConversationListElement({ session }: SideBarConversationListElementProps) {
  const theme = useTheme();
  const location = useLocation();
  const isSelected = location.pathname === `/chat/${session.id}`;

  return (
    <Box
      component={Link}
      to={`/chat/${session.id}`}
      sx={{
        textDecoration: "none",
        color: "inherit",
        display: "block",
      }}
    >
      <Box
        sx={{
          px: 1.5,
          py: 1,
          borderRadius: 1,
          userSelect: "none",
          background: isSelected ? theme.palette.action.selected : "transparent",
          ...(isSelected ? {} : { "&:hover": { background: theme.palette.action.hover } }),
          "&:hover .delete-button": { display: "flex" },
          display: "flex",
          alignItems: "center",
          gap: 1,
        }}
      >
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            flex: 1,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <PersonIcon sx={{ fontSize: "1rem", color: theme.palette.primary.main }} />
            <Typography variant="caption" sx={{ color: theme.palette.primary.main }}>
              Agent 1
            </Typography>
          </Box>
          <Typography
            variant="body2"
            sx={{
              color: theme.palette.text.primary,
              textOverflow: "ellipsis",
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {session.title}
          </Typography>
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
            {dayjs(session.updated_at).format("L")}
          </Typography>
        </Box>
        <IconButton
          className="delete-button"
          size="small"
          onClick={(e) => {
            e.preventDefault(); // Prevent Link navigation
            e.stopPropagation();
            // TODO: Implement delete functionality
          }}
          sx={{
            color: theme.palette.error.main,
            display: "none",
          }}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Box>
    </Box>
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
  const location = useLocation();
  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>({});

  const isActive = (path: string) => {
    const menuPathBase = path.split("?")[0];
    const currentPathBase = location.pathname;
    return currentPathBase === menuPathBase || currentPathBase.startsWith(menuPathBase + "/");
  };

  const isAnyChildActive = (children?: MenuItemCfg[]) => !!children?.some((c) => c.url && isActive(c.url));

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
  }, [location.pathname]);

  return (
    <List>
      {menuItems.map((item) => {
        const hasChildren = !!(item.children && item.children.length > 0);
        const hasLink = !!item.url;
        const isOpen = openKeys[item.key] || false;
        const active = item.url ? isActive(item.url) : isAnyChildActive(item.children);

        return (
          <>
            <ListItemButton
              selected={active}
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
