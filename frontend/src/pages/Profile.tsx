// components/profile/Profile.tsx
import { useState } from "react";
import {
  Box,
  Paper,
  Stack,
  Tooltip,
  Typography,
  Theme,
  Button,
  useTheme,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import KeyIcon from "@mui/icons-material/VpnKey";
import ChatIcon from "@mui/icons-material/Chat";
import { PageBodyWrapper } from "../common/PageBodyWrapper";
import { KeyCloakService } from "../security/KeycloakService";
import { ProfileCard } from "../components/profile/ProfileCard";
import { ProfileToken } from "../components/profile/ProfileToken";
import { ChatProfiles } from "../components/profile/ChatProfile";
import { TopBar } from "../common/TopBar";

export function Profile() {
  const theme = useTheme<Theme>();
  const username = KeyCloakService.GetUserName();
  const userRoles = KeyCloakService.GetUserRoles();
  const tokenParsed = KeyCloakService.GetTokenParsed();
  const [showToken, setShowToken] = useState(false);

  const theme = useTheme<Theme>();

  const getInitials = () => {
    if (!username) return "U";
    const names = username.split(" ");
    if (names.length > 1) {
      return `${names[0][0]}${names[1][0]}`.toUpperCase();
    }
    return username.substring(0, 2).toUpperCase();
  };

  const getAvatarColor = () => {
  if (userRoles.includes("admin")) return theme.palette.error.main;
  if (userRoles.includes("manager")) return theme.palette.secondary.dark;
  return theme.palette.primary.main;
};

  const getRoleIcon = (role) => {
    if (role.includes("admin")) return <AdminPanelSettingsIcon fontSize="small" />;
    if (role.includes("user")) return <AccountCircleIcon fontSize="small" />;
    if (role.includes("manager")) return <SecurityIcon fontSize="small" />;
    return <CodeIcon fontSize="small" />;
  };

  const formatAuthDate = () => {
    if (!tokenParsed?.auth_time) return "Not available";
    return new Date(tokenParsed.auth_time * 1000).toLocaleString();
  };

  const formatExpDate = () => {
    if (!tokenParsed?.exp) return "Not available";
    return new Date(tokenParsed.exp * 1000).toLocaleString();
  };

  const menuItems = [
    { label: "Account Info", icon: <AccountCircleIcon /> },
    { label: "Session Token", icon: <KeyIcon /> },
    { label: "Agent Preferences", icon: <ChatIcon /> },
  ];

  return (
    <PageBodyWrapper>
      <TopBar
        title="User Profile"
        description="Manage your user preferences and chat profiles"
      />

      <Box sx={{ width: "95%", mx: "auto", px: 2, py: 8 }}>
        {username ? (
          <Box display="flex">
            <Box width={340} mr={4}>
              <Paper elevation={1}>
                <List>
                  {menuItems.map((item, index) => (
                    <ListItemButton
                      key={item.label}
                      selected={activeTab === index}
                      onClick={() => {
                        setActiveTab(index);
                        localStorage.setItem("profile_active_tab", index.toString());
                      }}
                      sx={{
                        borderRadius: 2,
                        mx: 1,
                        my: 0.5,
                        px: 2,
                        py: 1.2,
                        bgcolor: activeTab === index ? theme.palette.sidebar.activeItem : "transparent",
                        "&:hover": {
                          bgcolor: theme.palette.sidebar.hoverColor,
                        },
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
                      <ListItemText
                        primary={
                          <Typography
                            variant="sidebar"
                            fontWeight={activeTab === index ? 500 : 300}
                            color={activeTab === index ? "text.primary" : "text.secondary"}
                          >
                            {item.label}
                          </Typography>
                        }
                      />
                    </ListItemButton>
                  ))}
                </List>
              </Paper>
            </Box>

            <Box flexGrow={1}>
              {activeTab === 0 && (
                <ProfileCard
                  username={username}
                  userRoles={userRoles}
                  tokenParsed={tokenParsed}
                  fullName={fullName}
                  userEmail={userEmail}
                  userId={userId}
                  formatAuthDate={formatAuthDate}
                  formatExpDate={formatExpDate}
                  onLogout={KeyCloakService.CallLogout}
                />
              )}

              {activeTab === 1 && <ProfileToken tokenParsed={tokenParsed} />}

              {activeTab === 2 && <ChatProfiles />}
            </Box>
          </Box>
        ) : (
          <Paper
            elevation={2}
            sx={{
              p: 4,
              textAlign: "center",
              borderRadius: 2,
              backgroundColor:
                theme.palette.mode === "dark" ? "background.paper" : "white",
            }}
          >
            <Typography variant="h5" sx={{ color: "text.secondary" }}>
              No user connected
            </Typography>
            <Button
              variant="contained"
              color="primary"
              sx={{ mt: 2, borderRadius: 2 }}
              onClick={() => (window.location.href = "/login")}
            >
              Log in
            </Button>
          </Paper>
        )}
      </Box>
    </PageBodyWrapper>
  );
}
