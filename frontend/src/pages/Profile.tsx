// components/profile/Profile.tsx
import { useEffect } from "react";
import {
  Box,
  Paper,
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
import { useSearchParams } from "react-router-dom";
import InvisibleLink from "../components/InvisibleLink";

function getFallbackTab(): number {
  const savedTab = localStorage.getItem("last_profile_active_tab");
  return parseInt(savedTab, 10) || 0;
}

export function Profile() {
  const theme = useTheme<Theme>();

  const username = KeyCloakService.GetUserName();
  const userRoles = KeyCloakService.GetUserRoles();
  const tokenParsed = KeyCloakService.GetTokenParsed();
  const fullName = tokenParsed?.name || username || "Not available";
  const userEmail = tokenParsed?.email || "Not available";
  const userId = tokenParsed?.sub?.substring(0, 8) || "Not available";

  // Get tab index from URL param, fallback to localStorage, and redirect if needed
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab = tabParam !== null && !isNaN(Number(tabParam)) ? Number(tabParam) : getFallbackTab();
  console.log("Active tab:", activeTab);

  // On mount: if tab param is missing, redirect to URL with correct tab param
  useEffect(() => {
    if (tabParam === null) {
      const fallbackTab = getFallbackTab();
      setSearchParams({ tab: fallbackTab.toString() }, { replace: true });
    }
  }, [tabParam, setSearchParams]);

  // When tab changes via URL, update localStorage
  useEffect(() => {
    localStorage.setItem("last_profile_active_tab", activeTab.toString());
  }, [activeTab]);

  const formatAuthDate = () => {
    if (!tokenParsed?.auth_time) return "Not available";
    return new Date(tokenParsed.auth_time * 1000).toLocaleString();
  };

  const formatExpDate = () => {
    if (!tokenParsed?.exp) return "Not available";
    return new Date(tokenParsed.exp * 1000).toLocaleString();
  };

  const menuItems = [
    { label: "Account", icon: <AccountCircleIcon /> },
    { label: "Token", icon: <KeyIcon /> },
    { label: "Agentic Profiles", icon: <ChatIcon /> },
  ];

  return (
    <PageBodyWrapper>
      <TopBar title="User Profile" description="Manage your user preferences and chat profiles" />

      <Box sx={{ width: "95%", mx: "auto", px: 2, py: 8 }}>
        {username ? (
          <Box display="flex">
            <Box width={200} mr={4}>
              {/* Tab selector */}
              <Paper elevation={1}>
                <List>
                  {menuItems.map((item, index) => (
                    <InvisibleLink to={{ search: `?tab=${index}` }} key={item.label}>
                      <ListItemButton
                        selected={activeTab === index}
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
                    </InvisibleLink>
                  ))}
                </List>
              </Paper>
            </Box>

            <Box flexGrow={1}>
              {/* Active tab */}
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
              backgroundColor: theme.palette.mode === "dark" ? "background.paper" : "white",
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
