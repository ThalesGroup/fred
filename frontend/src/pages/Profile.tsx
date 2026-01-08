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
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import KeyIcon from "@mui/icons-material/VpnKey";
import {
  Box,
  Button,
  Card,
  CardContent,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Theme,
  Typography,
  useTheme,
} from "@mui/material";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import InvisibleLink from "../components/InvisibleLink";
import { ProfileCard } from "../components/profile/ProfileCard";
import { ProfileToken } from "../components/profile/ProfileToken";
import { KeyCloakService } from "../security/KeycloakService";
import ReleaseNotes from "./ReleaseNotes";

function getFallbackTab(): number {
  const savedTab = localStorage.getItem("last_profile_active_tab");
  return parseInt(savedTab || "0", 10) || 0;
}

export function Profile() {
  const theme = useTheme<Theme>();
  const { t } = useTranslation();

  const username = KeyCloakService.GetUserName() || t("profile.notAvailable");
  const userRoles = KeyCloakService.GetUserRoles() || [t("profile.notAvailable")];
  const tokenParsed = KeyCloakService.GetTokenParsed() || null;

  const fullName = KeyCloakService.GetUserFullName() || username || t("profile.notAvailable");
  const userEmail = KeyCloakService.GetUserMail() || t("profile.notAvailable");
  const rawUserId = KeyCloakService.GetUserId?.() || "";
  const userId = rawUserId ? rawUserId.substring(0, 8) : t("profile.notAvailable");

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
    { label: t("profile.menu.account"), icon: <AccountCircleIcon fontSize="small" /> },
    { label: t("profile.menu.token"), icon: <KeyIcon fontSize="small" /> },
    { label: t("profile.menu.releaseNotes"), icon: <InfoOutlinedIcon fontSize="small" /> },
  ];

  return (
    <>
      <TopBar title={t("profile.title")} description={t("profile.description")} />

      <Box
        sx={{
          width: "100%",
          flexGrow: 1,
          overflowY: "auto",
          mx: "auto",
          px: { xs: 2, md: 3 },
          py: { xs: 4, md: 6 },
        }}
      >
        {username ? (
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", md: "220px 1fr" },
              columnGap: { xs: 0, md: 3 },
              rowGap: 3,
              alignItems: "start",
            }}
          >
            {/* Left rail (outlined, transparent, sticky on md+) */}
            <Box
              component="nav"
              sx={{
                position: { md: "sticky" },
                top: { md: 0 },
                alignSelf: "start",
              }}
            >
              <Card
                variant="outlined"
                sx={{
                  borderRadius: 2,
                  bgcolor: "transparent",
                  boxShadow: "none",
                  borderColor: "divider",
                }}
              >
                <List dense disablePadding sx={{ p: 1 }}>
                  {menuItems.map((item, index) => (
                    <InvisibleLink to={{ search: `?tab=${index}` }} key={item.label}>
                      <ListItemButton
                        selected={activeTab === index}
                        sx={{
                          borderRadius: 1.5,
                          px: 1.25,
                          py: 0.75,
                          mb: 0.5,
                          border: (t) =>
                            `1px solid ${activeTab === index ? t.palette.primary.main : t.palette.divider}`,
                          backgroundColor:
                            activeTab === index
                              ? theme.palette.mode === "dark"
                                ? "rgba(25,118,210,0.10)"
                                : "rgba(25,118,210,0.06)"
                              : "transparent",
                          "&:hover": {
                            backgroundColor:
                              activeTab === index
                                ? theme.palette.mode === "dark"
                                  ? "rgba(25,118,210,0.14)"
                                  : "rgba(25,118,210,0.10)"
                                : theme.palette.sidebar.hoverColor,
                          },
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 30, color: "inherit" }}>{item.icon}</ListItemIcon>
                        <ListItemText
                          primary={
                            <Typography
                              variant="sidebar"
                              fontWeight={activeTab === index ? 600 : 300}
                              color={activeTab === index ? "text.primary" : "text.secondary"}
                              noWrap
                            >
                              {item.label}
                            </Typography>
                          }
                        />
                      </ListItemButton>
                    </InvisibleLink>
                  ))}
                </List>
              </Card>
            </Box>

            {/* Right content */}
            <Box sx={{ minWidth: 0 }}>
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

              {activeTab === 2 && (
                <Card sx={{ mx: { xs: 1.5, md: 3 } }}>
                  <ReleaseNotes />
                </Card>
              )}
            </Box>
          </Box>
        ) : (
          // Signed out / no user
          <Card
            variant="outlined"
            sx={{
              maxWidth: 760,
              borderRadius: 3,
              bgcolor: "transparent",
              boxShadow: "none",
              borderColor: "divider",
            }}
          >
            <CardContent sx={{ py: { xs: 3, md: 4 }, px: { xs: 2, md: 3 }, textAlign: "center" }}>
              <Typography variant="h6" sx={{ color: "text.secondary", mb: 1 }}>
                {t("profile.noUser")}
              </Typography>
              <Button
                variant="contained"
                color="primary"
                sx={{ mt: 1.5, borderRadius: 2, textTransform: "none" }}
                onClick={() => (window.location.href = "/login")}
              >
                {t("profile.login")}
              </Button>
            </CardContent>
          </Card>
        )}
      </Box>
    </>
  );
}
