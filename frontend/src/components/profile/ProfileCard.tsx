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

import AccessTimeIcon from "@mui/icons-material/AccessTime";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import CodeIcon from "@mui/icons-material/Code";
import EmailIcon from "@mui/icons-material/Email";
import FingerprintIcon from "@mui/icons-material/Fingerprint";
import LogoutIcon from "@mui/icons-material/Logout";
import SecurityIcon from "@mui/icons-material/Security";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid2,
  Stack,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import { LanguageSelector } from "../LanguageSelector";
import { ThemeModeSelector } from "../ThemeModeSelector";
import { UserAvatar } from "./UserAvatar";

interface ProfileCardProps {
  username: string;
  userRoles: string[];
  tokenParsed: any; // unused, kept for API compatibility
  fullName: string;
  userEmail: string;
  userId: string;
  formatAuthDate: () => string;
  formatExpDate: () => string;
  onLogout: () => void;
}

export function ProfileCard({
  username,
  userRoles,
  fullName,
  userEmail,
  userId,
  formatAuthDate,
  formatExpDate,
  onLogout,
}: ProfileCardProps) {
  const theme = useTheme();
  const { t } = useTranslation();

  const getRoleIcon = (role: string) => {
    if (role.includes("admin")) return <AdminPanelSettingsIcon fontSize="small" />;
    if (role.includes("manager")) return <SecurityIcon fontSize="small" />;
    if (role.includes("user")) return <AccountCircleIcon fontSize="small" />;
    return <CodeIcon fontSize="small" />;
  };

  // Compact label/value row
  const InfoItem = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) => (
    <Stack spacing={0.5}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Box sx={{ color: "primary.main", display: "inline-flex" }}>{icon}</Box>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
      </Stack>
      <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
        {value}
      </Typography>
    </Stack>
  );

  const SectionTitle = ({ children }: { children: React.ReactNode }) => (
    <Typography
      variant="overline"
      color="text.secondary"
      sx={{ letterSpacing: 0.6, fontWeight: 600, display: "block" }}
    >
      {children}
    </Typography>
  );

  return (
    // Right-anchored container
    <Grid2 size={{ xs: 12 }} display="flex" justifyContent={{ xs: "stretch", md: "flex-end" }} px={{ xs: 1.5, md: 3 }}>
      <Card
        variant="outlined"
        sx={{
          ml: { md: "auto" }, // stick to the right on md+
          width: "100%",
          maxWidth: 980, // comfortable reading width
          borderRadius: 3,
          bgcolor: "transparent", // no paper slab
          boxShadow: "none",
          borderColor: "divider",
        }}
      >
        <CardContent sx={{ py: { xs: 2, md: 3 }, px: { xs: 2, md: 3 } }}>
          {/* Two-column responsive grid */}
          <Grid2 container spacing={3}>
            {/* LEFT COLUMN — identity & controls */}
            <Grid2 size={{ xs: 12, md: 5 }} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <UserAvatar />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="h6" fontWeight={600} noWrap>
                    {fullName}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" noWrap>
                    @{username}
                  </Typography>
                </Box>
              </Stack>

              <Divider />

              <Box>
                <SectionTitle>{t("profile.language")}</SectionTitle>
                <LanguageSelector />
              </Box>

              <Box sx={{ flexGrow: 1 }} />

              <Button
                variant="contained"
                color="primary"
                startIcon={<LogoutIcon />}
                onClick={onLogout}
                sx={{ alignSelf: { xs: "stretch", md: "flex-start" }, textTransform: "none", minHeight: 36 }}
              >
                {t("profile.logout")}
              </Button>
            </Grid2>

            {/* RIGHT COLUMN — account details & roles */}
            <Grid2 size={{ xs: 12, md: 7 }} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <Box>
                <SectionTitle>{t("profile.title", "Profile")}</SectionTitle>
                <Grid2 container spacing={2} sx={{ mt: 0.5 }}>
                  <Grid2 size={{ xs: 12, sm: 6 }}>
                    <InfoItem icon={<EmailIcon fontSize="small" />} label={t("profile.email")} value={userEmail} />
                  </Grid2>
                  <Grid2 size={{ xs: 12, sm: 6 }}>
                    <InfoItem icon={<FingerprintIcon fontSize="small" />} label={t("profile.userId")} value={userId} />
                  </Grid2>
                  <Grid2 size={{ xs: 12, sm: 6 }}>
                    <InfoItem
                      icon={<AccessTimeIcon fontSize="small" />}
                      label={t("profile.authTime")}
                      value={formatAuthDate()}
                    />
                  </Grid2>
                  <Grid2 size={{ xs: 12, sm: 6 }}>
                    <InfoItem
                      icon={<AccessTimeIcon fontSize="small" />}
                      label={t("profile.expTime")}
                      value={formatExpDate()}
                    />
                  </Grid2>
                </Grid2>
              </Box>

              <Divider />

              <Box>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                  <SecurityIcon fontSize="small" />
                  <Typography variant="subtitle2">{t("profile.roles")}</Typography>
                </Stack>
                <Box display="flex" flexWrap="wrap" gap={0.75}>
                  {userRoles.map((role) => (
                    <Tooltip key={role} title={role} arrow disableInteractive>
                      <Chip
                        size="small"
                        icon={getRoleIcon(role)}
                        label={role}
                        sx={{
                          px: 0.5,
                          borderRadius: 1.5,
                          backgroundColor: theme.palette.mode === "dark" ? "primary.dark" : "primary.light",
                          color: theme.palette.mode === "dark" ? "common.white" : "primary.dark",
                          "& .MuiChip-label": { px: 0.5, fontSize: "0.78rem" },
                          "&:hover": { backgroundColor: "primary.main", color: "common.white" },
                        }}
                      />
                    </Tooltip>
                  ))}
                </Box>
              </Box>

              <Divider />

              <Box>
                <SectionTitle>{t("profile.theme.title")}</SectionTitle>
                <ThemeModeSelector />
              </Box>
            </Grid2>
          </Grid2>
        </CardContent>
      </Card>
    </Grid2>
  );
}
