// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at:
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
import { KeyCloakService } from "../security/KeycloakService";
import { ProfileCard } from "../components/profile/ProfileCard";
import { ProfileToken } from "../components/profile/ProfileToken";
import { TopBar } from "../common/TopBar";
import { useSearchParams } from "react-router-dom";
import InvisibleLink from "../components/InvisibleLink";
import { useTranslation } from "react-i18next";

function getFallbackTab(): number {
  const savedTab = localStorage.getItem("last_profile_active_tab");
  return parseInt(savedTab, 10) || 0;
}

export function Profile() {
  const theme = useTheme<Theme>();
  const { t } = useTranslation();

  const username = KeyCloakService.GetUserName() || t("profile.notAvailable");
  const userRoles = KeyCloakService.GetUserRoles() || [t("profile.notAvailable")];
  const tokenParsed = KeyCloakService.GetTokenParsed() || t("profile.notAvailable");
  const fullName = KeyCloakService.GetUserFullName() || username || t("profile.notAvailable");
  const userEmail = KeyCloakService.GetUserMail() || t("profile.notAvailable");
  const userId = KeyCloakService.GetUserId().substring(0, 8) || t("profile.notAvailable");

  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab = tabParam !== null && !isNaN(Number(tabParam)) ? Number(tabParam) : getFallbackTab();

  useEffect(() => {
    if (tabParam === null) {
      const fallbackTab = getFallbackTab();
      setSearchParams({ tab: fallbackTab.toString() }, { replace: true });
    }
  }, [tabParam, setSearchParams]);

  useEffect(() => {
    localStorage.setItem("last_profile_active_tab", activeTab.toString());
  }, [activeTab]);

  const formatAuthDate = () => {
    if (!tokenParsed?.auth_time) return t("profile.notAvailable");
    return new Date(tokenParsed.auth_time * 1000).toLocaleString();
  };

  const formatExpDate = () => {
    if (!tokenParsed?.exp) return t("profile.notAvailable");
    return new Date(tokenParsed.exp * 1000).toLocaleString();
  };

  const menuItems = [
    { label: t("profile.menu.account"), icon: <AccountCircleIcon /> },
    { label: t("profile.menu.token"), icon: <KeyIcon /> },
  ];

  return (
    <>
      <TopBar title={t("profile.title")} description={t("profile.description")} />

      <Box sx={{ width: "95%", mx: "auto", px: 2, py: 8 }}>
        {username ? (
          <Box display="flex">
            <Box width={200} mr={4}>
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
              {t("profile.noUser")}
            </Typography>
            <Button
              variant="contained"
              color="primary"
              sx={{ mt: 2, borderRadius: 2 }}
              onClick={() => (window.location.href = "/login")}
            >
              {t("profile.login")}
            </Button>
          </Paper>
        )}
      </Box>
    </>
  );
}
